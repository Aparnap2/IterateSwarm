package web

import (
	"database/sql"
	"fmt"
	"time"

	"github.com/gofiber/fiber/v2"
)

// APICommandStatus returns the status bar with live health metrics from mission_state
func (h *Handler) APICommandStatus(c *fiber.Ctx) error {
	if c.Get("HX-Request") != "true" {
		return c.SendString("Command Status")
	}
	health := 72
	riskLevel := "MEDIUM"
	blindspots := 5
	approvals := 3
	lastSync := time.Now().Format("15:04:05")

	if h.db != nil {
		var hScore sql.NullInt32
		var rLevel sql.NullString
		var bSpots, appCount sql.NullInt32
		err := h.db.QueryRow(`
			SELECT
				COALESCE(trust_score, 72),
				CASE
					WHEN burn_alert = true THEN 'HIGH'
					WHEN COALESCE(burn_severity, '') != '' THEN UPPER(burn_severity)
					ELSE 'MEDIUM'
				END,
				(SELECT COUNT(*) FROM mission_state WHERE COALESCE(burn_alert, false)),
				(SELECT COUNT(*) FROM planned_actions WHERE status = 'planned')
			FROM mission_state
			ORDER BY updated_at DESC
			LIMIT 1
		`).Scan(&hScore, &rLevel, &bSpots, &appCount)
		if err == nil {
			if hScore.Valid {
				health = int(hScore.Int32)
			}
			if rLevel.Valid {
				riskLevel = rLevel.String
			}
			if bSpots.Valid {
				blindspots = int(bSpots.Int32)
			}
			if appCount.Valid {
				approvals = int(appCount.Int32)
			}
		}
	}

	return Render(c, "partials/command_status_bar", fiber.Map{
		"Health": health, "RiskLevel": riskLevel,
		"Blindspots": blindspots, "Approvals": approvals, "LastSync": lastSync,
	})
}

// APICommandKPIs returns command center KPI cards from mission_state
func (h *Handler) APICommandKPIs(c *fiber.Ctx) error {
	if c.Get("HX-Request") != "true" {
		return c.SendString("Command KPIs")
	}

	kpis := []fiber.Map{
		{"Label": "MRR", "Value": "₹4.82L", "Delta": "+8.4% vs last month", "Trend": "up"},
		{"Label": "Runway", "Value": "7.8 mo", "Delta": "-0.6 months compression", "Trend": "warn"},
		{"Label": "Activation", "Value": "41%", "Delta": "Funnel wall at onboarding step 3", "Trend": "warn"},
		{"Label": "Support Load", "Value": "128", "Delta": "+22% week over week", "Trend": "down"},
	}

	if h.db != nil {
		var mrr, burnRate sql.NullFloat64
		var runwayDays, trustScore sql.NullInt32
		err := h.db.QueryRow(`
			SELECT
				COALESCE(mrr, 0),
				COALESCE(burn_rate, 0),
				COALESCE(runway_days, 0),
				COALESCE(trust_score, 0)
			FROM mission_state
			ORDER BY updated_at DESC
			LIMIT 1
		`).Scan(&mrr, &burnRate, &runwayDays, &trustScore)
		if err == nil {
			if mrr.Valid && mrr.Float64 > 0 {
				lakhs := mrr.Float64 / 100000.0
				mrrVal := fmt.Sprintf("\u20b9%.2fL", lakhs)
				kpis[0] = fiber.Map{"Label": "MRR", "Value": mrrVal, "Delta": "From mission_state", "Trend": "up"}
			}
			if runwayDays.Valid && runwayDays.Int32 > 0 {
				months := float64(runwayDays.Int32) / 30.0
				runwayVal := fmt.Sprintf("%.1f mo", months)
				kpis[1] = fiber.Map{"Label": "Runway", "Value": runwayVal, "Delta": "From mission_state", "Trend": "warn"}
			}
			if trustScore.Valid && trustScore.Int32 > 0 {
				kpis[2] = fiber.Map{"Label": "Trust Score", "Value": fmt.Sprintf("%d%%", trustScore.Int32), "Delta": "From mission_state", "Trend": "warn"}
			}
			if burnRate.Valid && burnRate.Float64 > 0 {
				kpis[3] = fiber.Map{"Label": "Burn Rate", "Value": fmt.Sprintf("\u20b9%.1fK", burnRate.Float64/1000), "Delta": "From mission_state", "Trend": "down"}
			}
		}
	}

	return Render(c, "partials/command_kpis", fiber.Map{"KPIs": kpis})
}

// APICommandMetrics returns system metrics for the command center
func (h *Handler) APICommandMetrics(c *fiber.Ctx) error {
	if c.Get("HX-Request") != "true" {
		return c.SendString("Metrics")
	}
	metrics := []fiber.Map{
		{"Label": "Average agent response", "Value": "1.8s", "Pill": "GOOD"},
		{"Label": "Approval turnaround", "Value": "6m 12s", "Pill": "OK"},
		{"Label": "False alert rate", "Value": "4.2%", "Pill": "LOW"},
		{"Label": "Context budget", "Value": "612 / 800 tokens", "Pill": "SAFE"},
	}
	return Render(c, "partials/command_metrics", fiber.Map{"Metrics": metrics})
}

// APICommandChartData returns chart data as JSON
func (h *Handler) APICommandChartData(c *fiber.Ctx) error {
	return c.JSON(fiber.Map{
		"labels": []string{"W1", "W2", "W3", "W4", "W5", "W6"},
		"datasets": []fiber.Map{
			{"label": "Mission Health", "data": []int{84, 82, 80, 79, 75, 72}, "borderColor": "#7dd3fc", "backgroundColor": "rgba(125,211,252,.12)", "fill": true, "tension": 0.34},
			{"label": "Risk Index", "data": []int{26, 29, 35, 38, 45, 52}, "borderColor": "#f59e0b", "backgroundColor": "rgba(245,158,11,.06)", "fill": false, "tension": 0.34},
			{"label": "Execution Drag", "data": []int{18, 22, 24, 29, 34, 39}, "borderColor": "#a78bfa", "backgroundColor": "rgba(167,139,250,.06)", "fill": false, "tension": 0.34},
		},
	})
}

// Dashboard handler - serves the main HTMX dashboard
func (h *Handler) Dashboard(c *fiber.Ctx) error {
	return Render(c, "dashboard", fiber.Map{
		"Title": "IterateSwarm Admin Dashboard",
	})
}
