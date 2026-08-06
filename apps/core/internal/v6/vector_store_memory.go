package v6

import (
	"context"
	"math"
	"sort"
	"sync"
)

// memoryItem is a single stored vector in MemoryVectorStore.
type memoryItem struct {
	vector  Vector
	payload map[string]any
}

// MemoryVectorStore is an in-memory VectorStore used as a non-DB fallback
// (local development, tests, or when Postgres/pgvector is unavailable).
// It mirrors the in-memory fallback pattern used elsewhere in the codebase
// (e.g. the legacy Qdrant stub in internal/memory). Not safe for horizontal
// scaling — use PGVectorStore in production.
type MemoryVectorStore struct {
	mu    sync.RWMutex
	items map[string]map[string]memoryItem // tenantID -> id -> item
}

// NewMemoryVectorStore returns an empty in-memory VectorStore.
func NewMemoryVectorStore() *MemoryVectorStore {
	return &MemoryVectorStore{items: make(map[string]map[string]memoryItem)}
}

// Upsert stores the vector for (tenantID, id), replacing any existing entry.
func (s *MemoryVectorStore) Upsert(ctx context.Context, tenantID, id string, vector Vector, payload map[string]any) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.items[tenantID] == nil {
		s.items[tenantID] = make(map[string]memoryItem)
	}
	s.items[tenantID][id] = memoryItem{vector: vector, payload: payload}
	return nil
}

// Search returns the top-k nearest vectors by cosine similarity, optionally
// constrained by filter.Payload equality predicates.
func (s *MemoryVectorStore) Search(ctx context.Context, tenantID string, query Vector, topK int, filter VectorFilter) ([]VectorSearchResult, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	tenant := s.items[tenantID]
	if len(tenant) == 0 {
		return []VectorSearchResult{}, nil
	}

	results := make([]VectorSearchResult, 0, len(tenant))
	for id, item := range tenant {
		if !matchesFilter(item.payload, filter.Payload) {
			continue
		}
		results = append(results, VectorSearchResult{
			ID:      id,
			Score:   cosineSimilarity(query, item.vector),
			Payload: item.payload,
		})
	}

	// Highest similarity first.
	sort.Slice(results, func(i, j int) bool { return results[i].Score > results[j].Score })

	if topK > 0 && len(results) > topK {
		results = results[:topK]
	}
	return results, nil
}

// Delete removes the vector for (tenantID, id).
func (s *MemoryVectorStore) Delete(ctx context.Context, tenantID, id string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if tenant := s.items[tenantID]; tenant != nil {
		delete(tenant, id)
	}
	return nil
}

// matchesFilter reports whether payload satisfies all equality predicates.
func matchesFilter(payload, filter map[string]any) bool {
	for k, v := range filter {
		if payload[k] != v {
			return false
		}
	}
	return true
}

// cosineSimilarity returns the cosine similarity between two vectors.
// Returns 0 for empty or mismatched-dimension vectors.
func cosineSimilarity(a, b Vector) float64 {
	if len(a) == 0 || len(a) != len(b) {
		return 0
	}
	var dot, na, nb float64
	for i := range a {
		dot += float64(a[i]) * float64(b[i])
		na += float64(a[i]) * float64(a[i])
		nb += float64(b[i]) * float64(b[i])
	}
	if na == 0 || nb == 0 {
		return 0
	}
	return dot / (math.Sqrt(na) * math.Sqrt(nb))
}

// Compile-time assertion that MemoryVectorStore satisfies VectorStore.
var _ VectorStore = (*MemoryVectorStore)(nil)
