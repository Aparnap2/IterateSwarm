package v6

// QueueGroup represents one of three Temporal task queue groups (ADR-007).
type QueueGroup string

const (
	QueuePipeline   QueueGroup = "ONTOLOGYAI-PIPELINE-QUEUE"
	QueueAgent      QueueGroup = "ONTOLOGYAI-AGENT-QUEUE"
	QueueValidation QueueGroup = "ONTOLOGYAI-VALIDATION-QUEUE"
)

// PipelineStage represents a named pipeline stage with its queue routing.
type PipelineStage string

const (
	StageIngest       PipelineStage = "pipeline.ingest"
	StageParse        PipelineStage = "pipeline.parse"
	StageNormalize    PipelineStage = "pipeline.normalize"
	StageDedupe       PipelineStage = "pipeline.dedupe"
	StageAliasResolve PipelineStage = "pipeline.alias_resolve"
	StageEntityBuild  PipelineStage = "pipeline.entity_build"
	StageConflictScan PipelineStage = "pipeline.conflict_scan"
	StageGraphUpdate  PipelineStage = "pipeline.graph_update"
	StageGapAnalysis  PipelineStage = "pipeline.gap_analysis"
	StageDecision     PipelineStage = "pipeline.decision"
	StageFeasibility  PipelineStage = "pipeline.feasibility"
	StageProjection   PipelineStage = "pipeline.projection"
	StageValidation   PipelineStage = "pipeline.validation"
	StagePublish      PipelineStage = "pipeline.publish"
)

// StageQueue returns which queue group a stage belongs to.
func StageQueue(s PipelineStage) QueueGroup {
	switch s {
	case StageIngest, StageParse, StageNormalize, StageDedupe,
		StageAliasResolve, StageEntityBuild, StageConflictScan,
		StageGraphUpdate, StageGapAnalysis, StageFeasibility:
		return QueuePipeline
	case StageDecision, StageProjection:
		return QueueAgent
	case StageValidation, StagePublish:
		return QueueValidation
	default:
		return QueuePipeline
	}
}
