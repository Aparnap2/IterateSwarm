package web

import (
	"context"
	"database/sql"

	"github.com/gofiber/fiber/v2"
)

// APICommandTimeline returns timeline events — delegates to h.timeline provider.
func (h *Handler) APICommandTimeline(c *fiber.Ctx) error {
	if c.Get("HX-Request") != "true" {
		return c.SendString("Timeline")
	}

	tenantID := c.Query("tenant_id", "default")
	days := 7
	allEvents, err := h.timeline.GetEvents(context.Background(), tenantID, days)
	if err != nil {
		allEvents = []map[string]interface{}{}
	}

	events := make([]fiber.Map, 0, len(allEvents))
	for _, e := range allEvents {
		events = append(events, fiber.Map{
			"Time":        e["Time"],
			"Title":       e["Title"],
			"Description": e["Description"],
		})
	}

	return Render(c, "partials/command_timeline", fiber.Map{"Events": events})
}

// APICommandAlertLineage returns alert lineage data — delegates to h.alertLineage provider.
func (h *Handler) APICommandAlertLineage(c *fiber.Ctx) error {
	if c.Get("HX-Request") != "true" {
		return c.SendString("Alert Lineage")
	}

	tenantID := c.Query("tenant_id", "default")
	alertID := c.Query("alert_id", "all")
	lineage, err := h.alertLineage.GetLineage(context.Background(), tenantID, alertID)
	if err != nil {
		lineage = []map[string]interface{}{}
	}

	alerts := make([]fiber.Map, 0, len(lineage))
	for _, l := range lineage {
		rawActions, _ := l["SuggestedActions"].([]map[string]interface{})
		fiberActions := make([]fiber.Map, 0, len(rawActions))
		for _, a := range rawActions {
			label, _ := a["Label"].(string)
			tier, _ := a["Tier"].(string)
			fiberActions = append(fiberActions, fiber.Map{
				"Label": label,
				"Tier":  tier,
			})
		}
		alerts = append(alerts, fiber.Map{
			"PatternName":       l["PatternName"],
			"SourceMetrics":     l["SourceMetrics"],
			"MissionContext":    l["MissionContext"],
			"RaiseTimelineRisk": l["RaiseTimelineRisk"],
			"SuggestedActions":  fiberActions,
		})
	}

	return Render(c, "partials/command_alert_lineage", fiber.Map{"Alerts": alerts})
}

// APICommandOperatingLayer returns the operating layer panel from mission_state
func (h *Handler) APICommandOperatingLayer(c *fiber.Ctx) error {
	if c.Get("HX-Request") != "true" {
		return c.SendString("Operating Layer")
	}

	preparedBrief := ""
	lastWriter := ""
	lastUpdateReason := ""
	pendingDecisions := ""
	activeRoles := ""

	if h.db != nil {
		var brief, writer, reason, decisions, roles sql.NullString
		err := h.db.QueryRow(`
			SELECT
				prepared_brief,
				last_updated_by,
				last_update_reason,
				pending_decisions::text,
				active_agent_roles::text
			FROM mission_state
			ORDER BY updated_at DESC
			LIMIT 1
		`).Scan(&brief, &writer, &reason, &decisions, &roles)
		if err == nil {
			if brief.Valid {
				preparedBrief = brief.String
			}
			if writer.Valid {
				lastWriter = writer.String
			}
			if reason.Valid {
				lastUpdateReason = reason.String
			}
			if decisions.Valid {
				pendingDecisions = decisions.String
			}
			if roles.Valid {
				activeRoles = roles.String
			}
		}
	}

	return Render(c, "partials/command_operating_layer", fiber.Map{
		"PreparedBrief":    preparedBrief,
		"LastWriter":       lastWriter,
		"LastUpdateReason": lastUpdateReason,
		"PendingDecisions": pendingDecisions,
		"ActiveAgentRoles": activeRoles,
	})
}
