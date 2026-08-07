package web

import (
	"database/sql"
	"fmt"
	"log"

	"github.com/gofiber/fiber/v2"
)

// APICommandMissionState returns mission state signals from mission_state table
func (h *Handler) APICommandMissionState(c *fiber.Ctx) error {
	if c.Get("HX-Request") != "true" {
		return c.SendString("Mission State")
	}

	signals := []fiber.Map{
		{"Domain": "Finance", "Title": "Burn multiple 1.9x", "Description": "Approaching FG-02 threshold", "DeltaClass": "warn"},
		{"Domain": "BI", "Title": "Cohort -12%", "Description": "BG-04 risk emerging", "DeltaClass": "down"},
		{"Domain": "Ops", "Title": "Error cluster 14%", "Description": "Segment correlation detected", "DeltaClass": "down"},
	}
	healthScore := 72
	riskLevel := "MEDIUM"
	var lastUpdateReason, lastChangedFields, activeRuntimeRoles sql.NullString

	if h.db != nil {
		var trustScore sql.NullInt32
		var burnAlert sql.NullBool
		var burnSev, mrrTrend, activeAlerts, founderFocus sql.NullString
		var churnRate sql.NullFloat64
		var errorSpike sql.NullBool
		var burnMult sql.NullFloat64
		var mrr sql.NullFloat64
		var runwayDays sql.NullInt32

		err := h.db.QueryRow(`
			SELECT
				COALESCE(trust_score, 72),
				COALESCE(burn_alert, false),
				COALESCE(burn_severity, ''),
				COALESCE(mrr_trend, ''),
				COALESCE(churn_rate, 0),
				COALESCE(error_spike, false),
				COALESCE(active_alerts, ''),
				COALESCE(founder_focus, ''),
				COALESCE(burn_multiple, 0),
				COALESCE(mrr, 0),
				COALESCE(runway_days, 0),
				last_update_reason,
				last_changed_fields::text,
				active_agent_roles::text
			FROM mission_state
			ORDER BY updated_at DESC
			LIMIT 1
		`).Scan(&trustScore, &burnAlert, &burnSev, &mrrTrend,
			&churnRate, &errorSpike, &activeAlerts, &founderFocus,
			&burnMult, &mrr, &runwayDays,
			&lastUpdateReason, &lastChangedFields, &activeRuntimeRoles)
		if err == nil {
			if trustScore.Valid {
				healthScore = int(trustScore.Int32)
			}

			// Build signals from mission_state data
			var liveSignals []fiber.Map

			// Finance signal
			if burnAlert.Valid && burnAlert.Bool {
				burnDesc := "Burn alert active"
				if burnMult.Valid && burnMult.Float64 > 0 {
					burnDesc = fmt.Sprintf("Burn multiple %.1fx", burnMult.Float64)
				}
				liveSignals = append(liveSignals, fiber.Map{
					"Domain": "Finance", "Title": "Burn alert",
					"Description": burnDesc, "DeltaClass": "warn",
				})
			} else if mrr.Valid && mrr.Float64 > 0 {
				liveSignals = append(liveSignals, fiber.Map{
					"Domain": "Finance", "Title": fmt.Sprintf("MRR ₹%.2fL", mrr.Float64/100000),
					"Description": fmt.Sprintf("Runway %d days", runwayDays.Int32), "DeltaClass": "warn",
				})
			} else {
				liveSignals = append(liveSignals, signals[0]) // fallback
			}

			// BI/Data signal
			if churnRate.Valid && churnRate.Float64 > 5 {
				liveSignals = append(liveSignals, fiber.Map{
					"Domain": "BI", "Title": fmt.Sprintf("Churn %.1f%%", churnRate.Float64),
					"Description": "Churn rate above threshold", "DeltaClass": "down",
				})
			} else if churnRate.Valid && churnRate.Float64 > 0 {
				liveSignals = append(liveSignals, fiber.Map{
					"Domain": "BI", "Title": fmt.Sprintf("Churn %.1f%%", churnRate.Float64),
					"Description": "Monitoring cohort health", "DeltaClass": "warn",
				})
			} else {
				liveSignals = append(liveSignals, signals[1]) // fallback
			}

			// Ops signal
			if errorSpike.Valid && errorSpike.Bool {
				liveSignals = append(liveSignals, fiber.Map{
					"Domain": "Ops", "Title": "Error spike detected",
					"Description": "Segment correlation detected", "DeltaClass": "down",
				})
			} else if activeAlerts.Valid && activeAlerts.String != "" {
				liveSignals = append(liveSignals, fiber.Map{
					"Domain": "Ops", "Title": activeAlerts.String,
					"Description": "Active alerts from monitoring", "DeltaClass": "warn",
				})
			} else {
				liveSignals = append(liveSignals, signals[2]) // fallback
			}

			signals = liveSignals
		}
	}

	return Render(c, "partials/command_mission_state", fiber.Map{
		"Signals": signals, "HealthScore": healthScore, "RiskLevel": riskLevel,
		"LastUpdateReason": lastUpdateReason.String, "LastChangedFields": lastChangedFields.String,
		"ActiveRuntimeRoles": activeRuntimeRoles.String,
	})
}

// APICommandMissionStateUpdate accepts mission state data via POST and upserts into mission_state table.
// Returns the updated mission state HTML partial for HTMX swap.
func (h *Handler) APICommandMissionStateUpdate(c *fiber.Ctx) error {
	var input struct {
		TenantID        string   `json:"tenant_id"`
		MRR             *float64 `json:"mrr"`
		BurnRate        *float64 `json:"burn_rate"`
		RunwayDays      *int     `json:"runway_days"`
		BurnAlert       *bool    `json:"burn_alert"`
		BurnSeverity    *string  `json:"burn_severity"`
		MRRTrend        *string  `json:"mrr_trend"`
		ChurnRate       *float64 `json:"churn_rate"`
		ErrorSpike      *bool    `json:"error_spike"`
		ActiveAlerts    *string  `json:"active_alerts"`
		FounderFocus    *string  `json:"founder_focus"`
		TrustScore      *int     `json:"trust_score"`
		BurnMultiple    *float64 `json:"burn_multiple"`
		EffectiveRunway *int     `json:"effective_runway_days"`
	}

	if err := c.BodyParser(&input); err != nil {
		log.Printf("Failed to parse mission state update: %v", err)
		return c.Status(400).JSON(fiber.Map{"error": "Invalid JSON"})
	}

	if h.db != nil {
		result, err := h.db.Exec(`
			UPDATE mission_state SET
				mrr = COALESCE($2, mission_state.mrr),
				burn_rate = COALESCE($3, mission_state.burn_rate),
				runway_days = COALESCE($4, mission_state.runway_days),
				burn_alert = COALESCE($5, mission_state.burn_alert),
				burn_severity = COALESCE($6, mission_state.burn_severity),
				mrr_trend = COALESCE($7, mission_state.mrr_trend),
				churn_rate = COALESCE($8, mission_state.churn_rate),
				error_spike = COALESCE($9, mission_state.error_spike),
				active_alerts = COALESCE($10, mission_state.active_alerts),
				founder_focus = COALESCE($11, mission_state.founder_focus),
				trust_score = COALESCE($12, mission_state.trust_score),
				burn_multiple = COALESCE($13, mission_state.burn_multiple),
				effective_runway_days = COALESCE($14, mission_state.effective_runway_days),
				updated_at = NOW()
			WHERE tenant_id = $1
		`, input.TenantID, input.MRR, input.BurnRate, input.RunwayDays,
			input.BurnAlert, input.BurnSeverity, input.MRRTrend, input.ChurnRate,
			input.ErrorSpike, input.ActiveAlerts, input.FounderFocus, input.TrustScore,
			input.BurnMultiple, input.EffectiveRunway)
		if err != nil {
			log.Printf("Failed to update mission state: %v", err)
		} else {
			rows, _ := result.RowsAffected()
			if rows == 0 {
				// No existing row — insert
				_, insertErr := h.db.Exec(`
					INSERT INTO mission_state (
						tenant_id, mrr, burn_rate, runway_days, burn_alert,
						burn_severity, mrr_trend, churn_rate, error_spike,
						active_alerts, founder_focus, trust_score, burn_multiple,
						effective_runway_days
					) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
				`, input.TenantID, input.MRR, input.BurnRate, input.RunwayDays,
					input.BurnAlert, input.BurnSeverity, input.MRRTrend, input.ChurnRate,
					input.ErrorSpike, input.ActiveAlerts, input.FounderFocus, input.TrustScore,
					input.BurnMultiple, input.EffectiveRunway)
				if insertErr != nil {
					log.Printf("Failed to insert mission state: %v", insertErr)
				}
			}
		}
	}

	return h.APICommandMissionState(c)
}

// APICommandWatchlist returns watchlist items
func (h *Handler) APICommandWatchlist(c *fiber.Ctx) error {
	if c.Get("HX-Request") != "true" {
		return c.SendString("Watchlist")
	}
	items := []fiber.Map{
		{"Title": "FG-04 Runway Compression", "Description": "Burn acceleration is reducing fundraising slack earlier than plan.", "Severity": "high"},
		{"Title": "BG-04 Cohort Degradation", "Description": "New cohorts retain materially worse than prior cohorts.", "Severity": "med"},
		{"Title": "OG-02 Support Outpacing Growth", "Description": "Support growth is rising faster than active user growth.", "Severity": "med"},
		{"Title": "OG-01 Error Segment Correlation", "Description": "A concentrated error cluster is affecting one customer segment.", "Severity": "low"},
	}
	return Render(c, "partials/command_watchlist", fiber.Map{"Items": items})
}

// APICommandAgentFleet returns agent fleet inline HTML
func (h *Handler) APICommandAgentFleet(c *fiber.Ctx) error {
	if c.Get("HX-Request") != "true" {
		return c.SendString("Agent Fleet")
	}
	html := `<div class="flex justify-between items-center mb-4">
        <div><h3 class="text-lg font-bold">Agent fleet</h3><p class="text-sm" style="color:var(--muted)">Specialists act separately, co-founder synthesizes.</p></div>
    </div>
    <div class="grid grid-cols-4 gap-3">
        <div class="p-4 rounded-2xl" style="background:rgba(255,255,255,.025);border:1px solid rgba(255,255,255,.05)">
            <div class="flex items-center gap-3 mb-2">
                <div class="w-10 h-10 rounded-xl grid place-items-center font-bold text-sm" style="background:rgba(125,211,252,.15);color:#bae6fd">C</div>
                <div><h4 class="font-semibold">Workspace Guide</h4><p class="text-xs" style="color:var(--muted)">Manager · synthesis</p></div>
            </div>
            <ul class="text-xs space-y-1" style="color:var(--muted)"><li>Routes questions</li><li>Resolves conflicts</li><li>Queues approvals</li></ul>
        </div>
        <div class="p-4 rounded-2xl" style="background:rgba(255,255,255,.025);border:1px solid rgba(255,255,255,.05)">
            <div class="flex items-center gap-3 mb-2">
                <div class="w-10 h-10 rounded-xl grid place-items-center font-bold text-sm" style="background:rgba(52,211,153,.15);color:#a7f3d0">F</div>
                <div><h4 class="font-semibold">FP&A</h4><p class="text-xs" style="color:var(--muted)">MRR · burn · runway</p></div>
            </div>
            <ul class="text-xs space-y-1" style="color:var(--muted)"><li>Injects numbers</li><li>Flags concentration</li><li>Drafts financing alerts</li></ul>
        </div>
        <div class="p-4 rounded-2xl" style="background:rgba(255,255,255,.025);border:1px solid rgba(255,255,255,.05)">
            <div class="flex items-center gap-3 mb-2">
                <div class="w-10 h-10 rounded-xl grid place-items-center font-bold text-sm" style="background:rgba(167,139,250,.14);color:#ddd6fe">G</div>
                <div><h4 class="font-semibold">Growth Analytics</h4><p class="text-xs" style="color:var(--muted)">Cohorts · funnel</p></div>
            </div>
            <ul class="text-xs space-y-1" style="color:var(--muted)"><li>Answers metric questions</li><li>Summarizes trends</li><li>Finds activation walls</li></ul>
        </div>
        <div class="p-4 rounded-2xl" style="background:rgba(255,255,255,.025);border:1px solid rgba(255,255,255,.05)">
            <div class="flex items-center gap-3 mb-2">
                <div class="w-10 h-10 rounded-xl grid place-items-center font-bold text-sm" style="background:rgba(245,158,11,.15);color:#fcd34d">R</div>
                <div><h4 class="font-semibold">Reliability & Delivery</h4><p class="text-xs" style="color:var(--muted)">Errors · support</p></div>
            </div>
            <ul class="text-xs space-y-1" style="color:var(--muted)"><li>Detects bug convergence</li><li>Tracks service health</li><li>Correlates incidents</li></ul>
        </div>
    </div>`
	return c.SendString(html)
}

// APICommandSelfGuardianStatus returns the self-guardian monitoring status panel
func (h *Handler) APICommandSelfGuardianStatus(c *fiber.Ctx) error {
	if c.Get("HX-Request") != "true" {
		return c.SendString("Self-Guardian Status")
	}

	type Alert struct {
		Severity      string
		AgentName     string
		DeviationType string
		Description   string
		TimeAgo       string
	}

	alerts := []Alert{}

	if h.db != nil {
		rows, err := h.db.Query(`
			SELECT severity, agent_name, deviation_type, COALESCE(description, ''),
			       EXTRACT(EPOCH FROM NOW() - created_at) AS age_seconds
			FROM self_guardian_alerts
			ORDER BY
				CASE severity
					WHEN 'critical' THEN 0
					WHEN 'warning' THEN 1
					ELSE 2
				END,
				created_at DESC
			LIMIT 20
		`)
		if err == nil {
			defer rows.Close()
			for rows.Next() {
				var a Alert
				var ageSeconds float64
				if err := rows.Scan(&a.Severity, &a.AgentName, &a.DeviationType, &a.Description, &ageSeconds); err != nil {
					continue
				}
				switch {
				case ageSeconds < 60:
					a.TimeAgo = "just now"
				case ageSeconds < 120:
					a.TimeAgo = "1m ago"
				case ageSeconds < 3600:
					a.TimeAgo = fmt.Sprintf("%dm ago", int(ageSeconds/60))
				default:
					a.TimeAgo = fmt.Sprintf("%dh ago", int(ageSeconds/3600))
				}
				alerts = append(alerts, a)
			}
		}
	}

	if alerts == nil {
		alerts = []Alert{}
	}

	// Per-agent health summary
	type AgentHealth struct {
		AgentName    string
		Observations int
		Deviations   int
		StatusClass  string
	}

	agentHealthMap := make(map[string]*AgentHealth)
	healthOrder := []string{}

	if h.db != nil {
		rows, err := h.db.Query(`
			SELECT agent_name,
			       COUNT(*) AS total_obs,
			       SUM(CASE WHEN severity IN ('critical','warning') THEN 1 ELSE 0 END) AS deviations
			FROM self_guardian_alerts
			WHERE created_at > NOW() - INTERVAL '24 hours'
			GROUP BY agent_name
			ORDER BY deviations DESC
		`)
		if err == nil {
			defer rows.Close()
			for rows.Next() {
				var ah AgentHealth
				if err := rows.Scan(&ah.AgentName, &ah.Observations, &ah.Deviations); err != nil {
					continue
				}
				switch {
				case ah.Deviations > 5:
					ah.StatusClass = "disconnected"
				case ah.Deviations > 1:
					ah.StatusClass = "connecting"
				default:
					ah.StatusClass = "connected"
				}
				agentHealthMap[ah.AgentName] = &ah
				healthOrder = append(healthOrder, ah.AgentName)
			}
		}
	}

	agentHealth := []AgentHealth{}
	for _, name := range healthOrder {
		if h, ok := agentHealthMap[name]; ok {
			agentHealth = append(agentHealth, *h)
		}
	}

	if agentHealth == nil {
		agentHealth = []AgentHealth{}
	}

	return Render(c, "partials/command_self_guardian_status", fiber.Map{
		"Alerts":      alerts,
		"AgentHealth": agentHealth,
	})
}
