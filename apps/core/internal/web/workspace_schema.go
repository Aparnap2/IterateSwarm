package web

import (
	"encoding/json"
	"fmt"
	"time"

	"github.com/gofiber/fiber/v2"
)

// WorkspaceSchema is the typed JSON contract produced by the Python Decision Runtime.
// The Go HTMX renderer renders this schema — no backend logic coupled to UI.
type WorkspaceSchema struct {
	Workspace   string         `json:"workspace"`
	Title       string         `json:"title"`
	TenantID    string         `json:"tenant_id"`
	MissionID   *string        `json:"mission_id,omitempty"`
	Components  []Component    `json:"components"`
	Layout      LayoutSpec     `json:"layout"`
	Permissions WorkspacePerms `json:"permissions"`
	State       map[string]any `json:"state,omitempty"`
	UpdatedAt   *string        `json:"updated_at,omitempty"`
}

type LayoutSpec struct {
	GridCols   int    `json:"grid_cols"`
	Gap        string `json:"gap"`
	Responsive bool   `json:"responsive"`
}

type WorkspacePerms struct {
	CanView    bool `json:"can_view"`
	CanEdit    bool `json:"can_edit"`
	CanExecute bool `json:"can_execute"`
	CanApprove bool `json:"can_approve"`
}

type Component struct {
	ID          string         `json:"id"`
	Type        string         `json:"type"`
	Title       string         `json:"title,omitempty"`
	Props       map[string]any `json:"props,omitempty"`
	State       ComponentState `json:"state,omitempty"`
	Layout      map[string]any `json:"layout,omitempty"`
	Permissions []string       `json:"permissions,omitempty"`
	EvidenceIDs []string       `json:"evidence_ids,omitempty"`
}

type ComponentState struct {
	Loading bool   `json:"loading"`
	Error   string `json:"error,omitempty"`
	Version string `json:"version"`
}

// ComponentRenderer renders a single component as HTMX fragment.
type ComponentRenderer interface {
	Render(c *fiber.Ctx, comp Component) error
}

var componentRegistry = map[string]ComponentRenderer{}

// RegisterRenderer adds a component renderer to the registry.
func RegisterRenderer(compType string, renderer ComponentRenderer) {
	componentRegistry[compType] = renderer
}

// RenderWorkspace renders a full workspace schema as HTMX.
func RenderWorkspace(c *fiber.Ctx, schema WorkspaceSchema) error {
	html := fmt.Sprintf(`<div id="workspace-%s" class="workspace-container" data-workspace="%s">`,
		schema.Workspace, schema.Workspace)
	html += fmt.Sprintf(`<h2 class="workspace-title">%s</h2>`, schema.Title)

	for _, comp := range schema.Components {
		html += fmt.Sprintf(`<div id="comp-%s" class="component %s">`, comp.ID, comp.Type)
		html += fmt.Sprintf(`<h3 class="component-title">%s</h3>`, comp.Title)
		html += renderProps(comp.Props)
		html += `</div>`
	}

	html += `</div>`
	return c.SendString(html)
}

func renderProps(props map[string]any) string {
	if len(props) == 0 {
		return ""
	}
	html := `<div class="component-props">`
	for k, v := range props {
		html += fmt.Sprintf(`<div class="prop" data-prop="%s">`, k)
		switch val := v.(type) {
		case string:
			html += fmt.Sprintf(`<span class="prop-value">%s</span>`, escapeHTML(val))
		case float64:
			html += fmt.Sprintf(`<span class="prop-value">%.2f</span>`, val)
		case bool:
			html += fmt.Sprintf(`<span class="prop-value">%t</span>`, val)
		case []any:
			html += `<ul class="prop-list">`
			for _, item := range val {
				html += fmt.Sprintf(`<li>%v</li>`, escapeHTML(fmt.Sprintf("%v", item)))
			}
			html += `</ul>`
		default:
			html += fmt.Sprintf(`<span class="prop-value">%v</span>`, escapeHTML(fmt.Sprintf("%v", v)))
		}
		html += `</div>`
	}
	html += `</div>`
	return html
}

func escapeHTML(s string) string {
	r := []byte(s)
	for i, b := range r {
		switch b {
		case '<':
			r[i] = '['
		case '>':
			r[i] = ']'
		}
	}
	return string(r)
}

// APIWorkspaceSchema returns the typed workspace schema as JSON.
func APIWorkspaceSchema(c *fiber.Ctx) error {
	now := time.Now().Format(time.RFC3339)
	schema := WorkspaceSchema{
		Workspace: "revenue-health",
		Title:     "Revenue Health Dashboard",
		TenantID:  c.Query("tenant_id", "default"),
		Components: []Component{
			{
				ID:    "revenue-card",
				Type:  "kpi_card",
				Title: "MRR",
				Props: map[string]any{"value": 45000, "currency": "USD"},
				State: ComponentState{Loading: false, Version: "v6"},
			},
		},
		Layout:      LayoutSpec{GridCols: 12, Gap: "2", Responsive: true},
		Permissions: WorkspacePerms{CanView: true, CanEdit: false, CanExecute: false, CanApprove: true},
		UpdatedAt:   &now,
	}
	return c.JSON(schema)
}

// APIWorkspaceRender renders the schema as HTMX HTML.
func APIWorkspaceRender(c *fiber.Ctx) error {
	raw := c.Query("schema")
	if raw == "" {
		return APIWorkspaceSchema(c)
	}

	var schema WorkspaceSchema
	if err := json.Unmarshal([]byte(raw), &schema); err != nil {
		return c.Status(400).JSON(fiber.Map{"error": "invalid schema"})
	}

	return RenderWorkspace(c, schema)
}
