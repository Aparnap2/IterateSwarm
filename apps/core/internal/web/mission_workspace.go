package web

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"html/template"
	"strings"
	"sync"
	"time"

	"github.com/gofiber/fiber/v2"
)

// ── Milestone 1.5 — Adaptive Workspace Integration ─────────────────────────
//
// The Mission Orchestrator drives a living, real-time operational workspace.
// This file is the Go-side adapter that:
//
//   - mirrors the Python MissionCoordinator.mission_card() dict as MissionCard;
//   - keeps a deterministic, in-memory MissionStore (ready to be wired to real
//     Python mission events later);
//   - maps a semantic Python event type → an SSE event name + HTMX partial;
//   - broadcasts named SSE events over the existing SSEHub (reused as-is);
//   - serves the Mission Dashboard + Mission Detail HTMX partials.
//
// The product loop completed here:
//
//	Mission Events → SSE Hub (Go) → Workspace Schema fragment → HTMX partial swap

// MissionCard mirrors the Python MissionCoordinator.mission_card() dict.
type MissionCard struct {
	MissionID      string  `json:"mission_id"`
	Name           string  `json:"name"`
	Owner          string  `json:"owner"`
	Status         string  `json:"status"`
	Confidence     float64 `json:"confidence"`
	EvidenceCount  int     `json:"evidence_count"`
	Priority       string  `json:"priority"`
	Worker         string  `json:"worker"`
	Directive      string  `json:"directive"`
	LastObservedAt string  `json:"last_observed_at"`
	NextReviewAt   string  `json:"next_review_at"`
	Epoch          int     `json:"epoch"`
	Planned        bool    `json:"planned"`
}

// MissionTimelineEntry is a single semantic event on a mission's timeline.
type MissionTimelineEntry struct {
	ID        string `json:"id"`
	MissionID string `json:"mission_id"`
	EventType string `json:"event_type"`
	SSEEvent  string `json:"sse_event"`
	Partial   string `json:"partial"`
	Summary   string `json:"summary"`
	At        string `json:"at"`
}

// MissionStore is an in-memory, deterministic store of live mission cards plus
// a timeline of semantic events. It is the Go-side mirror of the Python
// MissionCoordinator and is thread-safe for concurrent SSE fan-out.
type MissionStore struct {
	mu       sync.RWMutex
	missions map[string]MissionCard
	timeline []MissionTimelineEntry
	seq      int
}

// NewMissionStore creates a store seeded with a deterministic demo fleet so the
// workspace is alive on first load (and later wired to real Python events).
func NewMissionStore() *MissionStore {
	s := &MissionStore{missions: make(map[string]MissionCard)}
	now := time.Now().UTC()
	for i, c := range demo {
		c.LastObservedAt = now.Add(-time.Duration(i*7) * time.Minute).Format(time.RFC3339)
		s.missions[c.MissionID] = c
	}
	// Seed a small timeline so the detail view is alive on first load.
	s.AddTimeline(MissionTimelineEntry{
		MissionID: "m-1", EventType: "mission_created", SSEEvent: "mission-card-m-1",
		Partial: "mission_card", Summary: "Monitoring plan active for Revenue Health",
		At: now.Add(-6 * time.Minute).Format(time.RFC3339),
	})
	s.AddTimeline(MissionTimelineEntry{
		MissionID: "m-1", EventType: "new_evidence", SSEEvent: "evidence-m-1",
		Partial: "mission_evidence", Summary: "New evidence applied to Revenue Health",
		At: now.Add(-4 * time.Minute).Format(time.RFC3339),
	})
	s.AddTimeline(MissionTimelineEntry{
		MissionID: "m-2", EventType: "mission_created", SSEEvent: "mission-card-m-2",
		Partial: "mission_card", Summary: "Investigation started for Customer Health",
		At: now.Add(-9 * time.Minute).Format(time.RFC3339),
	})
	s.AddTimeline(MissionTimelineEntry{
		MissionID: "m-2", EventType: "new_recommendation", SSEEvent: "recommendation-m-2",
		Partial: "mission_recommendation", Summary: "Recommendation ready for review",
		At: now.Add(-2 * time.Minute).Format(time.RFC3339),
	})
	return s
}

// demo is the deterministic seed fleet (kept as a package var for tests).
var demo = []MissionCard{
	{
		MissionID: "m-1", Name: "Revenue Health", Owner: "ceo@finp.io",
		Status: "monitoring", Worker: "revops-analyst", Confidence: 0.8,
		EvidenceCount: 12, Priority: "high", Directive: "Protect MRR",
		Epoch: 1, Planned: true,
	},
	{
		MissionID: "m-2", Name: "Customer Health", Owner: "cso@finp.io",
		Status: "investigating", Worker: "growth-analyst", Confidence: 0.61,
		EvidenceCount: 8, Priority: "high", Directive: "Cohort retention",
		Epoch: 2, Planned: false,
	},
	{
		MissionID: "m-3", Name: "Roadmap Delivery", Owner: "cto@finp.io",
		Status: "awaiting_approval", Worker: "ops-analyst", Confidence: 0.74,
		EvidenceCount: 5, Priority: "high", Directive: "Ship Q2 scope",
		Epoch: 1, Planned: true,
	},
	{
		MissionID: "m-4", Name: "Financing Runway", Owner: "cfo@finp.io",
		Status: "executing", Worker: "fpa-analyst", Confidence: 0.9,
		EvidenceCount: 6, Priority: "critical", Directive: "Extend runway",
		Epoch: 3, Planned: true,
	},
}

// Upsert stores (or replaces) a mission card.
func (s *MissionStore) Upsert(c MissionCard) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.missions[c.MissionID] = c
}

// Get returns a mission card by id.
func (s *MissionStore) Get(id string) (MissionCard, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	c, ok := s.missions[id]
	return c, ok
}

// List returns all mission cards, newest first.
func (s *MissionStore) List() []MissionCard {
	s.mu.RLock()
	defer s.mu.RUnlock()
	out := make([]MissionCard, 0, len(s.missions))
	for _, c := range s.missions {
		out = append(out, c)
	}
	return out
}

// AddTimeline appends a semantic timeline entry and returns it.
func (s *MissionStore) AddTimeline(e MissionTimelineEntry) MissionTimelineEntry {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.seq++
	e.ID = fmt.Sprintf("ev-%d", s.seq)
	s.timeline = append(s.timeline, e)
	return e
}

// Timeline returns the timeline entries for a mission (or all if id is empty).
func (s *MissionStore) Timeline(id string) []MissionTimelineEntry {
	s.mu.RLock()
	defer s.mu.RUnlock()
	var out []MissionTimelineEntry
	for _, e := range s.timeline {
		if id == "" || e.MissionID == id {
			out = append(out, e)
		}
	}
	return out
}

// ── Semantic event → SSE event + HTMX partial mapping ──────────────────────
//
// The Workspace decides which component to update from the event type. Each
// semantic event maps to a base SSE event name and the HTMX partial that
// renders the affected component. The broadcast appends the mission id so only
// the affected mission's component swaps (granular, no full-page refresh).

// MissionEventToSSE maps a Python semantic event type to (baseSSEEvent, partial).
func MissionEventToSSE(eventType string) (string, string) {
	switch eventType {
	case "mission_created":
		return "mission-card", "mission_card"
	case "mission_status_changed":
		return "mission-card", "mission_card"
	case "mission_confidence_changed":
		return "confidence", "mission_confidence"
	case "new_evidence":
		return "evidence", "mission_evidence"
	case "mission_replanned":
		return "mission-card", "mission_card"
	case "new_recommendation":
		return "recommendation", "mission_recommendation"
	case "evaluation_recorded":
		return "mission-card", "mission_card"
	case "mission_completed":
		return "mission-card", "mission_card"
	case "mission_paused":
		return "mission-card", "mission_card"
	case "mission_retried":
		return "mission-card", "mission_card"
	case "mission_escalated":
		return "mission-card", "mission_card"
	case "mission_failed":
		return "mission-card", "mission_card"
	case "mission_interrupted":
		return "mission-card", "mission_card"
	case "review_completed":
		return "mission-card", "mission_card"
	default:
		return "mission-card", "mission_card"
	}
}

// missionSSEEventName builds the per-mission SSE event name, e.g.
// "mission-card-m-1" or "confidence-m-2".
func missionSSEEventName(base, missionID string) string {
	return base + "-" + missionID
}

// renderPartialToString renders an embedded HTMX partial to a string so it can
// be broadcast as an SSE payload (HTMX sse-swap renders it directly).
func renderPartialToString(name string, data interface{}) (string, error) {
	content, err := templatesFS.ReadFile("templates/" + name + ".html")
	if err != nil {
		return "", err
	}
	tmpl, err := template.New(name).Funcs(missionTemplateFuncs).Parse(string(content))
	if err != nil {
		return "", err
	}
	var buf bytes.Buffer
	if err := tmpl.Execute(&buf, data); err != nil {
		return "", err
	}
	return buf.String(), nil
}

// missionTemplateFuncs are the template helpers shared by the mission partials
// (also merged into the global Render funcs map so detail views can use them).
var missionTemplateFuncs = template.FuncMap{
	"statusLabel": missionStatusLabel,
	"statusClass": missionStatusClass,
	"statusPill":  missionStatusPill,
	"pct":         missionPct,
	"timeAgo":     missionTimeAgo,
	"workerLabel": missionWorkerLabel,
	"sequence":    missionSequence,
	"shortTime":   missionShortTime,
}

// missionSequence returns [1..n] capped at 12, for rendering evidence dots.
func missionSequence(n int) []int {
	if n < 0 {
		n = 0
	}
	if n > 12 {
		n = 12
	}
	out := make([]int, n)
	for i := range out {
		out[i] = i + 1
	}
	return out
}

// missionShortTime renders an RFC3339 timestamp as HH:MM (UTC/local display).
func missionShortTime(ts string) string {
	if ts == "" {
		return ""
	}
	t, err := time.Parse(time.RFC3339, ts)
	if err != nil {
		return ts
	}
	return t.Format("15:04")
}

// missionWorkerLabel maps a worker id to the small "Handled by …" secondary
// label used on mission cards (operational status stays the primary copy).
func missionWorkerLabel(worker string) string {
	switch worker {
	case "revops-analyst":
		return "RevOps Analyst"
	case "growth-analyst":
		return "Growth Analyst"
	case "ops-analyst":
		return "Ops Analyst"
	case "fpa-analyst":
		return "FP&A Analyst"
	default:
		return strings.Title(strings.ReplaceAll(worker, "-", " "))
	}
}

// missionStatusLabel maps a mission phase to a CEO-facing operational status.
func missionStatusLabel(status string) string {
	switch status {
	case "investigating":
		return "Investigating…"
	case "monitoring":
		return "Monitoring…"
	case "awaiting_approval":
		return "Waiting Approval…"
	case "executing":
		return "Executing…"
	case "replanning":
		return "Replanning…"
	case "waiting":
		return "Review Scheduled…"
	case "created":
		return "Created"
	case "active":
		return "Active"
	case "completed":
		return "Completed"
	case "archived":
		return "Archived"
	case "failed":
		return "Failed"
	case "paused":
		return "Paused"
	default:
		return strings.Title(status)
	}
}

// missionStatusClass maps a phase to the status-dot colour class.
func missionStatusClass(status string) string {
	switch status {
	case "completed", "monitoring":
		return "connected"
	case "failed", "paused", "archived":
		return "disconnected"
	default:
		return "connecting"
	}
}

// missionStatusPill maps a phase to a pill colour class.
func missionStatusPill(status string) string {
	switch status {
	case "completed", "monitoring":
		return "bg-green-900/30 text-green-400"
	case "investigating", "executing", "replanning":
		return "bg-blue-900/30 text-blue-400"
	case "awaiting_approval":
		return "bg-yellow-900/30 text-yellow-400"
	case "failed":
		return "bg-red-900/30 text-red-400"
	case "paused", "archived":
		return "bg-gray-700/30 text-gray-400"
	default:
		return "bg-blue-900/30 text-blue-400"
	}
}

// missionPct converts a 0..1 confidence to a 0..100 integer.
func missionPct(f float64) int {
	p := int(f * 100)
	if p < 0 {
		p = 0
	}
	if p > 100 {
		p = 100
	}
	return p
}

// missionTimeAgo renders a relative "…ago" label for an RFC3339 timestamp.
func missionTimeAgo(ts string) string {
	if ts == "" {
		return "—"
	}
	t, err := time.Parse(time.RFC3339, ts)
	if err != nil {
		return ts
	}
	d := time.Since(t)
	switch {
	case d < time.Minute:
		return "just now"
	case d < time.Hour:
		return fmt.Sprintf("%dm ago", int(d.Minutes()))
	case d < 24*time.Hour:
		return fmt.Sprintf("%dh ago", int(d.Hours()))
	default:
		return fmt.Sprintf("%dd ago", int(d.Hours()/24))
	}
}

// parseMissionMessage extracts the SSEEvent from a hub-delivered frame
// ("event: <type>\ndata: <json>\n\n") so the SSE endpoint can re-emit the raw
// HTML payload (HTMX sse-swap renders HTML, not the JSON wrapper).
func parseMissionMessage(msgBytes []byte) (SSEEvent, error) {
	var evt SSEEvent
	for _, line := range strings.Split(string(msgBytes), "\n") {
		if strings.HasPrefix(line, "data: ") {
			return evt, json.Unmarshal([]byte(strings.TrimPrefix(line, "data: ")), &evt)
		}
	}
	return evt, fmt.Errorf("no data line in SSE frame")
}

// ── Mission Dashboard (HTMX partial) ───────────────────────────────────────

// APIMissionDashboard renders the Mission Dashboard panel (list of live cards).
func (h *Handler) APIMissionDashboard(c *fiber.Ctx) error {
	if c.Get("HX-Request") != "true" {
		return c.SendString("Mission Dashboard")
	}
	return Render(c, "partials/mission_dashboard", fiber.Map{
		"Missions": h.missions.List(),
	})
}

// APIMissionCenter serves the standalone Mission Workspace page. It loads the
// live Mission Dashboard partial and, when ?mission=<id> is present, the
// matching Mission Detail partial alongside it.
func (h *Handler) APIMissionCenter(c *fiber.Ctx) error {
	return Render(c, "mission_center", fiber.Map{
		"Title":  "OntologyAI — Mission Workspace",
		"Active": c.Query("mission", ""),
	})
}

// APIMissionDetail renders the Mission Detail panel for a single mission.
func (h *Handler) APIMissionDetail(c *fiber.Ctx) error {
	id := c.Params("id")
	card, ok := h.missions.Get(id)
	if !ok {
		return c.Status(404).SendString(`<div class="text-red-400 text-sm">Mission not found</div>`)
	}
	return Render(c, "partials/mission_detail", fiber.Map{
		"Mission":  card,
		"Timeline": h.missions.Timeline(id),
	})
}

// APIMissionSchema returns a mission as a Workspace Schema fragment (JSON).
func (h *Handler) APIMissionSchema(c *fiber.Ctx) error {
	id := c.Params("id")
	card, ok := h.missions.Get(id)
	if !ok {
		return c.Status(404).JSON(fiber.Map{"error": "mission not found"})
	}
	now := time.Now().Format(time.RFC3339)
	schema := WorkspaceSchema{
		Workspace: "mission",
		Title:     card.Name,
		TenantID:  c.Query("tenant_id", "default"),
		MissionID: &card.MissionID,
		Components: []Component{
			{
				ID:    "mission-card-" + card.MissionID,
				Type:  "mission_card",
				Title: card.Name,
				Props: map[string]any{
					"status": card.Status, "confidence": card.Confidence,
					"priority": card.Priority, "worker": card.Worker,
					"evidence_count": card.EvidenceCount,
				},
				State: ComponentState{Loading: false, Version: "v1.5"},
			},
		},
		Layout:      LayoutSpec{GridCols: 12, Gap: "2", Responsive: true},
		Permissions: WorkspacePerms{CanView: true, CanEdit: true, CanExecute: true, CanApprove: true},
		UpdatedAt:   &now,
	}
	return c.JSON(schema)
}

// APIMissionNow returns the current UTC datetime (for the live clock).
func (h *Handler) APIMissionNow(c *fiber.Ctx) error {
	return c.JSON(fiber.Map{
		"now":       time.Now().UTC().Format(time.RFC3339),
		"timestamp": time.Now().UTC().Unix(),
	})
}

// ── SSE: mission timeline stream ───────────────────────────────────────────

// APIMissionStream is the SSE endpoint for live mission updates. It subscribes
// to the mission tenant (no filter → all mission events) and re-emits the raw
// HTML payload so HTMX sse-swap renders the affected component only.
func (h *Handler) APIMissionStream(c *fiber.Ctx) error {
	sub := h.sseHub.Subscribe("missions")
	defer h.sseHub.Unsubscribe("missions", sub.ID)

	c.Set("Content-Type", "text/event-stream")
	c.Set("Cache-Control", "no-cache")
	c.Set("Connection", "keep-alive")

	done := c.Context().Done()
	c.Context().SetBodyStreamWriter(func(w *bufio.Writer) {
		defer func() { recover() }()

		fmt.Fprintf(w, "event: connected\ndata: {\"status\":\"connected\",\"text\":\"Connected to mission stream\"}\n\n")
		w.Flush()

		heartbeat := time.NewTicker(30 * time.Second)
		defer heartbeat.Stop()

		for {
			select {
			case <-heartbeat.C:
				_, _ = fmt.Fprintf(w, "event: heartbeat\ndata: {}\n\n")
				w.Flush()
			case msgBytes, ok := <-sub.Channel:
				if !ok {
					return
				}
				evt, err := parseMissionMessage(msgBytes)
				if err != nil {
					continue
				}
				_, _ = fmt.Fprintf(w, "event: %s\ndata: %s\n\n", evt.Type, evt.Payload)
				w.Flush()
			case <-done:
				return
			}
		}
	})
	return nil
}

// APIMissionTimeline is the SSE endpoint for a single mission's timeline. It
// filters the mission stream to events that belong to the requested mission.
func (h *Handler) APIMissionTimeline(c *fiber.Ctx) error {
	missionID := c.Params("id")
	sub := h.sseHub.Subscribe("missions")
	defer h.sseHub.Unsubscribe("missions", sub.ID)

	c.Set("Content-Type", "text/event-stream")
	c.Set("Cache-Control", "no-cache")
	c.Set("Connection", "keep-alive")

	done := c.Context().Done()
	c.Context().SetBodyStreamWriter(func(w *bufio.Writer) {
		defer func() { recover() }()

		fmt.Fprintf(w, "event: connected\ndata: {\"status\":\"connected\",\"text\":\"Connected to mission timeline\"}\n\n")
		w.Flush()

		heartbeat := time.NewTicker(30 * time.Second)
		defer heartbeat.Stop()

		for {
			select {
			case <-heartbeat.C:
				_, _ = fmt.Fprintf(w, "event: heartbeat\ndata: {}\n\n")
				w.Flush()
			case msgBytes, ok := <-sub.Channel:
				if !ok {
					return
				}
				evt, err := parseMissionMessage(msgBytes)
				if err != nil {
					continue
				}
				// Only forward events for this mission (event name carries the id).
				if !strings.Contains(evt.Type, missionID) {
					continue
				}
				_, _ = fmt.Fprintf(w, "event: %s\ndata: %s\n\n", evt.Type, evt.Payload)
				w.Flush()
			case <-done:
				return
			}
		}
	})
	return nil
}

// ──Demo event injection (deterministic, wires to Python later) ────────────

// APIMissionEvent applies a semantic mission event (as Python would emit) to a
// mission: updates the card, records a timeline entry, and broadcasts the
// affected component over the SSE hub. This is the deterministic demo driver.
func (h *Handler) APIMissionEvent(c *fiber.Ctx) error {
	id := c.Params("id")
	card, ok := h.missions.Get(id)
	if !ok {
		return c.Status(404).JSON(fiber.Map{"error": "mission not found"})
	}

	var req struct {
		Type       string   `json:"type" form:"type"`
		Status     string   `json:"status" form:"status"`
		Confidence *float64 `json:"confidence" form:"confidence"`
		Evidence   *int     `json:"evidence_count" form:"evidence_count"`
		Priority   string   `json:"priority" form:"priority"`
		Summary    string   `json:"summary" form:"summary"`
	}
	if err := c.BodyParser(&req); err != nil {
		return c.Status(400).JSON(fiber.Map{"error": "invalid JSON"})
	}
	if req.Type == "" {
		return c.Status(400).JSON(fiber.Map{"error": "type required"})
	}

	// Apply the semantic change to the mission card.
	if req.Status != "" {
		card.Status = req.Status
	}
	if req.Confidence != nil {
		card.Confidence = *req.Confidence
	}
	if req.Priority != "" {
		card.Priority = req.Priority
	}
	if req.Evidence != nil {
		card.EvidenceCount = *req.Evidence
	}
	card.LastObservedAt = time.Now().UTC().Format(time.RFC3339)
	h.missions.Upsert(card)

	// Map the semantic event to an SSE event + partial.
	base, partial := MissionEventToSSE(req.Type)
	sseName := missionSSEEventName(base, id)

	// Render the affected component as an HTML fragment.
	htmlFragment, err := renderPartialToString("partials/"+partial, fiber.Map{"Card": card})
	if err != nil {
		return c.Status(500).JSON(fiber.Map{"error": "failed to render partial"})
	}

	// Record a timeline entry.
	summary := req.Summary
	if summary == "" {
		summary = fmt.Sprintf("%s → %s", req.Type, card.Status)
	}
	h.missions.AddTimeline(MissionTimelineEntry{
		MissionID: id, EventType: req.Type, SSEEvent: sseName,
		Partial: partial, Summary: summary, At: time.Now().UTC().Format(time.RFC3339),
	})

	// Broadcast the affected component over the existing SSEHub.
	if h.sseHub != nil {
		h.sseHub.Broadcast("missions", SSEEvent{Type: sseName, Payload: htmlFragment})
	}

	return c.JSON(fiber.Map{"ok": true, "mission_id": id, "sse_event": sseName, "card": card})
}

// RegisterMissionRoutes registers the Milestone 1.5 mission workspace routes.
func (h *Handler) RegisterMissionRoutes(app *fiber.App) {
	app.Get("/missions", h.APIMissionCenter)
	app.Get("/api/missions/dashboard", h.APIMissionDashboard)
	app.Get("/api/missions/stream", h.APIMissionStream)
	app.Get("/api/missions/now", h.APIMissionNow)
	app.Get("/api/missions/:id", h.APIMissionDetail)
	app.Get("/api/missions/:id/schema", h.APIMissionSchema)
	app.Get("/api/missions/:id/timeline", h.APIMissionTimeline)
	app.Post("/api/missions/:id/event", h.APIMissionEvent)
}
