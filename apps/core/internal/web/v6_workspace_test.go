package web

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gofiber/fiber/v2"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"iterateswarm-core/internal/v6"
)

// Compile-time assertions: the web Handler implements v6.WorkspaceHandler, so
// the Founder Workspace (Milestone #5) can be wired into the /v6 registry
// without a circular import.
var (
	_ v6.WorkspaceHandler = (*Handler)(nil)
)

// newV6TestApp builds a Fiber app with the V6 routes wired through the web
// Handler (the real production wiring path in RegisterV6Routes).
func newV6TestApp() *fiber.App {
	app := fiber.New()
	h := NewHandler(nil, nil)
	h.RegisterV6Routes(app)
	return app
}

// ── Panels ───────────────────────────────────────────────────────────────────

func TestV6PanelsReturn200(t *testing.T) {
	app := newV6TestApp()
	for _, path := range []string{"/v6/morning-brief", "/v6/missions", "/v6/approvals", "/v6/timeline"} {
		req := httptest.NewRequest(http.MethodGet, path, nil)
		req.Header.Set("HX-Request", "true")
		resp, err := app.Test(req)
		require.NoError(t, err, "path %s", path)
		assert.Equal(t, http.StatusOK, resp.StatusCode, "path %s", path)
		resp.Body.Close()
	}
}

func TestV6PanelsRenderHTMXPartial(t *testing.T) {
	app := newV6TestApp()
	// With a nil DB every panel renders the empty state, which is the safe
	// degraded mode when the store is unavailable.
	for _, path := range []string{"/v6/morning-brief", "/v6/missions", "/v6/approvals", "/v6/timeline"} {
		req := httptest.NewRequest(http.MethodGet, path, nil)
		req.Header.Set("HX-Request", "true")
		resp, err := app.Test(req)
		require.NoError(t, err)
		body, err := io.ReadAll(resp.Body)
		require.NoError(t, err)
		resp.Body.Close()
		assert.Contains(t, string(body), "No ", "path %s should render an empty-state fragment", path)
	}
}

func TestV6PanelsReturnPlainTitleWithoutHTMX(t *testing.T) {
	app := newV6TestApp()
	for path, want := range map[string]string{
		"/v6/morning-brief": "Morning Brief",
		"/v6/missions":      "Missions",
		"/v6/approvals":     "Approvals",
		"/v6/timeline":      "Timeline",
	} {
		req := httptest.NewRequest(http.MethodGet, path, nil) // no HX-Request
		resp, err := app.Test(req)
		require.NoError(t, err)
		body, err := io.ReadAll(resp.Body)
		require.NoError(t, err)
		resp.Body.Close()
		assert.Equal(t, want, string(body), "path %s", path)
	}
}

// ── End-to-end: /v6/status through the web Handler ──────────────────────────

// TestV6StatusThroughWebHandler proves the Workspace wiring works end to end:
// the web Handler is registered as v6.WorkspaceHandler, the route registry is
// live, and the workspace panels count toward the implemented tally.
func TestV6StatusThroughWebHandler(t *testing.T) {
	app := newV6TestApp()
	req := httptest.NewRequest(http.MethodGet, "/v6/status", nil)
	resp, err := app.Test(req)
	require.NoError(t, err)
	defer resp.Body.Close()
	require.Equal(t, http.StatusOK, resp.StatusCode)

	var body map[string]any
	require.NoError(t, json.NewDecoder(resp.Body).Decode(&body))
	assert.Equal(t, float64(6), body["version"])
	assert.NotEmpty(t, body["branch"])

	rs, ok := body["route_status"].(map[string]any)
	require.True(t, ok)
	assert.Equal(t, float64(6), rs["implemented"]) // /health /status + 4 workspace panels
}

// ── Frozen workspace vocabulary ──────────────────────────────────────────────

func TestWorkspaceStatusLabel(t *testing.T) {
	cases := map[string]string{
		"pending":   "WAITING",
		"active":    "ACTIVE",
		"stalled":   "INVESTIGATING",
		"completed": "COMPLETED",
		"failed":    "FAILED",
		"archived":  "ARCHIVED", // no frozen verb → uppercased DB status
		"":          "",
	}
	for in, want := range cases {
		assert.Equal(t, want, workspaceStatusLabel(in), "input %q", in)
	}
}

func TestMissionEventToSSEEventName(t *testing.T) {
	assert.Equal(t, "MISSION_CREATED", missionEventToSSEEventName("created"))
	assert.Equal(t, "MISSION_CONFIDENCE_CHANGED", missionEventToSSEEventName("confidence_changed"))
}

func TestMissionSSEEventNames(t *testing.T) {
	names := missionSSEEventNames()
	assert.Len(t, names, len(missionEventTypes))
	for _, n := range names {
		assert.True(t, strings.HasPrefix(n, "MISSION_"), "expected MISSION_ prefix, got %q", n)
	}
	assert.Contains(t, names, "MISSION_CREATED")
	assert.Contains(t, names, "MISSION_ARCHIVED")
}

func TestMissionEventSummary(t *testing.T) {
	assert.Equal(t, "Mission created · FinanceAgent", missionEventSummary("created", "FinanceAgent"))
	assert.Equal(t, "Mission completed", missionEventSummary("completed", ""))
}

// ── Timeline SSE fragment escaping (project XSS rule) ───────────────────────

func TestRenderTimelineRowHTMLEscapesUserContent(t *testing.T) {
	frag := renderTimelineRowHTML(WorkspaceTimelineEvent{
		Time:     "09:00",
		SSEEvent: "MISSION_CREATED",
		Summary:  "<script>alert(1)</script>",
		Actor:    "<b>attacker</b>",
	})
	assert.NotContains(t, frag, "<script>")
	assert.Contains(t, frag, "&lt;script&gt;")
	assert.NotContains(t, frag, "<b>attacker</b>")
	assert.Contains(t, frag, "&lt;b&gt;attacker&lt;/b&gt;")
}

func TestRenderTimelineRowHTMLIncludesEventBadge(t *testing.T) {
	frag := renderTimelineRowHTML(WorkspaceTimelineEvent{
		Time:     "10:30",
		SSEEvent: "MISSION_APPROVED",
		Summary:  "Mission approved · ChiefOfStaff",
		Actor:    "ChiefOfStaff",
	})
	assert.Contains(t, frag, "MISSION_APPROVED")
	assert.Contains(t, frag, "Mission approved · ChiefOfStaff")
	assert.Contains(t, frag, "actor: ChiefOfStaff")
}
