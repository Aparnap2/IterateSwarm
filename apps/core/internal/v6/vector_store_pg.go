package v6

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"
)

// vectorStoreSchemaDDL creates the pgvector extension and the vector_store
// table plus an HNSW index for cosine distance. All statements are idempotent
// (IF NOT EXISTS) so the DDL can be re-applied safely. The `<=>` operator is
// pgvector's cosine-distance operator; vector_cosine_ops is the matching
// operator class for the HNSW index.
//
// NOTE: run `CREATE EXTENSION IF NOT EXISTS vector;` (the first statement) on
// the target Postgres instance before first write. This DDL is validated in a
// later infra phase — it is intentionally not executed on startup.
const vectorStoreSchemaDDL = `
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS vector_store (
    id         TEXT NOT NULL,
    tenant_id  TEXT NOT NULL,
    embedding  vector(384),
    payload    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, id)
);

CREATE INDEX IF NOT EXISTS vector_store_embedding_hnsw_idx
    ON vector_store USING hnsw (embedding vector_cosine_ops);
`

// PGVectorStore is the pgvector-backed implementation of VectorStore.
// It talks to Postgres through database/sql and uses the pgvector `<=>`
// operator for cosine distance. It is the MVP vector backend.
type PGVectorStore struct {
	db *sql.DB
}

// NewPGVectorStore returns a VectorStore backed by pgvector on the given
// *sql.DB. The caller is responsible for ensuring the schema exists (see
// EnsureSchema) before first use.
func NewPGVectorStore(db *sql.DB) *PGVectorStore {
	return &PGVectorStore{db: db}
}

// EnsureSchema creates the vector extension and table if they do not exist.
// Safe to call multiple times.
func (s *PGVectorStore) EnsureSchema(ctx context.Context) error {
	if s.db == nil {
		return fmt.Errorf("pgvector store: no database connection configured")
	}
	if _, err := s.db.ExecContext(ctx, vectorStoreSchemaDDL); err != nil {
		return fmt.Errorf("pgvector store: ensure schema: %w", err)
	}
	return nil
}

// Upsert inserts or replaces the vector for (tenantID, id). The payload is
// stored as JSONB; ON CONFLICT makes the write idempotent per (tenant_id, id).
func (s *PGVectorStore) Upsert(ctx context.Context, tenantID, id string, vector Vector, payload map[string]any) error {
	if s.db == nil {
		return fmt.Errorf("pgvector store: no database connection configured")
	}
	payloadJSON, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("pgvector store: marshal payload: %w", err)
	}
	query := `
		INSERT INTO vector_store (tenant_id, id, embedding, payload, created_at, updated_at)
		VALUES ($1, $2, $3::vector, $4::jsonb, NOW(), NOW())
		ON CONFLICT (tenant_id, id) DO UPDATE SET
			embedding  = EXCLUDED.embedding,
			payload    = EXCLUDED.payload,
			updated_at = NOW()
	`
	if _, err := s.db.ExecContext(ctx, query, tenantID, id, vectorLiteral(vector), payloadJSON); err != nil {
		return fmt.Errorf("pgvector store: upsert %s/%s: %w", tenantID, id, err)
	}
	return nil
}

// Search returns the top-k nearest vectors to query within tenantID, ordered
// by cosine distance (ascending), so the returned Score is cosine similarity
// (1 - distance). Optional filter.Payload predicates are applied as JSONB
// containment (payload @> $n::jsonb) — parameterized, never string-concatenated.
func (s *PGVectorStore) Search(ctx context.Context, tenantID string, query Vector, topK int, filter VectorFilter) ([]VectorSearchResult, error) {
	if s.db == nil {
		return nil, fmt.Errorf("pgvector store: no database connection configured")
	}
	if topK <= 0 {
		topK = 10
	}

	// $1 = tenant_id, $2 = query vector (reused by ORDER BY).
	querySQL := `
		SELECT id, 1 - (embedding <=> $2::vector) AS score, payload
		FROM vector_store
		WHERE tenant_id = $1
	`
	args := []any{tenantID, vectorLiteral(query)}

	// Optional payload predicates via JSONB containment.
	if len(filter.Payload) > 0 {
		filterJSON, err := json.Marshal(filter.Payload)
		if err != nil {
			return nil, fmt.Errorf("pgvector store: marshal filter: %w", err)
		}
		args = append(args, filterJSON)
		querySQL += fmt.Sprintf(" AND payload @> $%d::jsonb", len(args))
	}

	args = append(args, topK)
	querySQL += fmt.Sprintf(`
		ORDER BY embedding <=> $2::vector
		LIMIT $%d
	`, len(args))

	rows, err := s.db.QueryContext(ctx, querySQL, args...)
	if err != nil {
		return nil, fmt.Errorf("pgvector store: search: %w", err)
	}
	defer rows.Close()

	results := make([]VectorSearchResult, 0)
	for rows.Next() {
		var r VectorSearchResult
		var payloadJSON []byte
		if err := rows.Scan(&r.ID, &r.Score, &payloadJSON); err != nil {
			return nil, fmt.Errorf("pgvector store: scan result: %w", err)
		}
		if err := json.Unmarshal(payloadJSON, &r.Payload); err != nil {
			return nil, fmt.Errorf("pgvector store: unmarshal payload: %w", err)
		}
		results = append(results, r)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("pgvector store: iterate results: %w", err)
	}
	return results, nil
}

// Delete removes the vector for (tenantID, id).
func (s *PGVectorStore) Delete(ctx context.Context, tenantID, id string) error {
	if s.db == nil {
		return fmt.Errorf("pgvector store: no database connection configured")
	}
	query := `DELETE FROM vector_store WHERE tenant_id = $1 AND id = $2`
	if _, err := s.db.ExecContext(ctx, query, tenantID, id); err != nil {
		return fmt.Errorf("pgvector store: delete %s/%s: %w", tenantID, id, err)
	}
	return nil
}

// vectorLiteral renders a Vector as a pgvector literal, e.g. "[0.1,0.2,0.3]".
// Passed as a parameter cast to ::vector so values are never inlined into SQL.
func vectorLiteral(v Vector) string {
	parts := make([]string, len(v))
	for i, f := range v {
		parts[i] = fmt.Sprintf("%g", f)
	}
	return "[" + strings.Join(parts, ",") + "]"
}

// Compile-time assertion that PGVectorStore satisfies VectorStore.
var _ VectorStore = (*PGVectorStore)(nil)
