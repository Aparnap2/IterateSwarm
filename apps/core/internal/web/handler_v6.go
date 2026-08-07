package web

import (
	"github.com/gofiber/fiber/v2"
	"iterateswarm-core/internal/v6"
)

// RegisterV6Routes adds V6 API routes to the Fiber app.
func RegisterV6Routes(app *fiber.App) {
	deps := &v6.Dependencies{
		GraphStore: nil, // wired in Milestone 1
	}
	v6.RegisterRoutes(app, deps)
}
