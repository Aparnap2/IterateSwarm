package memory

import (
	"context"

	"iterateswarm-core/internal/v6"
)

// QdrantClient is a legacy facade over the v6.VectorStore abstraction.
//
// Deprecated: prefer v6.VectorStore directly. pgvector (Postgres) is the MVP
// vector backend; Qdrant remains optional behind the v6.VectorStore interface.
// This type exists only so existing workflow activities keep compiling while
// the platform migrates off Qdrant — it no longer talks to a Qdrant driver.
type QdrantClient struct {
	store v6.VectorStore
}

// NewQdrantClientFromEnv creates a QdrantClient backed by an in-memory
// VectorStore. Swap in a real backend via SetVectorStore (e.g. a pgvector
// store) once an embedding generator is wired into the Go runtime.
func NewQdrantClientFromEnv() (*QdrantClient, error) {
	return &QdrantClient{store: v6.NewMemoryVectorStore()}, nil
}

// SetVectorStore swaps the underlying vector store.
func (c *QdrantClient) SetVectorStore(s v6.VectorStore) {
	if s != nil {
		c.store = s
	}
}

// Close closes the underlying store if it exposes a Close method.
func (c *QdrantClient) Close() {
	if closer, ok := c.store.(interface{ Close() }); ok {
		closer.Close()
	}
}

// EnsureCollection ensures the backing schema exists (pgvector extension/table).
func (c *QdrantClient) EnsureCollection(ctx context.Context) error {
	if ensurer, ok := c.store.(interface{ EnsureSchema(context.Context) error }); ok {
		return ensurer.EnsureSchema(ctx)
	}
	return nil
}

// CheckDuplicate checks for duplicate feedback. Without an embedding generator
// wired into the Go runtime there is no vector to compare, so this is a no-op
// that reports no duplicate (matching the legacy stub behaviour).
func (c *QdrantClient) CheckDuplicate(ctx context.Context, text string) (bool, float64, error) {
	return false, 0.0, nil
}

// IndexFeedback indexes feedback for duplicate detection. Without an embedding
// generator there is no vector to store, so this is a no-op. When an embedding
// model is available, route through c.store.Upsert.
func (c *QdrantClient) IndexFeedback(ctx context.Context, userID, text string, metadata map[string]interface{}) error {
	return nil
}
