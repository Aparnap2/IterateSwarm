package web

import (
	"github.com/gofiber/fiber/v2"
)

// safePreview safely truncates a string to max runes, appending "..." if truncated
func safePreview(s string, max int) string {
	r := []rune(s)
	if len(r) <= max {
		return s
	}
	return string(r[:max]) + "..."
}

// ── Command Center Handlers ────────────────────────────

// CommandCenter serves the command center dashboard page
func (h *Handler) CommandCenter(c *fiber.Ctx) error {
	return Render(c, "command_center", fiber.Map{
		"Title": "OntologyAI Workspace Command Center",
	})
}
