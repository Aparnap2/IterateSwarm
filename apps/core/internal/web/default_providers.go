package web

import (
	"context"
)

// DefaultProviders implements all provider interfaces with hardcoded stub data,
// preserving the existing behavior when no real provider is injected.
type DefaultProviders struct{}

// GetEvents returns hardcoded timeline events matching the original APICommandTimeline stub data.
func (DefaultProviders) GetEvents(_ context.Context, _ string, _ int) ([]map[string]interface{}, error) {
	return []map[string]interface{}{
		{"Time": "08:03", "Title": "Stripe webhook accepted", "Description": "Invoice payment failure cluster appended to event bus."},
		{"Time": "08:07", "Title": "Finance watchlist fired", "Description": "FG-05 and FG-04 evaluated for alert-worthiness."},
		{"Time": "08:11", "Title": "Correlation raised severity", "Description": "Support spike correlated with onboarding failure step."},
		{"Time": "08:18", "Title": "Approval queued", "Description": "Draft investor-update mention requires founder approval."},
		{"Time": "08:29", "Title": "MissionState refreshed", "Description": "Compiled context rebuilt under 800-token limit."},
	}, nil
}

// GetMetrics returns hardcoded metrics matching the original APICommandMetrics stub data.
func (DefaultProviders) GetMetrics(_ context.Context, _ string) (map[string]interface{}, error) {
	return map[string]interface{}{
		"items": []map[string]interface{}{
			{"Label": "Average agent response", "Value": "1.8s", "Pill": "GOOD"},
			{"Label": "Approval turnaround", "Value": "6m 12s", "Pill": "OK"},
			{"Label": "False alert rate", "Value": "4.2%", "Pill": "LOW"},
			{"Label": "Context budget", "Value": "612 / 800 tokens", "Pill": "SAFE"},
		},
	}, nil
}

// GetChartData returns hardcoded chart data matching the original APICommandChartData stub data.
func (DefaultProviders) GetChartData(_ context.Context, _ string, _ string) (map[string]interface{}, error) {
	return map[string]interface{}{
		"labels": []string{"W1", "W2", "W3", "W4", "W5", "W6"},
		"datasets": []map[string]interface{}{
			{"label": "Mission Health", "data": []int{84, 82, 80, 79, 75, 72}, "borderColor": "#7dd3fc", "backgroundColor": "rgba(125,211,252,.12)", "fill": true, "tension": 0.34},
			{"label": "Risk Index", "data": []int{26, 29, 35, 38, 45, 52}, "borderColor": "#f59e0b", "backgroundColor": "rgba(245,158,11,.06)", "fill": false, "tension": 0.34},
			{"label": "Execution Drag", "data": []int{18, 22, 24, 29, 34, 39}, "borderColor": "#a78bfa", "backgroundColor": "rgba(167,139,250,.06)", "fill": false, "tension": 0.34},
		},
	}, nil
}

// GetLineage returns hardcoded alert lineage data matching the original APICommandAlertLineage stub data.
func (DefaultProviders) GetLineage(_ context.Context, _, _ string) ([]map[string]interface{}, error) {
	return []map[string]interface{}{
		{
			"PatternName":       "Burn Multiple Spike",
			"SourceMetrics":     "burn_multiple: 1.9x → 2.4x (72h window)",
			"MissionContext":    "Finance guardian flagged FG-02 threshold breach",
			"RaiseTimelineRisk": "High — 3 consecutive data points above 2.0x",
			"SuggestedActions": []map[string]interface{}{
				{"Label": "Pause non-critical spend", "Tier": "review"},
				{"Label": "Notify founder", "Tier": "auto"},
			},
		},
		{
			"PatternName":       "Cohort Churn Correlation",
			"SourceMetrics":     "churn_rate: 4.2% → 6.1%, cohort_30d: -12%",
			"MissionContext":    "BI analyst BG-04 risk emerging",
			"RaiseTimelineRisk": "Medium — single data point, monitoring",
			"SuggestedActions": []map[string]interface{}{
				{"Label": "Draft retention email", "Tier": "approve"},
				{"Label": "Flag for weekly review", "Tier": "auto"},
			},
		},
	}, nil
}

// GetTaskBoard returns an empty task board (hardcoded default when no DB-backed provider is injected).
func (DefaultProviders) GetTaskBoard(_ context.Context, _ string) (*TaskBoard, error) {
	return &TaskBoard{
		Queued:       []Task{},
		Analyzing:    []Task{},
		AwaitingHITL: []Task{},
		Completed:    []Task{},
	}, nil
}
