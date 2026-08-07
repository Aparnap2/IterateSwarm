package web

import (
	"encoding/json"
	"io"
	"net/http/httptest"
	"testing"

	"github.com/gofiber/fiber/v2"
	"github.com/stretchr/testify/assert"
)

func TestAPIWorkspaceSchema(t *testing.T) {
	app := fiber.New()
	app.Get("/schema", APIWorkspaceSchema)

	req := httptest.NewRequest("GET", "/schema", nil)
	resp, err := app.Test(req)
	assert.NoError(t, err)
	assert.Equal(t, 200, resp.StatusCode)

	var schema WorkspaceSchema
	json.NewDecoder(resp.Body).Decode(&schema)
	assert.Equal(t, "revenue-health", schema.Workspace)
	assert.NotEmpty(t, schema.Components)
}

func TestRenderWorkspace(t *testing.T) {
	schema := WorkspaceSchema{
		Workspace: "test-ws",
		Title:     "Test",
		TenantID:  "t1",
		Components: []Component{
			{
				ID:    "card-1",
				Type:  "kpi_card",
				Title: "MRR",
				Props: map[string]any{"value": float64(45000)},
				State: ComponentState{Loading: false, Version: "v6"},
			},
		},
	}

	app := fiber.New()
	app.Get("/render", func(c *fiber.Ctx) error {
		return RenderWorkspace(c, schema)
	})

	req := httptest.NewRequest("GET", "/render", nil)
	resp, err := app.Test(req)
	assert.NoError(t, err)
	assert.Equal(t, 200, resp.StatusCode)

	body, _ := io.ReadAll(resp.Body)
	assert.Contains(t, string(body), "workspace-test-ws")
	assert.Contains(t, string(body), "MRR")
	assert.Contains(t, string(body), "45000.00")
}

func TestWorkspaceRenderWithSchemaParam(t *testing.T) {
	app := fiber.New()
	app.Get("/render", APIWorkspaceRender)

	// No schema param → falls back to APIWorkspaceSchema (JSON)
	req := httptest.NewRequest("GET", "/render", nil)
	resp, err := app.Test(req)
	assert.NoError(t, err)
	assert.Equal(t, 200, resp.StatusCode)
	body, _ := io.ReadAll(resp.Body)
	assert.Contains(t, string(body), "revenue-health")
}
