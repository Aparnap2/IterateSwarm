package web

import (
	"database/sql"
	"time"

	"github.com/gofiber/fiber/v2"
)

// TelemetryOverview represents telemetry overview data
type TelemetryOverview struct {
	RPM         int     `json:"rpm"`
	RPMChange   float64 `json:"rpm_change"`
	SuccessRate float64 `json:"success_rate"`
	AvgLatency  float64 `json:"avg_latency"`
	P95Latency  float64 `json:"p95_latency"`
	ErrorRate   float64 `json:"error_rate"`
	Alerts      []Alert `json:"alerts"`
}

// Alert represents a telemetry alert
type Alert struct {
	Severity string `json:"severity"`
	Message  string `json:"message"`
	Time     string `json:"time"`
}

// FinanceAlert represents a finance anomaly alert
type FinanceAlert struct {
	ID        string    `json:"id"`
	TenantID  string    `json:"tenant_id"`
	Vendor    string    `json:"vendor"`
	Amount    float64   `json:"amount"`
	Expected  float64   `json:"expected"`
	Multiple  float64   `json:"multiple"`
	Urgency   string    `json:"urgency"` // low, medium, high, critical
	Headline  string    `json:"headline"`
	CreatedAt time.Time `json:"created_at"`
	HITLSent  bool      `json:"hitl_sent"`
}

// BIQueryResult represents a BI query result
type BIQueryResult struct {
	ID        string    `json:"id"`
	TenantID  string    `json:"tenant_id"`
	Query     string    `json:"query"`
	Result    string    `json:"result"`
	ChartURL  string    `json:"chart_url"`
	CreatedAt time.Time `json:"created_at"`
}

// GetTelemetryPanel renders the telemetry panel
func (h *Handler) GetTelemetryPanel(c *fiber.Ctx) error {
	return Render(c, "telemetry_panel", nil)
}

// GetTelemetryOverview returns telemetry overview data from agent_traces
func (h *Handler) GetTelemetryOverview(c *fiber.Ctx) error {
	overview := TelemetryOverview{
		RPM:         0,
		RPMChange:   0,
		SuccessRate: 100.0,
		AvgLatency:  0,
		P95Latency:  0,
		ErrorRate:   0,
		Alerts:      []Alert{},
	}

	if h.db != nil {
		// RPM: count of traces in last minute
		var rpm int
		_ = h.db.QueryRow(`SELECT COUNT(*) FROM agent_traces WHERE created_at > NOW() - INTERVAL '1 minute'`).Scan(&rpm)
		overview.RPM = rpm

		// RPM change: compare to previous minute
		var prevRpm int
		_ = h.db.QueryRow(`SELECT COUNT(*) FROM agent_traces WHERE created_at BETWEEN NOW() - INTERVAL '2 minutes' AND NOW() - INTERVAL '1 minute'`).Scan(&prevRpm)
		if prevRpm > 0 {
			overview.RPMChange = float64(rpm-prevRpm) / float64(prevRpm) * 100
		}

		// Success rate and error rate
		var total, failed int
		_ = h.db.QueryRow(`SELECT COUNT(*) FROM agent_traces WHERE created_at > NOW() - INTERVAL '1 hour'`).Scan(&total)
		_ = h.db.QueryRow(`SELECT COUNT(*) FROM agent_traces WHERE status = 'failed' AND created_at > NOW() - INTERVAL '1 hour'`).Scan(&failed)
		if total > 0 {
			overview.SuccessRate = float64(total-failed) / float64(total) * 100
			overview.ErrorRate = float64(failed) / float64(total) * 100
		}

		// Average latency from agent_traces
		var avgLatency sql.NullFloat64
		_ = h.db.QueryRow(`SELECT AVG(COALESCE(duration_ms, 0)) FROM agent_traces WHERE created_at > NOW() - INTERVAL '1 hour'`).Scan(&avgLatency)
		if avgLatency.Valid {
			overview.AvgLatency = avgLatency.Float64
		}

		// P95 latency
		var p95Latency sql.NullFloat64
		_ = h.db.QueryRow(`
			SELECT PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms)
			FROM agent_traces WHERE created_at > NOW() - INTERVAL '1 hour'
		`).Scan(&p95Latency)
		if p95Latency.Valid {
			overview.P95Latency = p95Latency.Float64
		}

		// Alerts from self_guardian_alerts
		alertRows, err := h.db.Query(`
			SELECT severity, COALESCE(description, ''), created_at
			FROM self_guardian_alerts
			WHERE created_at > NOW() - INTERVAL '24 hours'
			ORDER BY created_at DESC
			LIMIT 5
		`)
		if err == nil {
			defer alertRows.Close()
			for alertRows.Next() {
				var a Alert
				var alertTime time.Time
				if err := alertRows.Scan(&a.Severity, &a.Message, &alertTime); err == nil {
					a.Time = alertTime.Format(time.RFC3339)
					overview.Alerts = append(overview.Alerts, a)
				}
			}
		}
	}

	return c.JSON(overview)
}

// GetSigNozData returns trace data from agent_traces
func (h *Handler) GetSigNozData(c *fiber.Ctx) error {
	traces := []fiber.Map{}
	services := []string{}

	if h.db != nil {
		rows, err := h.db.Query(`
			SELECT trace_id, COALESCE(agent_name, ''), COALESCE(action, ''),
			       COALESCE(status, ''), COALESCE(duration_ms, 0), created_at
			FROM agent_traces
			ORDER BY created_at DESC
			LIMIT 50
		`)
		if err == nil {
			defer rows.Close()
			for rows.Next() {
				var traceID, agentName, action, status string
				var durationMs int
				var createdAt time.Time
				if err := rows.Scan(&traceID, &agentName, &action, &status, &durationMs, &createdAt); err == nil {
					traces = append(traces, fiber.Map{
						"trace_id":    traceID,
						"agent":       agentName,
						"action":      action,
						"status":      status,
						"duration_ms": durationMs,
						"timestamp":   createdAt.Format(time.RFC3339),
					})
				}
			}
		}

		// Distinct agent names as services
		svcRows, err := h.db.Query(`SELECT DISTINCT agent_name FROM agent_traces WHERE agent_name IS NOT NULL AND agent_name != ''`)
		if err == nil {
			defer svcRows.Close()
			for svcRows.Next() {
				var svc string
				if err := svcRows.Scan(&svc); err == nil {
					services = append(services, svc)
				}
			}
		}
	}

	if services == nil {
		services = []string{}
	}

	return c.JSON(fiber.Map{
		"traces":   traces,
		"services": services,
	})
}

// GetHyperDXData returns log data from audit_log
func (h *Handler) GetHyperDXData(c *fiber.Ctx) error {
	logs := []fiber.Map{}
	query := ""

	if h.db != nil {
		rows, err := h.db.Query(`
			SELECT agent_name, action, outcome, COALESCE(tool_name, ''), created_at
			FROM audit_log
			ORDER BY created_at DESC
			LIMIT 50
		`)
		if err == nil {
			defer rows.Close()
			for rows.Next() {
				var agentName, action, outcome, toolName string
				var createdAt time.Time
				if err := rows.Scan(&agentName, &action, &outcome, &toolName, &createdAt); err == nil {
					logs = append(logs, fiber.Map{
						"agent":     agentName,
						"action":    action,
						"outcome":   outcome,
						"tool":      toolName,
						"timestamp": createdAt.Format(time.RFC3339),
					})
				}
			}
		}
		query = "SELECT agent_name, action, outcome, tool_name, created_at FROM audit_log ORDER BY created_at DESC LIMIT 50"
	}

	return c.JSON(fiber.Map{
		"logs":  logs,
		"query": query,
	})
}

// GetMetricsData returns aggregated metrics from agent_traces
func (h *Handler) GetMetricsData(c *fiber.Ctx) error {
	metrics := []fiber.Map{}

	if h.db != nil {
		// Total traces
		var totalTraces int
		_ = h.db.QueryRow(`SELECT COUNT(*) FROM agent_traces`).Scan(&totalTraces)
		metrics = append(metrics, fiber.Map{
			"name":   "total_traces",
			"value":  totalTraces,
			"type":   "counter",
			"labels": fiber.Map{"source": "agent_traces"},
		})

		// Traces in last hour
		var hourlyTraces int
		_ = h.db.QueryRow(`SELECT COUNT(*) FROM agent_traces WHERE created_at > NOW() - INTERVAL '1 hour'`).Scan(&hourlyTraces)
		metrics = append(metrics, fiber.Map{
			"name":   "hourly_traces",
			"value":  hourlyTraces,
			"type":   "gauge",
			"labels": fiber.Map{"window": "1h"},
		})

		// Failed traces in last hour
		var failedTraces int
		_ = h.db.QueryRow(`SELECT COUNT(*) FROM agent_traces WHERE status = 'failed' AND created_at > NOW() - INTERVAL '1 hour'`).Scan(&failedTraces)
		metrics = append(metrics, fiber.Map{
			"name":   "failed_traces_1h",
			"value":  failedTraces,
			"type":   "gauge",
			"labels": fiber.Map{"window": "1h"},
		})

		// Average duration
		var avgDuration sql.NullFloat64
		_ = h.db.QueryRow(`SELECT AVG(COALESCE(duration_ms, 0)) FROM agent_traces WHERE created_at > NOW() - INTERVAL '1 hour'`).Scan(&avgDuration)
		if avgDuration.Valid {
			metrics = append(metrics, fiber.Map{
				"name":   "avg_duration_ms",
				"value":  avgDuration.Float64,
				"type":   "gauge",
				"labels": fiber.Map{"window": "1h"},
			})
		}

		// Total LLM tokens used
		var totalTokens sql.NullInt64
		_ = h.db.QueryRow(`SELECT COALESCE(SUM(llm_tokens), 0) FROM agent_traces WHERE created_at > NOW() - INTERVAL '24 hours'`).Scan(&totalTokens)
		if totalTokens.Valid {
			metrics = append(metrics, fiber.Map{
				"name":   "llm_tokens_24h",
				"value":  totalTokens.Int64,
				"type":   "counter",
				"labels": fiber.Map{"window": "24h"},
			})
		}
	}

	return c.JSON(fiber.Map{
		"metrics": metrics,
	})
}

// GetLogsData returns log data from audit_log
func (h *Handler) GetLogsData(c *fiber.Ctx) error {
	logs := []fiber.Map{}

	if h.db != nil {
		rows, err := h.db.Query(`
			SELECT agent_name, action, outcome, COALESCE(tool_name, ''), created_at
			FROM audit_log
			ORDER BY created_at DESC
			LIMIT 50
		`)
		if err == nil {
			defer rows.Close()
			for rows.Next() {
				var agentName, action, outcome, toolName string
				var createdAt time.Time
				if err := rows.Scan(&agentName, &action, &outcome, &toolName, &createdAt); err == nil {
					logs = append(logs, fiber.Map{
						"agent":     agentName,
						"action":    action,
						"outcome":   outcome,
						"tool":      toolName,
						"timestamp": createdAt.Format(time.RFC3339),
					})
				}
			}
		}
	}

	return c.JSON(fiber.Map{
		"logs": logs,
	})
}

// GetFinanceAlerts returns recent finance anomalies from agent_outputs
func (h *Handler) GetFinanceAlerts(c *fiber.Ctx) error {
	// Query agent_outputs table for finance alerts
	rows, err := h.db.Query(`
		SELECT 
			id,
			tenant_id,
			output_json->>'vendor_name' as vendor,
			(output_json->>'amount')::float as amount,
			(output_json->>'expected_amount')::float as expected,
			(output_json->>'multiple')::float as multiple,
			urgency,
			headline,
			hitl_sent,
			created_at
		FROM agent_outputs
		WHERE agent_name = 'finance'
			AND output_type = 'anomaly_alert'
		ORDER BY created_at DESC
		LIMIT 10
	`)
	if err != nil {
		// Return empty list on error
		return Render(c, "partials/finance_alerts", fiber.Map{
			"Alerts": []FinanceAlert{},
		})
	}
	defer rows.Close()

	var alerts []FinanceAlert
	for rows.Next() {
		var alert FinanceAlert
		var vendor, headline sql.NullString
		var expected, multiple sql.NullFloat64
		var hitlSent sql.NullBool

		if err := rows.Scan(
			&alert.ID,
			&alert.TenantID,
			&vendor,
			&alert.Amount,
			&expected,
			&multiple,
			&alert.Urgency,
			&headline,
			&hitlSent,
			&alert.CreatedAt,
		); err != nil {
			continue
		}

		if vendor.Valid {
			alert.Vendor = vendor.String
		}
		if expected.Valid {
			alert.Expected = expected.Float64
		}
		if multiple.Valid {
			alert.Multiple = multiple.Float64
		}
		if headline.Valid {
			alert.Headline = headline.String
		}
		if hitlSent.Valid {
			alert.HITLSent = hitlSent.Bool
		}

		alerts = append(alerts, alert)
	}

	return Render(c, "partials/finance_alerts", fiber.Map{
		"Alerts": alerts,
	})
}

// GetRecentBIQueries returns recent BI query results
func (h *Handler) GetRecentBIQueries(c *fiber.Ctx) error {
	// Query agent_outputs for BI query results
	rows, err := h.db.Query(`
		SELECT 
			id,
			tenant_id,
			output_json->>'query' as query,
			output_json->>'result_summary' as result,
			output_json->>'chart_url' as chart_url,
			created_at
		FROM agent_outputs
		WHERE agent_name = 'bi'
			AND output_type = 'query_result'
		ORDER BY created_at DESC
		LIMIT 5
	`)
	if err != nil {
		// Return empty list on error
		return Render(c, "partials/bi_queries", fiber.Map{
			"queries": []BIQueryResult{},
		})
	}
	defer rows.Close()

	var queries []BIQueryResult
	for rows.Next() {
		var query BIQueryResult
		var queryText, result, chartURL sql.NullString

		if err := rows.Scan(
			&query.ID,
			&query.TenantID,
			&queryText,
			&result,
			&chartURL,
			&query.CreatedAt,
		); err != nil {
			continue
		}

		if queryText.Valid {
			query.Query = queryText.String
		}
		if result.Valid {
			query.Result = result.String
		}
		if chartURL.Valid {
			query.ChartURL = chartURL.String
		}

		queries = append(queries, query)
	}

	// Check if this is an HTMX request
	if c.Get("HX-Request") == "true" {
		return Render(c, "partials/bi_queries", fiber.Map{
			"queries": queries,
		})
	}

	return c.JSON(fiber.Map{
		"queries": queries,
	})
}
