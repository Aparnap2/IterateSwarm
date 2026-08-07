# Hardening — Chaos Smoke & Resource Limits

## chaos_smoke.sh
Restarts PostgreSQL + Temporal and verifies recovery after a persistence crash.
Run: `bash scripts/hardening/chaos_smoke.sh`
- Resolves names via `docker compose ps -q`; waits up to 90s for healthy.
- Exits non-zero on failure; prints `docker ps` before/after.

## Resource limits (docker-compose.yml)
neo4j 4G/2cpu, redpanda 2G/1cpu, temporal 1G/1cpu, postgres 512M/1cpu,
qdrant 512M/1cpu, victoriametrics 256M/0.5cpu. Metrics = VictoriaMetrics (no Prom/Grafana).

## Idempotency (no duplicate execution)
- `timeline_events`: UNIQUE (entity_type, entity_id, version)
- `mission_snapshots`: UNIQUE (mission_id, version) — see apps/ai/src/mission/timeline.py
