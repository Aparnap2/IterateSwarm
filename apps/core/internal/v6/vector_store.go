package v6

import "context"

// Vector is a dense embedding vector. pgvector stores these in a `vector`
// column whose dimension is fixed by the embedding model in use (default 1536
// for OpenAI text-embedding-3-large; the schema DDL in vector_store_pg.go uses
// 384 as a conservative default and can be widened).
type Vector []float32

// VectorFilter constrains a vector search to a tenant and optional payload
// predicates. Implementations interpret Payload as exact equality / JSONB
// containment predicates on the stored payload (e.g. {"type": "feedback"}).
type VectorFilter struct {
	TenantID string
	Payload  map[string]any
}

// VectorSearchResult is a single hit from a vector search.
type VectorSearchResult struct {
	ID      string         `json:"id"`
	Score   float64        `json:"score"` // cosine similarity, 1.0 = identical
	Payload map[string]any `json:"payload"`
}

// VectorStore is the abstraction over the vector database.
//
// pgvector (Postgres) is the MVP implementation; Qdrant is optional behind
// this interface. Callers should depend on VectorStore and never on a concrete
// driver, so the backing store can be swapped without touching call sites.
// This mirrors the GraphStore contract in graph.go: the rest of the Go code
// should NEVER depend directly on a vector-database driver.
type VectorStore interface {
	// Upsert inserts or replaces the vector for (tenantID, id).
	Upsert(ctx context.Context, tenantID, id string, vector Vector, payload map[string]any) error

	// Search returns the top-k nearest vectors to query within tenantID,
	// optionally constrained by filter.Payload predicates.
	Search(ctx context.Context, tenantID string, query Vector, topK int, filter VectorFilter) ([]VectorSearchResult, error)

	// Delete removes the vector for (tenantID, id).
	Delete(ctx context.Context, tenantID, id string) error
}
