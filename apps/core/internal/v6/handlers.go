package v6

import (
	"github.com/gofiber/fiber/v2"
)

// Dependencies holds the services that V6 handlers delegate to.
// These are wired in as milestones progress.
type Dependencies struct {
	GraphStore GraphStore
}

// RegisterRoutes registers V6 API endpoints on the given Fiber router.
func RegisterRoutes(app fiber.Router, deps *Dependencies) {
	g := app.Group("/v6")

	g.Post("/evidence", deps.IngestEvidence)
	g.Post("/evidence/batch", deps.IngestEvidenceBatch)

	g.Get("/workspace/:id", deps.GetWorkspace)
	g.Get("/workspace/:id/entities", deps.GetWorkspaceEntities)
	g.Get("/workspace/:id/decisions", deps.GetWorkspaceDecisions)
	g.Get("/workspace/:id/artifacts", deps.GetWorkspaceArtifacts)

	g.Post("/decision", deps.CreateDecision)
	g.Get("/decision/:id", deps.GetDecision)
	g.Post("/decision/:id/score", deps.ScoreDecision)

	g.Get("/artifact/:id", deps.GetArtifact)
	g.Post("/artifact/:id/validate", deps.ValidateArtifact)
	g.Post("/artifact/:id/publish", deps.PublishArtifact)

	g.Post("/validation/run", deps.RunValidation)
	g.Get("/validation/:id", deps.GetValidationResult)

	g.Post("/graph/query", deps.QueryGraph)
	g.Get("/graph/entity/:id", deps.GetEntityGraph)
	g.Get("/graph/entity/:id/traverse", deps.TraverseEntity)

	g.Get("/health", deps.Health)
}

// IngestEvidence validates and accepts a single evidence record.
func (d *Dependencies) IngestEvidence(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// IngestEvidenceBatch accepts multiple evidence records in one request.
func (d *Dependencies) IngestEvidenceBatch(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// GetWorkspace returns workspace details by ID.
func (d *Dependencies) GetWorkspace(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// GetWorkspaceEntities lists entities linked to a workspace.
func (d *Dependencies) GetWorkspaceEntities(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// GetWorkspaceDecisions lists decisions in a workspace.
func (d *Dependencies) GetWorkspaceDecisions(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// GetWorkspaceArtifacts lists artifacts in a workspace.
func (d *Dependencies) GetWorkspaceArtifacts(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// CreateDecision creates a new decision with associated evidence.
func (d *Dependencies) CreateDecision(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// GetDecision returns a decision by ID.
func (d *Dependencies) GetDecision(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// ScoreDecision triggers feasibility scoring for a decision.
func (d *Dependencies) ScoreDecision(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// GetArtifact returns an artifact by ID.
func (d *Dependencies) GetArtifact(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// ValidateArtifact triggers validation for an artifact.
func (d *Dependencies) ValidateArtifact(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// PublishArtifact publishes a validated artifact.
func (d *Dependencies) PublishArtifact(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// RunValidation runs validation rules against a workspace or artifact.
func (d *Dependencies) RunValidation(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// GetValidationResult returns validation result by ID.
func (d *Dependencies) GetValidationResult(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// QueryGraph runs a Cypher query against Neo4j.
func (d *Dependencies) QueryGraph(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// GetEntityGraph returns the graph surrounding an entity.
func (d *Dependencies) GetEntityGraph(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// TraverseEntity traverses relationships from an entity up to maxHops.
func (d *Dependencies) TraverseEntity(c *fiber.Ctx) error {
	return c.Status(fiber.StatusNotImplemented).JSON(fiber.Map{"error": "not implemented"})
}

// Health returns V6 service health status.
func (d *Dependencies) Health(c *fiber.Ctx) error {
	return c.JSON(fiber.Map{
		"status":  "ok",
		"version": "0.6.0",
	})
}
