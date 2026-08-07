package v6

import "time"

// EventType enumerates all canonical pipeline events.
type EventType string

const (
	EventEvidenceIngested    EventType = "evidence.ingested"
	EventEvidenceParsed      EventType = "evidence.parsed"
	EventEvidenceNormalized  EventType = "evidence.normalized"
	EventEntityResolved      EventType = "entity.resolved"
	EventConflictDetected    EventType = "conflict.detected"
	EventGraphUpdated        EventType = "knowledge_graph.updated"
	EventGapDetected         EventType = "gap.detected"
	EventDecisionCreated     EventType = "decision.created"
	EventFeasibilityComputed EventType = "feasibility.computed"
	EventArtifactProjected   EventType = "artifact.projected"
	EventValidationPassed    EventType = "validation.passed"
	EventValidationFailed    EventType = "validation.failed"
	EventWorkspacePublished  EventType = "workspace.published"
	EventPipelineError       EventType = "pipeline.error"
)

// Event is the base wrapper for all canonical events.
type Event struct {
	ID          string         `json:"id"`
	Type        EventType      `json:"type"`
	Version     int            `json:"version"`
	TenantID    string         `json:"tenant_id"`
	WorkspaceID string         `json:"workspace_id,omitempty"`
	Timestamp   time.Time      `json:"timestamp"`
	Payload     map[string]any `json:"payload"`
	TraceID     string         `json:"trace_id,omitempty"`
}

// EventPayloads — typed payloads for each event type.

type EvidenceIngestedPayload struct {
	EvidenceID  string  `json:"evidence_id"`
	Source      string  `json:"source"`
	SourceType  string  `json:"source_type"`
	Confidence  float64 `json:"confidence"`
	ContentHash string  `json:"content_hash"`
	Size        int     `json:"size"`
}

type EntityResolvedPayload struct {
	EntityID    string   `json:"entity_id"`
	EntityType  string   `json:"entity_type"`
	EvidenceIDs []string `json:"evidence_ids"`
	MergeMethod string   `json:"merge_method"`
	Confidence  float64  `json:"confidence"`
}

type ConflictDetectedPayload struct {
	ConflictID   string   `json:"conflict_id"`
	ConflictType string   `json:"conflict_type"`
	EvidenceIDs  []string `json:"evidence_ids"`
	EntityIDs    []string `json:"entity_ids"`
	Description  string   `json:"description"`
	Severity     string   `json:"severity"`
}

type FeasibilityComputedPayload struct {
	OptionID      string             `json:"option_id"`
	Dimensions    map[string]float64 `json:"dimensions"`
	WeightedTotal float64            `json:"weighted_total"`
	ReadinessTier string             `json:"readiness_tier"`
}

type ArtifactProjectedPayload struct {
	ArtifactID   string `json:"artifact_id"`
	ArtifactType string `json:"artifact_type"`
	WorkspaceID  string `json:"workspace_id"`
	Status       string `json:"status"`
	Version      int    `json:"version"`
}

type ValidationFailedPayload struct {
	ArtifactID string   `json:"artifact_id"`
	RuleID     string   `json:"rule_id"`
	Reason     string   `json:"reason"`
	Severity   string   `json:"severity"`
	Details    []string `json:"details,omitempty"`
}
