package web

import (
	"database/sql"
	"time"

	"github.com/gofiber/fiber/v2"
)

// ============== Panel 3: Runtime Map ==============

// RuntimeStatus represents a runtime's current status
type RuntimeStatus struct {
	Name      string `json:"name"`
	State     string `json:"state"` // active, busy, idle, error
	TaskCount int    `json:"task_count"`
	LastSeen  string `json:"last_seen"`
}

// GetRuntimeStatus returns status for a specific runtime from agent_traces
func (h *Handler) GetAgentStatus(c *fiber.Ctx) error {
	agent := c.Params("agent")
	if agent == "" {
		return c.Status(400).JSON(fiber.Map{"error": "Missing agent parameter"})
	}

	status := RuntimeStatus{
		Name:      agent,
		State:     "idle",
		TaskCount: 0,
		LastSeen:  time.Now().Format(time.RFC3339),
	}

	if h.db != nil {
		// Get last trace for this agent
		var lastSeen sql.NullTime
		var taskCount int
		err := h.db.QueryRow(`
			SELECT MAX(created_at), COUNT(*)
			FROM agent_traces
			WHERE agent_name = $1
		`, agent).Scan(&lastSeen, &taskCount)
		if err == nil {
			if lastSeen.Valid {
				status.LastSeen = lastSeen.Time.Format(time.RFC3339)
			}
			status.TaskCount = taskCount
		}

		// Determine state from most recent trace status
		var recentStatus sql.NullString
		_ = h.db.QueryRow(`
			SELECT status FROM agent_traces
			WHERE agent_name = $1
			ORDER BY created_at DESC
			LIMIT 1
		`, agent).Scan(&recentStatus)
		if recentStatus.Valid {
			switch recentStatus.String {
			case "processing", "running":
				status.State = "busy"
			case "failed":
				status.State = "error"
			case "success", "completed":
				status.State = "active"
			default:
				status.State = "idle"
			}
		}
	}

	return c.JSON(status)
}

// GetAllRuntimesStatus returns status for all runtimes from agent_traces
func (h *Handler) GetAllAgentsStatus(c *fiber.Ctx) error {
	statuses := make(map[string]RuntimeStatus)

	if h.db != nil {
		rows, err := h.db.Query(`
			SELECT agent_name,
			       MAX(created_at) as last_seen,
			       COUNT(*) as task_count
			FROM agent_traces
			WHERE agent_name IS NOT NULL AND agent_name != ''
			GROUP BY agent_name
			ORDER BY agent_name
		`)
		if err == nil {
			defer rows.Close()
			for rows.Next() {
				var name string
				var lastSeen time.Time
				var taskCount int
				if err := rows.Scan(&name, &lastSeen, &taskCount); err == nil {
					state := "idle"
					// Check most recent status
					var recentStatus sql.NullString
					_ = h.db.QueryRow(`
						SELECT status FROM agent_traces
						WHERE agent_name = $1
						ORDER BY created_at DESC LIMIT 1
					`, name).Scan(&recentStatus)
					if recentStatus.Valid {
						switch recentStatus.String {
						case "processing", "running":
							state = "busy"
						case "failed":
							state = "error"
						case "success", "completed":
							state = "active"
						}
					}
					statuses[name] = RuntimeStatus{
						Name:      name,
						State:     state,
						TaskCount: taskCount,
						LastSeen:  lastSeen.Format(time.RFC3339),
					}
				}
			}
		}
	}

	return c.JSON(statuses)
}

// GetRuntimeMap renders the runtime map panel
func (h *Handler) GetAgentMap(c *fiber.Ctx) error {
	return Render(c, "agent_map", nil)
}

// ============== Panel 4: Task Board ==============

// Task represents a task in the kanban board
type Task struct {
	TaskID      string `json:"task_id"`
	Description string `json:"description"`
	Priority    string `json:"priority"`
	CreatedAt   string `json:"created_at"`
	Source      string `json:"source"`
	Progress    int    `json:"progress"`
	Confidence  int    `json:"confidence"`
	Result      string `json:"result"`
	CompletedAt string `json:"completed_at"`
}

// TaskBoard represents all tasks organized by status
type TaskBoard struct {
	Queued       []Task `json:"queued"`
	Analyzing    []Task `json:"analyzing"`
	AwaitingHITL []Task `json:"awaiting_hitl"`
	Completed    []Task `json:"completed"`
}

// GetTaskBoard renders the task board panel
func (h *Handler) GetTaskBoard(c *fiber.Ctx) error {
	board := h.getTaskBoardData()
	return Render(c, "task_board", board)
}

// GetQueuedTasks returns tasks in queued state
func (h *Handler) GetQueuedTasks(c *fiber.Ctx) error {
	board := h.getTaskBoardData()
	return Render(c, "task_board", fiber.Map{
		"Queued": board.Queued,
	})
}

// GetAnalyzingTasks returns tasks in analyzing state
func (h *Handler) GetAnalyzingTasks(c *fiber.Ctx) error {
	board := h.getTaskBoardData()
	return Render(c, "task_board", fiber.Map{
		"Analyzing": board.Analyzing,
	})
}

// GetAwaitingHITLTasks returns tasks awaiting human review
func (h *Handler) GetAwaitingHITLTasks(c *fiber.Ctx) error {
	board := h.getTaskBoardData()
	return Render(c, "task_board", fiber.Map{
		"AwaitingHITL": board.AwaitingHITL,
	})
}

// GetCompletedTasks returns completed tasks
func (h *Handler) GetCompletedTasks(c *fiber.Ctx) error {
	board := h.getTaskBoardData()
	return Render(c, "task_board", fiber.Map{
		"Completed": board.Completed,
	})
}

// getTaskBoardData retrieves task board data from database tables
func (h *Handler) getTaskBoardData() *TaskBoard {
	board := &TaskBoard{
		Queued:       []Task{},
		Analyzing:    []Task{},
		AwaitingHITL: []Task{},
		Completed:    []Task{},
	}

	if h.db == nil {
		return board
	}

	// Queued tasks: sop_jobs with status = 'pending'
	queuedRows, err := h.db.Query(`
		SELECT id, COALESCE(sop_name, '') as description, 'pending' as priority,
		       created_at, 'sop_jobs' as source, 0 as progress, 0 as confidence
		FROM sop_jobs
		WHERE status = 'pending'
		ORDER BY created_at DESC
		LIMIT 20
	`)
	if err == nil {
		defer queuedRows.Close()
		for queuedRows.Next() {
			var t Task
			if err := queuedRows.Scan(&t.TaskID, &t.Description, &t.Priority, &t.CreatedAt, &t.Source, &t.Progress, &t.Confidence); err == nil {
				board.Queued = append(board.Queued, t)
			}
		}
	}

	// Analyzing tasks: agent_traces with status = 'processing' or similar
	analyzingRows, err := h.db.Query(`
		SELECT trace_id, COALESCE(action, '') as description, COALESCE(status, 'processing') as priority,
		       created_at, 'agent_traces' as source, COALESCE(duration_ms, 0) / 1000 as progress, 0 as confidence
		FROM agent_traces
		WHERE status = 'processing' OR status = 'running'
		ORDER BY created_at DESC
		LIMIT 20
	`)
	if err == nil {
		defer analyzingRows.Close()
		for analyzingRows.Next() {
			var t Task
			if err := analyzingRows.Scan(&t.TaskID, &t.Description, &t.Priority, &t.CreatedAt, &t.Source, &t.Progress, &t.Confidence); err == nil {
				board.Analyzing = append(board.Analyzing, t)
			}
		}
	}

	// Awaiting HITL: planned_actions with status = 'planned'
	hitlRows, err := h.db.Query(`
		SELECT id, COALESCE(approval_reason, action_type) as description,
		       COALESCE(risk_level, 'medium') as priority,
		       created_at, 'planned_actions' as source, 0 as progress, 0 as confidence
		FROM planned_actions
		WHERE status = 'planned'
		ORDER BY created_at DESC
		LIMIT 20
	`)
	if err == nil {
		defer hitlRows.Close()
		for hitlRows.Next() {
			var t Task
			if err := hitlRows.Scan(&t.TaskID, &t.Description, &t.Priority, &t.CreatedAt, &t.Source, &t.Progress, &t.Confidence); err == nil {
				board.AwaitingHITL = append(board.AwaitingHITL, t)
			}
		}
	}

	// Completed tasks: agent_traces with status = 'success' or 'completed'
	completedRows, err := h.db.Query(`
		SELECT trace_id, COALESCE(action, '') as description, COALESCE(status, 'completed') as priority,
		       created_at, 'agent_traces' as source, 100 as progress, 0 as confidence
		FROM agent_traces
		WHERE status = 'success' OR status = 'completed'
		ORDER BY created_at DESC
		LIMIT 20
	`)
	if err == nil {
		defer completedRows.Close()
		for completedRows.Next() {
			var t Task
			if err := completedRows.Scan(&t.TaskID, &t.Description, &t.Priority, &t.CreatedAt, &t.Source, &t.Progress, &t.Confidence); err == nil {
				board.Completed = append(board.Completed, t)
			}
		}
	}

	return board
}

// GetTaskDetails returns details for a specific task
func (h *Handler) GetTaskDetails(c *fiber.Ctx) error {
	taskID := c.Params("id")

	task := map[string]interface{}{
		"task_id":     taskID,
		"description": "Task not found",
		"status":      "unknown",
	}

	if h.db != nil {
		// Try agent_traces first
		var traceID, action, status string
		var durationMs sql.NullInt32
		var llmCalls sql.NullInt32
		var llmTokens sql.NullInt32
		var createdAt time.Time
		err := h.db.QueryRow(`
			SELECT trace_id, COALESCE(action, ''), COALESCE(status, ''),
			       COALESCE(duration_ms, 0), COALESCE(llm_calls, 0), COALESCE(llm_tokens, 0), created_at
			FROM agent_traces
			WHERE trace_id = $1
		`, taskID).Scan(&traceID, &action, &status, &durationMs, &llmCalls, &llmTokens, &createdAt)
		if err == nil {
			task = map[string]interface{}{
				"task_id":     traceID,
				"description": action,
				"status":      status,
				"duration_ms": durationMs,
				"llm_calls":   llmCalls,
				"llm_tokens":  llmTokens,
				"created_at":  createdAt.Format(time.RFC3339),
			}
		} else {
			// Fallback: try sop_jobs
			var sopID, sopName, sopStatus string
			var sopCreatedAt time.Time
			err2 := h.db.QueryRow(`
				SELECT id, COALESCE(sop_name, ''), COALESCE(status, 'pending'), created_at
				FROM sop_jobs WHERE id = $1
			`, taskID).Scan(&sopID, &sopName, &sopStatus, &sopCreatedAt)
			if err2 == nil {
				task = map[string]interface{}{
					"task_id":     sopID,
					"description": sopName,
					"status":      sopStatus,
					"created_at":  sopCreatedAt.Format(time.RFC3339),
				}
			}
		}
	}

	return c.JSON(task)
}
