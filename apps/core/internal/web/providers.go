package web

import (
	"context"
)

// TimelineProvider returns timeline events for a tenant.
type TimelineProvider interface {
	GetEvents(ctx context.Context, tenantID string, days int) ([]map[string]interface{}, error)
}

// MetricsProvider returns business metrics for a tenant.
type MetricsProvider interface {
	GetMetrics(ctx context.Context, tenantID string) (map[string]interface{}, error)
}

// ChartDataProvider returns chart data for a tenant.
type ChartDataProvider interface {
	GetChartData(ctx context.Context, tenantID string, chartType string) (map[string]interface{}, error)
}

// AlertLineageProvider returns alert lineage data.
type AlertLineageProvider interface {
	GetLineage(ctx context.Context, tenantID, alertID string) ([]map[string]interface{}, error)
}

// TaskBoardProvider returns task board data.
type TaskBoardProvider interface {
	GetTaskBoard(ctx context.Context, tenantID string) (*TaskBoard, error)
}

// ProviderBundle groups all optional providers for dependency injection.
// Each field may be nil; nil fields fall back to DefaultProviders.
type ProviderBundle struct {
	Timeline     TimelineProvider
	Metrics      MetricsProvider
	ChartData    ChartDataProvider
	AlertLineage AlertLineageProvider
	TaskBoard    TaskBoardProvider
}
