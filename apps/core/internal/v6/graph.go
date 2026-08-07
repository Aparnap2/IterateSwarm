package v6

import (
	"context"
	"time"
)

// EntityNode represents a Neo4j entity node returned from graph queries.
type EntityNode struct {
	ID         string         `json:"id"`
	Type       string         `json:"type"`
	Labels     []string       `json:"labels"`
	Properties map[string]any `json:"properties"`
	Confidence float64        `json:"confidence"`
	CreatedAt  time.Time      `json:"created_at"`
}

// RelationshipEdge represents a typed relationship between two entity nodes.
type RelationshipEdge struct {
	ID         string         `json:"id"`
	Type       string         `json:"type"`
	SourceID   string         `json:"source_id"`
	TargetID   string         `json:"target_id"`
	Properties map[string]any `json:"properties"`
	Confidence float64        `json:"confidence"`
	CreatedAt  time.Time      `json:"created_at"`
}

// GraphTriple is a source-relationship-target triple for traversal results.
type GraphTriple struct {
	Source       EntityNode       `json:"source"`
	Relationship RelationshipEdge `json:"relationship"`
	Target       EntityNode       `json:"target"`
}

// GraphStore defines the Neo4j operations available to the rest of the system.
// The rest of Go code should NEVER depend directly on the Neo4j driver.
type GraphStore interface {
	// Node operations
	CreateNode(ctx context.Context, entityType string, id string, properties map[string]any) (*EntityNode, error)
	GetNode(ctx context.Context, id string) (*EntityNode, error)
	UpdateNode(ctx context.Context, id string, properties map[string]any) (*EntityNode, error)
	MergeNode(ctx context.Context, entityType string, id string, properties map[string]any) (*EntityNode, error)
	DeleteNode(ctx context.Context, id string) error

	// Relationship operations
	CreateRelationship(ctx context.Context, relType string, sourceID string, targetID string, properties map[string]any) (*RelationshipEdge, error)
	DeleteRelationship(ctx context.Context, sourceID string, relType string, targetID string) error

	// Query operations
	Traverse(ctx context.Context, startID string, relTypes []string, maxHops int) ([]GraphTriple, error)
	Query(ctx context.Context, cypher string, params map[string]any) ([]map[string]any, error)
	GetEntityGraph(ctx context.Context, entityID string, maxHops int) ([]GraphTriple, error)

	// Health
	Health(ctx context.Context) error
	Close(ctx context.Context) error
}

// Neo4jConfig holds connection parameters for the Neo4j driver.
type Neo4jConfig struct {
	URI      string `json:"uri"`
	Username string `json:"username"`
	Password string `json:"password"`
	Database string `json:"database"` // optional, for Neo4j 5.0+
}
