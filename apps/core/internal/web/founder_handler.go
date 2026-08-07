package web

import (
	"bufio"
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"iterateswarm-core/internal/logging"
)

// DashboardSummary represents the dashboard data for a founder.
type DashboardSummary struct {
	FounderID             string    `json:"founder_id"`
	Name                  string    `json:"name"`
	Stage                 string    `json:"stage"`
	CommitmentRate        float64   `json:"commitment_rate"`
	OverdueCount          int       `json:"overdue_count"`
	TriggersFired30d      int       `json:"triggers_fired_30d"`
	TriggersSuppressed30d int       `json:"triggers_suppressed_30d"`
	PositiveRatings       int       `json:"positive_ratings"`
	NegativeRatings       int       `json:"negative_ratings"`
	DaysSinceReflection   float64   `json:"days_since_reflection"`
	EnergyTrend           []int     `json:"energy_trend"`
	LastReflectionAt      time.Time `json:"last_reflection_at"`
}

// FounderDashboardHandler handles founder dashboard requests.
type FounderDashboardHandler struct {
	pool   *pgxpool.Pool
	logger *logging.Logger
}

// NewFounderDashboardHandler creates a new FounderDashboardHandler.
func NewFounderDashboardHandler(pool *pgxpool.Pool) *FounderDashboardHandler {
	return &FounderDashboardHandler{
		pool:   pool,
		logger: logging.NewLogger("founder_dashboard"),
	}
}

// FounderDashboard serves the full dashboard page.
func (h *FounderDashboardHandler) FounderDashboard(c *fiber.Ctx) error {
	founderID := c.Locals("founder_id").(string)
	if founderID == "" {
		// Use demo founder for development
		founderID = "00000000-0000-0000-0000-000000000000"
	}

	summary, err := h.getDashboardSummary(c.Context(), founderID)
	if err != nil {
		h.logger.Error("failed to get dashboard summary", err, "founder_id", founderID)
		// Return dashboard with empty state
		summary = &DashboardSummary{
			FounderID:             founderID,
			Name:                  "Founder",
			Stage:                 "building",
			CommitmentRate:        0,
			OverdueCount:          0,
			TriggersFired30d:      0,
			TriggersSuppressed30d: 0,
			PositiveRatings:       0,
			NegativeRatings:       0,
			DaysSinceReflection:   0,
			EnergyTrend:           []int{},
			LastReflectionAt:      time.Now(),
		}
	}

	return Render(c, "founder_dashboard", fiber.Map{
		"Summary": summary,
		"Title":   "Saarathi — Your Patterns",
	})
}

// FounderDashboardPartial serves the HTMX partial for dashboard updates.
func (h *FounderDashboardHandler) FounderDashboardPartial(c *fiber.Ctx) error {
	founderID := c.Locals("founder_id").(string)
	if founderID == "" {
		founderID = "00000000-0000-0000-0000-000000000000"
	}

	summary, err := h.getDashboardSummary(c.Context(), founderID)
	if err != nil {
		h.logger.Error("failed to get dashboard summary for partial", err, "founder_id", founderID)
		return c.Status(500).SendString("Error loading dashboard")
	}

	return Render(c, "partials/founder_dashboard_summary", fiber.Map{
		"Summary": summary,
	})
}

// FounderDashboardStream serves SSE for live dashboard updates.
func (h *FounderDashboardHandler) FounderDashboardStream(c *fiber.Ctx) error {
	founderID := c.Locals("founder_id").(string)
	if founderID == "" {
		founderID = "00000000-0000-0000-0000-000000000000"
	}

	c.Set("Content-Type", "text/event-stream")
	c.Set("Cache-Control", "no-cache")
	c.Set("Connection", "keep-alive")
	c.Set("X-Accel-Buffering", "no")

	ctx := c.Context()
	conn, err := h.pool.Acquire(ctx)
	if err != nil {
		h.logger.Error("failed to acquire database connection", err)
		return c.Status(500).SendString("Failed to connect to database")
	}
	defer conn.Release()

	_, err = conn.Exec(ctx, "LISTEN dashboard_update")
	if err != nil {
		h.logger.Error("failed to LISTEN to dashboard_update channel", err)
		return c.Status(500).SendString("Failed to subscribe to updates")
	}

	// Send initial connection message
	fmt.Fprintf(c.Response().BodyWriter(), "event: connected\ndata: {\"status\":\"connected\"}\n\n")
	if err := c.Response().BodyWriter().(*bufio.Writer).Flush(); err != nil {
		h.logger.Warn("failed to flush initial SSE message", err)
		return nil
	}

	// Listen for notifications
	for {
		notification, err := conn.Conn().WaitForNotification(context.Background())
		if err != nil {
			h.logger.Warn("SSE connection closed", "error", err.Error())
			return nil
		}

		// Parse payload
		var payload struct {
			FounderID string `json:"founder_id"`
		}
		if err := json.Unmarshal([]byte(notification.Payload), &payload); err != nil {
			continue
		}

		// Only send if founder_id matches
		if payload.FounderID != founderID {
			continue
		}

		// Send refresh event
		fmt.Fprintf(c.Response().BodyWriter(), "event: dashboard_update\ndata: {\"type\":\"refresh\"}\n\n")
		if err := c.Response().BodyWriter().(*bufio.Writer).Flush(); err != nil {
			h.logger.Warn("failed to flush SSE message", err)
			return nil
		}
	}
}

// getDashboardSummary retrieves dashboard summary from materialized view.
func (h *FounderDashboardHandler) getDashboardSummary(ctx context.Context, founderID string) (*DashboardSummary, error) {
	// Refresh materialized view first
	_, err := h.pool.Exec(ctx, "SELECT refresh_dashboard_summary()")
	if err != nil {
		h.logger.Warn("failed to refresh dashboard summary", err)
		// Continue anyway - stale data is better than no data
	}

	query := `
		SELECT 
			founder_id,
			name,
			stage,
			COALESCE(commitment_rate, 0),
			COALESCE(overdue_count, 0),
			COALESCE(triggers_fired_30d, 0),
			COALESCE(triggers_suppressed_30d, 0),
			COALESCE(positive_ratings, 0),
			COALESCE(negative_ratings, 0),
			COALESCE(days_since_reflection, 0),
			COALESCE(energy_trend, '{}'),
			COALESCE(last_reflection_at, NOW())
		FROM founder_dashboard_summary
		WHERE founder_id = $1
	`

	row := h.pool.QueryRow(ctx, query, founderID)

	var s DashboardSummary
	err = row.Scan(
		&s.FounderID,
		&s.Name,
		&s.Stage,
		&s.CommitmentRate,
		&s.OverdueCount,
		&s.TriggersFired30d,
		&s.TriggersSuppressed30d,
		&s.PositiveRatings,
		&s.NegativeRatings,
		&s.DaysSinceReflection,
		&s.EnergyTrend,
		&s.LastReflectionAt,
	)
	if err != nil {
		if err == sql.ErrNoRows {
			// Return default summary for new founders
			return &DashboardSummary{
				FounderID:             founderID,
				Name:                  "Founder",
				Stage:                 "building",
				CommitmentRate:        0,
				OverdueCount:          0,
				TriggersFired30d:      0,
				TriggersSuppressed30d: 0,
				PositiveRatings:       0,
				NegativeRatings:       0,
				DaysSinceReflection:   0,
				EnergyTrend:           []int{},
				LastReflectionAt:      time.Now(),
			}, nil
		}
		return nil, err
	}

	return &s, nil
}

// ReflectionHandler handles reflection form submissions.
type ReflectionHandler struct {
	pool     *pgxpool.Pool
	producer EventProducer
	logger   *logging.Logger
}

// EventProducer interface for producing events to Redpanda.
type EventProducer interface {
	ProduceMessage(topic string, message map[string]interface{}) error
}

// NewReflectionHandler creates a new ReflectionHandler.
func NewReflectionHandler(pool *pgxpool.Pool, producer EventProducer) *ReflectionHandler {
	return &ReflectionHandler{
		pool:     pool,
		producer: producer,
		logger:   logging.NewLogger("reflection"),
	}
}

// FounderDashboard serves the founder dashboard page (Handler method)
func (h *Handler) FounderDashboard(c *fiber.Ctx) error {
	return Render(c, "founder_dashboard", fiber.Map{
		"Title": "OntologyAI Workspace — Your Patterns",
	})
}

// SubmitReflection handles POST /founder/reflection.
func (h *ReflectionHandler) SubmitReflection(c *fiber.Ctx) error {
	founderID := c.Locals("founder_id").(string)
	if founderID == "" {
		founderID = "00000000-0000-0000-0000-000000000000"
	}

	// Parse form values
	shipped := c.FormValue("shipped", "")
	blocked := c.FormValue("blocked", "")
	commitments := c.FormValue("commitments", "")
	energyScoreStr := c.FormValue("energy_score", "7")
	energyScore, err := strconv.Atoi(energyScoreStr)
	if err != nil {
		energyScore = 7 // Default value
	}

	// Validate
	if shipped == "" && blocked == "" && commitments == "" {
		return c.Status(400).SendString("At least one field must be filled")
	}

	// Create raw text
	rawText := strings.Join([]string{
		"SHIPPED: " + shipped,
		"BLOCKED: " + blocked,
		"COMMITMENTS: " + commitments,
	}, "\n")

	// Generate IDs
	reflectionID := uuid.New().String()
	weekStart := time.Now().Truncate(7 * 24 * time.Hour)

	// Insert reflection
	_, err = h.pool.Exec(c.Context(), `
		INSERT INTO weekly_reflections
			(id, founder_id, week_start, shipped, blocked, energy_score, raw_text)
		VALUES ($1, $2, $3, $4, $5, $6, $7)
	`, reflectionID, founderID, weekStart, shipped, blocked, energyScore, rawText)
	if err != nil {
		h.logger.Error("failed to save reflection", err, "founder_id", founderID)
		return c.Status(500).SendString("Failed to save reflection")
	}

	// Parse and insert commitments
	commitmentCount := 0
	for _, line := range strings.Split(commitments, "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}

		commitmentID := uuid.New().String()
		_, err := h.pool.Exec(c.Context(), `
			INSERT INTO commitments
				(id, founder_id, reflection_id, description, due_date)
			VALUES ($1, $2, $3, $4, NOW() + INTERVAL '7 days')
		`, commitmentID, founderID, reflectionID, line)
		if err != nil {
			h.logger.Warn("failed to save commitment", err, "line", line)
			continue
		}
		commitmentCount++
	}

	h.logger.Info("reflection saved",
		"founder_id", founderID,
		"reflection_id", reflectionID,
		"commitments_count", commitmentCount,
	)

	// Produce event to Redpanda
	if h.producer != nil {
		err = h.producer.ProduceMessage("founder.signals", map[string]interface{}{
			"type":          "weekly_reflection",
			"founder_id":    founderID,
			"reflection_id": reflectionID,
			"raw_text":      rawText,
			"energy_score":  energyScore,
		})
		if err != nil {
			h.logger.Warn("failed to produce reflection event", err)
		}
	}

	// Return response based on request type
	if c.Get("HX-Request") == "true" {
		return c.SendString(`✅ Reflection saved. Saarathi is watching.`)
	}

	return c.Redirect("/founder/dashboard")
}
