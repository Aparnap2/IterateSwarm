package web

import (
	"bufio"
	"bytes"
	"context"
	"fmt"
	"html"
	"log"
	"strings"
	"time"

	"github.com/gofiber/fiber/v2"
	temporalclient "go.temporal.io/sdk/client"

	"iterateswarm-core/internal/temporal"
)

// ============== Panel 1: Live Feed ==============

// GetLiveFeed renders the live feed panel
func (h *Handler) GetLiveFeed(c *fiber.Ctx) error {
	return Render(c, "live_feed", nil)
}

// ============== Chat / SSE / Streaming ==============

// APICommandChatSend handles chat message submission with @mention parsing
func (h *Handler) APICommandChatSend(c *fiber.Ctx) error {
	message := c.FormValue("message")
	mention := c.FormValue("mention")

	if message == "" {
		return c.SendString("")
	}

	// Parse @mentions from message text
	mentions := extractMentions(message)
	if mention != "" && mention != "@all" {
		mentions = append(mentions, mention)
	}

	// Deduplicate mentions
	seen := make(map[string]bool)
	var unique []string
	for _, m := range mentions {
		if !seen[m] {
			seen[m] = true
			unique = append(unique, m)
		}
	}

	// Without DB: return empty for backward compat with tests
	if h.db == nil {
		return c.SendString("")
	}

	// With DB: persist message, broadcast via SSE, and return JSON
	var createdAt time.Time
	err := h.db.QueryRow(
		`INSERT INTO chat_messages (sender, mention, message) VALUES ('founder', $1, $2) RETURNING created_at`,
		mention, message,
	).Scan(&createdAt)
	if err == nil {
		h.chatBroadcast <- fiber.Map{
			"sender":      "founder",
			"displayName": "You",
			"text":        message,
			"time":        createdAt.Format("15:04:05"),
		}
	}

	// Specialist workflow routing: map mention → workflow type + display name
	type specialistRoute struct {
		workflowType string
		displayName  string
	}

	// V6 9-runtime model: @mentions map to Temporal workflow implementations
	// of the Evidence→Knowledge→Decision→Workspace pipeline.
	// ChiefOfStaffWorkflow is the coordinator/router that dispatches to domain workflows.
	var specialistRoutes = map[string]specialistRoute{
		"@sarthi":   {"ChiefOfStaffWorkflow", "Workspace Guide"},
		"@finance":  {"FinanceWorkflow", "FP&A"},
		"@data":     {"DataWorkflow", "Data"},
		"@ops":      {"OpsWorkflow", "Ops"},
		"@qa":       {"QAWorkflow", "QA"},
		"@comms":    {"CommsWorkflow", "Comms"},
		"@hiring":   {"HiringWorkflow", "Hiring"},
		"@pulse":    {"PulseWorkflow", "Pulse"},
		"@anomaly":  {"AnomalyWorkflow", "Anomaly"},
		"@investor": {"InvestorWorkflow", "Investor"},
	}

	shouldDispatch := false
	mentionTarget := ""
	route := specialistRoute{}
	for _, m := range unique {
		m = strings.ToLower(m)
		if r, ok := specialistRoutes[m]; ok {
			shouldDispatch = true
			mentionTarget = m
			route = r
			break
		}
	}
	// Dispatch ChiefOfStaff workflow asynchronously via Temporal
	if shouldDispatch && h.temporal != nil {
		workflowID := fmt.Sprintf("chat-qa-%s-%d", strings.ReplaceAll(c.IP(), ":", ""), time.Now().UnixNano())

		input := map[string]interface{}{
			"tenant_id":      "default",
			"question":       message,
			"notify_channel": "#chat",
		}

		// Show "thinking" indicator immediately via SSE (non-blocking)
		h.tryBroadcast(mentionTarget, route.displayName, "🤔 Thinking...")

		// Dispatch workflow in background goroutine — result pushes via SSE when ready
		h.wg.Add(1)
		go func(handler *Handler, wID, target string, r specialistRoute, in map[string]interface{}, reqCtx context.Context) {
			defer handler.wg.Done()

			// Merge request context with longer timeout
			ctx, cancel := context.WithTimeout(reqCtx, 5*time.Minute)
			defer cancel()

			opts := temporalclient.StartWorkflowOptions{
				ID:        wID,
				TaskQueue: temporal.ResolveTaskQueue(),
			}

			run, err := handler.temporal.Client.ExecuteWorkflow(ctx, opts, r.workflowType, in)
			if err != nil {
				log.Printf("Failed to start QA workflow: %v", err)
				return
			}

			log.Printf("QA workflow started: id=%s", wID)

			var result map[string]interface{}
			if getErr := run.Get(ctx, &result); getErr != nil {
				log.Printf("QA workflow failed: %v", getErr)
				handler.tryBroadcast(target, r.displayName, fmt.Sprintf("❌ Sorry, I couldn't process your question: %v", getErr))
				return
			}

			ok, _ := result["ok"].(bool)
			answer := ""
			// V6 SpecialistResponse format: summary / detailed_response
			if s, _ := result["summary"].(string); s != "" {
				answer = s
			} else if s, _ := result["detailed_response"].(string); s != "" {
				answer = s
			}
			// Legacy QA workflow format: qa_result.answer
			if answer == "" {
				if qr, _ := result["qa_result"].(map[string]interface{}); qr != nil {
					if s, _ := qr["answer"].(string); s != "" {
						answer = s
					} else if s, _ := qr["output_message"].(string); s != "" {
						answer = s
					}
				}
			}
			if answer == "" {
				answer, _ = result["error"].(string)
			}
			if answer == "" {
				answer = "I processed your question but couldn't generate an answer."
			}

			log.Printf("QA workflow result: ok=%v answer=%s", ok, answer[:min(len(answer), 200)])

			// Persist to DB
			var agentCreatedAt time.Time
			if handler.db != nil {
				if err := handler.db.QueryRow(
					`INSERT INTO chat_messages (sender, mention, message) VALUES ('agent', $1, $2) RETURNING created_at`,
					target, answer,
				).Scan(&agentCreatedAt); err != nil {
					log.Printf("Failed to persist agent response: %v", err)
				}
			}

			handler.tryBroadcast("agent", r.displayName, answer)
		}(h, workflowID, mentionTarget, route, input, context.Background())
	}

	// Return the user message bubble as HTML so HTMX can append it to #chat-messages.
	// The form uses hx-target="#chat-messages" hx-swap="beforeend" to append this.
	userDisplayName := "You"
	timeStr := createdAt.Format("15:04:05")
	return c.SendString(h.renderChatBubble("founder", userDisplayName, message, timeStr))
}

// renderChatBubble builds an HTML string for a single chat message bubble.
// This is used by the SSE endpoint to send HTML fragments that HTMX swaps directly.
func (h *Handler) renderChatBubble(sender, displayName, text, timeStr string) string {
	// Normalize sender key for CSS class lookup
	normalized := strings.TrimPrefix(sender, "@")

	agentClasses := map[string]string{
		"founder":  "bg-blue-500/20 text-blue-400",
		"sarthi":   "agent-chief-of-staff",
		"finance":  "agent-fpa",
		"data":     "agent-growth-analytics",
		"ops":      "agent-reliability",
		"qa":       "agent-qa",
		"comms":    "agent-comms",
		"hiring":   "agent-hiring",
		"pulse":    "agent-pulse",
		"anomaly":  "agent-anomaly",
		"investor": "agent-investor",
	}
	agentClass := agentClasses[normalized]
	if agentClass == "" {
		agentClass = "agent-system"
	}

	initials := map[string]string{
		"founder": "Y", "sarthi": "W",
		"finance": "F", "data": "G", "ops": "R",
		"qa": "Q", "comms": "M", "hiring": "H",
		"pulse": "P", "anomaly": "A", "investor": "I",
	}
	initial := initials[normalized]
	if initial == "" && len(normalized) > 0 {
		initial = strings.ToUpper(string(normalized[0]))
	} else if initial == "" {
		initial = "?"
	}

	if timeStr == "" {
		timeStr = time.Now().Format("15:04:05")
	}

	var buf bytes.Buffer
	buf.WriteString(`<div class="chat-msg flex gap-2 mb-2">`)
	buf.WriteString(`<div class="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 `)
	buf.WriteString(agentClass)
	buf.WriteString(`">`)
	buf.WriteString(initial)
	buf.WriteString(`</div>`)
	buf.WriteString(`<div class="flex-1 min-w-0">`)
	buf.WriteString(`<div class="flex items-baseline gap-2">`)
	buf.WriteString(`<span class="text-xs font-semibold" style="color:var(--text)">`)
	buf.WriteString(html.EscapeString(displayName))
	buf.WriteString(`</span>`)
	buf.WriteString(`<span class="text-[10px]" style="color:var(--text-muted)">`)
	buf.WriteString(html.EscapeString(timeStr))
	buf.WriteString(`</span></div>`)
	buf.WriteString(`<p class="text-xs mt-0.5" style="color:var(--text-secondary);word-break:break-word">`)
	buf.WriteString(html.EscapeString(text))
	buf.WriteString(`</p></div></div>`)
	return buf.String()
}

// tryBroadcast sends a message to chatBroadcast without blocking.
func (h *Handler) tryBroadcast(sender, displayName, text string) {
	msg := fiber.Map{
		"sender":      sender,
		"displayName": displayName,
		"text":        text,
		"time":        time.Now().Format("15:04:05"),
	}
	select {
	case h.chatBroadcast <- msg:
	default:
		log.Printf("chatBroadcast channel full, dropping message from %s", sender)
	}
	// Also broadcast via SSEHub for fan-out support
	if h.sseHub != nil {
		h.sseHub.Broadcast("default", SSEEvent{
			Type:    "chat",
			Payload: fmt.Sprintf("%s|%s|%s|%s", sender, displayName, text, time.Now().Format("15:04:05")),
		})
	}
}

// extractMentions finds @mentions in a message string
func extractMentions(msg string) []string {
	var mentions []string
	words := strings.Fields(msg)
	for _, w := range words {
		if strings.HasPrefix(w, "@") {
			mention := strings.TrimRight(w, ",.;:!?")
			mentions = append(mentions, mention)
		}
	}
	return mentions
}

// APICommandEvents is the SSE endpoint for the dashboard connection indicator (heartbeats only)
func (h *Handler) APICommandEvents(c *fiber.Ctx) error {
	c.Set("Content-Type", "text/event-stream")
	c.Set("Cache-Control", "no-cache")
	c.Set("Connection", "keep-alive")

	done := c.Context().Done()
	c.Context().SetBodyStreamWriter(func(w *bufio.Writer) {
		defer func() { recover() }()
		fmt.Fprintf(w, "event: connected\ndata: {\"status\":\"connected\"}\n\n")
		w.Flush()

		heartbeat := time.NewTicker(30 * time.Second)
		defer heartbeat.Stop()

		for {
			select {
			case <-heartbeat.C:
				_, err := fmt.Fprintf(w, "event: heartbeat\ndata: {}\n\n")
				if err != nil {
					return
				}
				w.Flush()
			case <-done:
				return
			}
		}
	})

	return nil
}

// APICommandChatEvents is a dedicated SSE endpoint for chat messages.
// It sends HTML fragments instead of JSON so HTMX's SSE extension can
// swap them directly into the DOM (via sse-swap="chat" + hx-swap="beforeend").
func (h *Handler) APICommandChatEvents(c *fiber.Ctx) error {
	tenantID := c.Query("tenant_id", "default")
	sub := h.sseHub.Subscribe(tenantID, "chat")
	defer h.sseHub.Unsubscribe(tenantID, sub.ID)

	c.Set("Content-Type", "text/event-stream")
	c.Set("Cache-Control", "no-cache")
	c.Set("Connection", "keep-alive")

	done := c.Context().Done()
	c.Context().SetBodyStreamWriter(func(w *bufio.Writer) {
		defer func() { recover() }()

		fmt.Fprintf(w, "event: connected\ndata: {\"status\":\"connected\",\"text\":\"Connected to chat\"}\n\n")
		w.Flush()

		heartbeat := time.NewTicker(30 * time.Second)
		defer heartbeat.Stop()

		for {
			select {
			case <-heartbeat.C:
				_, err := fmt.Fprintf(w, "event: heartbeat\ndata: {}\n\n")
				if err != nil {
					return
				}
				w.Flush()
			case msgBytes, ok := <-sub.Channel:
				if !ok {
					return
				}
				_, err := fmt.Fprintf(w, "%s", msgBytes)
				if err != nil {
					return
				}
				w.Flush()
			case <-done:
				return
			}
		}
	})

	return nil
}

// APICommandMissionEvents is an SSE endpoint for mission state updates (event type: "mission-update").
func (h *Handler) APICommandMissionEvents(c *fiber.Ctx) error {
	tenantID := c.Query("tenant_id", "default")
	sub := h.sseHub.Subscribe(tenantID, "mission-update")
	defer h.sseHub.Unsubscribe(tenantID, sub.ID)

	c.Set("Content-Type", "text/event-stream")
	c.Set("Cache-Control", "no-cache")
	c.Set("Connection", "keep-alive")

	done := c.Context().Done()
	c.Context().SetBodyStreamWriter(func(w *bufio.Writer) {
		defer func() { recover() }()

		fmt.Fprintf(w, "event: connected\ndata: {\"status\":\"connected\",\"text\":\"Connected to mission events\"}\n\n")
		w.Flush()

		heartbeat := time.NewTicker(30 * time.Second)
		defer heartbeat.Stop()

		for {
			select {
			case <-heartbeat.C:
				_, err := fmt.Fprintf(w, "event: heartbeat\ndata: {}\n\n")
				if err != nil {
					return
				}
				w.Flush()
			case msgBytes, ok := <-sub.Channel:
				if !ok {
					return
				}
				_, err := fmt.Fprintf(w, "%s", msgBytes)
				if err != nil {
					return
				}
				w.Flush()
			case <-done:
				return
			}
		}
	})

	return nil
}

// APICommandHITLEvents is an SSE endpoint for HITL approval events (event type: "hitl-item").
func (h *Handler) APICommandHITLEvents(c *fiber.Ctx) error {
	tenantID := c.Query("tenant_id", "default")
	sub := h.sseHub.Subscribe(tenantID, "hitl-item")
	defer h.sseHub.Unsubscribe(tenantID, sub.ID)

	c.Set("Content-Type", "text/event-stream")
	c.Set("Cache-Control", "no-cache")
	c.Set("Connection", "keep-alive")

	done := c.Context().Done()
	c.Context().SetBodyStreamWriter(func(w *bufio.Writer) {
		defer func() { recover() }()

		fmt.Fprintf(w, "event: connected\ndata: {\"status\":\"connected\",\"text\":\"Connected to HITL events\"}\n\n")
		w.Flush()

		heartbeat := time.NewTicker(30 * time.Second)
		defer heartbeat.Stop()

		for {
			select {
			case <-heartbeat.C:
				_, err := fmt.Fprintf(w, "event: heartbeat\ndata: {}\n\n")
				if err != nil {
					return
				}
				w.Flush()
			case msgBytes, ok := <-sub.Channel:
				if !ok {
					return
				}
				_, err := fmt.Fprintf(w, "%s", msgBytes)
				if err != nil {
					return
				}
				w.Flush()
			case <-done:
				return
			}
		}
	})

	return nil
}

// APICommandSessionEvents is an SSE endpoint for agent message events (event type: "agent-message").
func (h *Handler) APICommandSessionEvents(c *fiber.Ctx) error {
	tenantID := c.Query("tenant_id", "default")
	sub := h.sseHub.Subscribe(tenantID, "agent-message")
	defer h.sseHub.Unsubscribe(tenantID, sub.ID)

	c.Set("Content-Type", "text/event-stream")
	c.Set("Cache-Control", "no-cache")
	c.Set("Connection", "keep-alive")

	done := c.Context().Done()
	c.Context().SetBodyStreamWriter(func(w *bufio.Writer) {
		defer func() { recover() }()

		fmt.Fprintf(w, "event: connected\ndata: {\"status\":\"connected\",\"text\":\"Connected to session events\"}\n\n")
		w.Flush()

		heartbeat := time.NewTicker(30 * time.Second)
		defer heartbeat.Stop()

		for {
			select {
			case <-heartbeat.C:
				_, err := fmt.Fprintf(w, "event: heartbeat\ndata: {}\n\n")
				if err != nil {
					return
				}
				w.Flush()
			case msgBytes, ok := <-sub.Channel:
				if !ok {
					return
				}
				_, err := fmt.Fprintf(w, "%s", msgBytes)
				if err != nil {
					return
				}
				w.Flush()
			case <-done:
				return
			}
		}
	})

	return nil
}

// APICommandRevenueEvents is an SSE endpoint for Revenue Protection findings.
func (h *Handler) APICommandRevenueEvents(c *fiber.Ctx) error {
	tenantID := c.Query("tenant_id", "default")
	sub := h.sseHub.Subscribe(tenantID, "revenue_finding")
	defer h.sseHub.Unsubscribe(tenantID, sub.ID)

	c.Set("Content-Type", "text/event-stream")
	c.Set("Cache-Control", "no-cache")
	c.Set("Connection", "keep-alive")

	done := c.Context().Done()
	c.Context().SetBodyStreamWriter(func(w *bufio.Writer) {
		defer func() { recover() }()
		fmt.Fprintf(w, "event: connected\ndata: {\"status\":\"connected\"}\n\n")
		w.Flush()

		heartbeat := time.NewTicker(30 * time.Second)
		defer heartbeat.Stop()

		for {
			select {
			case msgBytes, ok := <-sub.Channel:
				if !ok {
					return
				}
				w.Write(msgBytes)
				w.Flush()
			case <-heartbeat.C:
				fmt.Fprintf(w, "event: heartbeat\ndata: {}\n\n")
				w.Flush()
			case <-done:
				return
			}
		}
	})
	return nil
}
