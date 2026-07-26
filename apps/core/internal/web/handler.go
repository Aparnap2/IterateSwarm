package web

import (
	"database/sql"
	"embed"
	"fmt"
	"html/template"
	"strings"
	"sync"
	"time"

	"github.com/gofiber/fiber/v2"

	"iterateswarm-core/internal/temporal"
)

//go:embed templates
var templatesFS embed.FS

// Render renders a template with data
func Render(c *fiber.Ctx, name string, data interface{}) error {
	tmpl := template.New(name).Funcs(template.FuncMap{
		"upper": strings.ToUpper,
		"sub": func(a, b int) int {
			return a - b
		},
		"first": func(s string) string {
			if len(s) > 0 {
				return string(s[0])
			}
			return ""
		},
		"displayName": func(sender string) string {
			switch sender {
			case "founder":
				return "You"
			case "sarthi", "agent", "chief_of_staff", "chief":
				return "Workspace Guide"
			case "discover", "discovery":
				return "Discovery"
			case "map", "ontology_mapper":
				return "Business Map"
			case "truth", "knowledge_validator":
				return "Operational Truth"
			case "build", "solution_architect":
				return "Pilot Builder"
			case "govern", "governance":
				return "Approvals & Safety"
			case "all":
				return "Everyone"
			default:
				return strings.Title(sender)
			}
		},
	})
	content, err := templatesFS.ReadFile("templates/" + name + ".html")
	if err != nil {
		return fmt.Errorf("failed to read template %s: %w", name, err)
	}
	tmpl, err = tmpl.Parse(string(content))
	if err != nil {
		return fmt.Errorf("failed to parse template %s: %w", name, err)
	}

	c.Set("Content-Type", "text/html")
	return tmpl.Execute(c.Response().BodyWriter(), data)
}

// Handler struct for web routes
type Handler struct {
	db            *sql.DB
	chatBroadcast chan fiber.Map
	temporal      *temporal.Client
	wg            sync.WaitGroup
	sseHub        *SSEHub
	creds         *CredentialStore

	// Data providers (default implementations used when a field is nil)
	timeline     TimelineProvider
	metrics      MetricsProvider
	chartData    ChartDataProvider
	alertLineage AlertLineageProvider
	taskBoard    TaskBoardProvider
}

// NewHandler creates a new web handler.
// providerBundles is optional; if provided, the first non-nil bundle is used to
// inject custom providers. Any nil provider field falls back to DefaultProviders,
// preserving backward compatibility with existing callers.
func NewHandler(db *sql.DB, temporalClient *temporal.Client, providerBundles ...*ProviderBundle) *Handler {
	if db != nil {
		db.Exec(`CREATE TABLE IF NOT EXISTS chat_messages (
			id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
			tenant_id VARCHAR(100) DEFAULT 'default',
			sender VARCHAR(50) NOT NULL DEFAULT 'founder',
			mention VARCHAR(50),
			message TEXT NOT NULL,
			created_at TIMESTAMP DEFAULT NOW()
		)`)
		db.Exec(`CREATE INDEX IF NOT EXISTS idx_chat_messages_created ON chat_messages(created_at DESC)`)

		db.Exec(`CREATE TABLE IF NOT EXISTS app_config (
			id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
			tenant_id VARCHAR(100) DEFAULT 'default',
			config_key VARCHAR(100) UNIQUE NOT NULL,
			config_value JSONB NOT NULL DEFAULT '{}',
			updated_at TIMESTAMP DEFAULT NOW()
		)`)
	}

	h := &Handler{
		db:            db,
		chatBroadcast: make(chan fiber.Map, 100),
		temporal:      temporalClient,
		sseHub:        NewSSEHub(),
		creds:         NewCredentialStore(),
	}

	// Wire providers — use DefaultProviders as fallback for any nil field
	defaults := DefaultProviders{}
	h.timeline = defaults
	h.metrics = defaults
	h.chartData = defaults
	h.alertLineage = defaults
	h.taskBoard = defaults

	if len(providerBundles) > 0 && providerBundles[0] != nil {
		pb := providerBundles[0]
		if pb.Timeline != nil {
			h.timeline = pb.Timeline
		}
		if pb.Metrics != nil {
			h.metrics = pb.Metrics
		}
		if pb.ChartData != nil {
			h.chartData = pb.ChartData
		}
		if pb.AlertLineage != nil {
			h.alertLineage = pb.AlertLineage
		}
		if pb.TaskBoard != nil {
			h.taskBoard = pb.TaskBoard
		}
	}

	return h
}

// RegisterRoutes registers all web routes
func (h *Handler) RegisterRoutes(app *fiber.App) {
	// Main dashboard
	app.Get("/", h.Dashboard)
	app.Get("/dashboard", h.Dashboard)

	// Founder routes
	app.Get("/founder/dashboard", h.FounderDashboard)

	// API endpoints for HTMX
	app.Post("/api/feedback", h.HandleFeedback)
	app.Get("/api/stats", h.HandleStats)
	app.Get("/api/metrics", h.HandleMetrics)

	// Panel 1: Live Feed
	app.Get("/api/live-feed", h.GetLiveFeed)

	// Panel 2: HITL Queue
	app.Get("/api/approvals/pending", h.GetPendingApprovals)
	app.Post("/api/approvals/:id/approve", h.ApprovePR)
	app.Post("/api/approvals/:id/reject", h.RejectPR)

	// Panel 3: Agent Map
	app.Get("/api/agent-map", h.GetAgentMap)
	app.Get("/api/agents/status", h.GetAllAgentsStatus)
	app.Get("/api/agents/:agent/status", h.GetAgentStatus)

	// Panel 4: Task Board
	app.Get("/api/tasks/board", h.GetTaskBoard)
	app.Get("/api/tasks/queued", h.GetQueuedTasks)
	app.Get("/api/tasks/analyzing", h.GetAnalyzingTasks)
	app.Get("/api/tasks/awaiting-hitl", h.GetAwaitingHITLTasks)
	app.Get("/api/tasks/completed", h.GetCompletedTasks)
	app.Get("/api/tasks/:id/details", h.GetTaskDetails)

	// Panel 5: Config Panel
	app.Get("/api/config", h.GetConfig)
	app.Get("/api/config/panel", h.GetConfigPanel)
	app.Post("/api/config/save", h.SaveConfig)
	app.Get("/api/config/reset", h.ResetConfig)

	// Panel 6: Telemetry Panel
	app.Get("/api/telemetry/panel", h.GetTelemetryPanel)
	app.Get("/api/telemetry/overview", h.GetTelemetryOverview)
	app.Get("/api/telemetry/signoz", h.GetSigNozData)
	app.Get("/api/telemetry/hyperdx", h.GetHyperDXData)
	app.Get("/api/telemetry/metrics", h.GetMetricsData)
	app.Get("/api/telemetry/logs", h.GetLogsData)

	// OntologyAI Enhancements
	app.Get("/api/finance/alerts", h.GetFinanceAlerts)
	app.Get("/api/bi/recent", h.GetRecentBIQueries)

	// V4.1 Mission State API (machine-readable JSON for Python/integrations)
	app.Get("/api/mission-state", h.APIMissionState)
	app.Post("/api/mission-state", h.APIMissionStatePost)

	// ── Command Center Routes ──────────────────────────────
	app.Get("/command", h.CommandCenter)
	app.Get("/api/command/status", h.APICommandStatus)
	app.Get("/api/command/kpis", h.APICommandKPIs)
	app.Get("/api/command/mission-state", h.APICommandMissionState)
	app.Post("/api/command/mission-state/update", h.APICommandMissionStateUpdate)
	app.Get("/api/command/watchlist", h.APICommandWatchlist)
	app.Get("/api/command/agent-fleet", h.APICommandAgentFleet)
	app.Get("/api/command/timeline", h.APICommandTimeline)
	app.Get("/api/command/approvals", h.APICommandApprovals)
	app.Post("/api/command/approvals/:id/:action", h.APICommandApprovalAction)
	app.Get("/api/command/metrics", h.APICommandMetrics)
	app.Get("/api/command/chart-data", h.APICommandChartData)
	app.Get("/api/command/alert-lineage", h.APICommandAlertLineage)
	app.Get("/api/command/operating-layer", h.APICommandOperatingLayer)
	app.Get("/api/command/control-plane-status", h.APICommandControlPlaneStatus)
	app.Get("/api/command/self-guardian-status", h.APICommandSelfGuardianStatus)
	app.Get("/api/command/risk-status", h.APICommandRiskStatus)
	app.Post("/api/command/chat/send", h.APICommandChatSend)
	app.Get("/api/command/chat/events", h.APICommandChatEvents)
	app.Get("/events/mission", h.APICommandMissionEvents)
	app.Get("/events/hitl", h.APICommandHITLEvents)
	app.Get("/events/session", h.APICommandSessionEvents)
	app.Get("/api/command/stream", h.APICommandEvents)
	app.Get("/api/command/events", h.APICommandEvents)
	app.Get("/api/command/revenue/events", h.APICommandRevenueEvents)

	// Chat panel partial — loads the chat HTML with HTMX SSE extension
	// ── V5.2 Workspace Routes (gated by workspace_mode) ──
	h.RegisterWorkspaceRoutes(app)

	app.Get("/api/command/chat", func(c *fiber.Ctx) error {
		type ChatMsg struct {
			Sender      string
			Text        string
			Time        string
			DisplayName string
			Initial     string
			AgentClass  string
		}

		messages := []ChatMsg{}
		if h.db != nil {
			rows, err := h.db.Query(`SELECT sender, mention, message, created_at FROM chat_messages ORDER BY created_at DESC LIMIT 50`)
			if err == nil {
				defer rows.Close()
				for rows.Next() {
					var sender, message string
					var mention sql.NullString
					var createdAt time.Time
					if err := rows.Scan(&sender, &mention, &message, &createdAt); err != nil {
						continue
					}

					// Compute display fields matching renderChatBubble
					displayName := sender
					switch sender {
					case "founder":
						displayName = "You"
					case "sarthi", "agent", "chief_of_staff", "chief":
						displayName = "Workspace Guide"
					case "discover", "discovery":
						displayName = "Discovery"
					case "map", "ontology_mapper":
						displayName = "Business Map"
					case "truth", "knowledge_validator":
						displayName = "Operational Truth"
					case "build", "solution_architect":
						displayName = "Pilot Builder"
					case "govern", "governance":
						displayName = "Approvals & Safety"
					case "finance", "fpa":
						displayName = "FP&A"
					case "data", "growth":
						displayName = "Growth Analytics"
					case "ops", "reliability":
						displayName = "Reliability & Delivery"
					case "comms":
						displayName = "Communications"
					}

					normalized := strings.TrimPrefix(sender, "@")
					initials := map[string]string{
						"founder": "Y", "sarthi": "W", "chief": "W", "chief_of_staff": "W",
						"discover": "D", "map": "B", "truth": "O", "build": "P", "govern": "A",
						"finance": "F", "fpa": "F", "data": "G", "growth": "G", "ops": "R",
						"reliability": "R", "agent": "A", "comms": "M",
					}
					initial := initials[normalized]
					if initial == "" && len(normalized) > 0 {
						initial = strings.ToUpper(string(normalized[0]))
					}

					agentClasses := map[string]string{
						"founder":        "bg-blue-500/20 text-blue-400",
						"sarthi":         "agent-chief-of-staff",
						"chief":          "agent-chief-of-staff",
						"chief_of_staff": "agent-chief-of-staff",
						"discover":       "agent-discovery",
						"map":            "agent-ontology-mapper",
						"truth":          "agent-truth-analyst",
						"build":          "agent-solution-architect",
						"govern":         "agent-governance",
						"finance":        "agent-fpa",
						"fpa":            "agent-fpa",
						"data":           "agent-growth-analytics",
						"growth":         "agent-growth-analytics",
						"ops":            "agent-reliability",
						"reliability":    "agent-reliability",
						"agent":          "agent-system",
						"comms":          "agent-comms",
					}
					agentClass := agentClasses[normalized]
					if agentClass == "" {
						agentClass = "agent-system"
					}

					messages = append(messages, ChatMsg{
						Sender:      sender,
						Text:        message,
						Time:        createdAt.Format("15:04:05"),
						DisplayName: displayName,
						Initial:     initial,
						AgentClass:  agentClass,
					})
				}
			}
		}

		// Reverse so they display oldest-first
		for i, j := 0, len(messages)-1; i < j; i, j = i+1, j-1 {
			messages[i], messages[j] = messages[j], messages[i]
		}

		return Render(c, "partials/command_chat", fiber.Map{
			"Messages": messages,
		})
	})

	// ── V5.2 Ontology Setup Wizard Routes ────────────────────────────
	h.RegisterOntologySetupRoutes(app)
}
