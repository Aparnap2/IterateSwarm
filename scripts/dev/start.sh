#!/usr/bin/env bash
#===============================================================================
# OntologyAI V6 — One-command local dev bootstrap.
#
# Sequentially:
#   1. MiniSky (GCP control plane emulator)  — optional, external
#   2. Docker Compose (Neo4j, Postgres, Temporal, Redpanda, Redis, ...)
#   3. Mockoon CLI (Slack/Jira/Salesforce/Notion on :3001-:3004)
#   4. DB migrations (apps/core/migrations/*.sql, idempotent)
#   5. Seed fixtures (scripts/seed_data.sql + scripts/demo_seed.py if present)
#   6. Health checks + status table
#
# Idempotent: safe to re-run.
# Usage:  bash scripts/dev/start.sh
#===============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✅ $1${NC}"; }
warn() { echo -e "${YELLOW}  ⚠️  $1${NC}"; }
err()  { echo -e "${RED}  ❌ $1${NC}"; }
info() { echo -e "${BLUE}[INFO]${NC} $1"; }

# ── Config (overridable via env) ──────────────────────────────────────────────
MINISKY_API="${MINISKY_API:-http://localhost:8080}"
MINISKY_CONSOLE="${MINISKY_CONSOLE:-http://localhost:8081}"
POSTGRES_HOST_PORT="${POSTGRES_HOST_PORT:-5433}"
POSTGRES_USER="${POSTGRES_USER:-iterateswarm}"
POSTGRES_DB="${POSTGRES_DB:-iterateswarm}"
POSTGRES_CONTAINER="iterateswarm-postgres"
MOCKOON_PORTS=(3001 3002 3003 3004)
LANGFUSE_HOST="${LANGFUSE_HOST:-http://localhost:3000}"

# ── Helpers ───────────────────────────────────────────────────────────────────
http_up() { # any HTTP response (incl. 404/error) means the server is listening
    local url="$1"
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "$url" 2>/dev/null || echo "000")
    [ "$code" != "000" ]
}

tcp_up() { # raw TCP connect
    local host="$1" port="$2"
    (exec 3<>"/dev/tcp/$host/$port") 2>/dev/null && { exec 3>&- 3<&-; return 0; } || return 1
}

wait_for() { # wait_for <desc> <seconds> <cmd...>
    local desc="$1" secs="$2"; shift 2
    for _ in $(seq 1 "$secs"); do
        if "$@" >/dev/null 2>&1; then return 0; fi
        sleep 1
    done
    return 1
}

# ───────────────────────────────────────────────────────────────────────────────
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║        OntologyAI V6 — LOCAL DEV BOOTSTRAP (start.sh)            ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""

# ── 1. MiniSky (GCP control plane emulator) ──────────────────────────────────
echo "── [1/6] MiniSky (GCP control plane) ──────────────────────────────"
if http_up "$MINISKY_API" || http_up "$MINISKY_CONSOLE"; then
    ok "MiniSky detected (API $MINISKY_API / console $MINISKY_CONSOLE)"
else
    warn "MiniSky not detected on $MINISKY_API / $MINISKY_CONSOLE."
    warn "  Start it manually (e.g. 'miniskay start' or your local GCP emulator),"
    warn "  then re-run this script. Continuing without it (non-fatal)."
fi
echo ""

# ── 2. Docker Compose ─────────────────────────────────────────────────────────
echo "── [2/6] Docker Compose (Neo4j, Postgres, Temporal, Redpanda, Redis) ──"
if ! command -v docker >/dev/null 2>&1; then
    err "docker not found. Install Docker and re-run."
    exit 1
fi
docker compose -f "$PROJECT_ROOT/docker-compose.yml" up -d
echo "  docker compose up -d complete."
echo ""

# ── 3. Mockoon (Slack / Jira / Salesforce / Notion) ──────────────────────────
echo "── [3/6] Mockoon CLI (:3001-:3004) ────────────────────────────────"
if [ -f "$PROJECT_ROOT/scripts/start-mockoon.sh" ]; then
    bash "$PROJECT_ROOT/scripts/start-mockoon.sh" || {
        warn "Mockoon start reported a failure (see above). Continuing (non-fatal)."
    }
else
    warn "scripts/start-mockoon.sh not found — skipping Mockoon."
fi
echo ""

# ── 4. DB Migrations ─────────────────────────────────────────────────────────
echo "── [4/6] DB Migrations (apps/core/migrations) ─────────────────────"
run_migrations() {
    local mig_dir="$PROJECT_ROOT/apps/core/migrations"
    if [ ! -d "$mig_dir" ]; then
        warn "No migrations dir at apps/core/migrations — skipping."
        return 0
    fi
    # Ensure tracking table exists (idempotent).
    docker exec -i "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -q \
        -c "CREATE TABLE IF NOT EXISTS schema_migrations (filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT now());" \
        >/dev/null 2>&1 || { warn "Could not init schema_migrations table — skipping migrations."; return 0; }

    local applied=0 skipped=0
    for f in "$mig_dir"/*.sql; do
        [ -f "$f" ] || continue
        local name; name="$(basename "$f")"
        if docker exec -i "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
            "SELECT 1 FROM schema_migrations WHERE filename='$name'" 2>/dev/null | grep -q 1; then
            skipped=$((skipped + 1))
            continue
        fi
        if docker exec -i "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -q -v ON_ERROR_STOP=1 -f - < "$f" \
            && docker exec -i "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -q \
                -c "INSERT INTO schema_migrations (filename) VALUES ('$name') ON CONFLICT DO NOTHING;" >/dev/null 2>&1; then
            ok "applied $name"
            applied=$((applied + 1))
        else
            warn "migration $name failed (may already be applied) — continuing."
        fi
    done
    info "Migrations: $applied applied, $skipped already applied."
}
run_migrations
echo ""

# ── 5. Seed Fixtures ─────────────────────────────────────────────────────────
echo "── [5/6] Seed Fixtures ───────────────────────────────────────────────"
seed_fixtures() {
    local seeded=0
    if [ -f "$PROJECT_ROOT/scripts/seed_data.sql" ]; then
        if docker exec -i "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f - < "$PROJECT_ROOT/scripts/seed_data.sql" >/dev/null 2>&1; then
            ok "seed_data.sql applied"
            seeded=1
        else
            warn "seed_data.sql failed (tables may not exist yet) — continuing."
        fi
    fi
    if [ -f "$PROJECT_ROOT/scripts/demo_seed.py" ]; then
        if command -v uv >/dev/null 2>&1; then
            (cd "$PROJECT_ROOT/apps/ai" && uv run python "$PROJECT_ROOT/scripts/demo_seed.py") \
                && ok "demo_seed.py applied" || warn "demo_seed.py failed (may need Qdrant/Ollama) — continuing."
        else
            warn "uv not found — skipping demo_seed.py."
        fi
    fi
    [ "$seeded" -eq 1 ] || warn "No seed_data.sql applied — check postgres is up."
}
seed_fixtures
echo ""

# ── 6. Health Checks + Status Table ──────────────────────────────────────────
echo "── [6/6] Health Checks ───────────────────────────────────────────────"
declare -a ROWS=()
declare -a FAIL=()

check() { # check <name> <port> <tcp|http> <url>
    local name="$1" port="$2" kind="$3" url="${4:-}"
    local status
    if [ "$kind" = "tcp" ]; then
        if tcp_up localhost "$port"; then status="✅ up"; else status="❌ down"; FAIL+=("$name"); fi
    else
        if http_up "$url"; then status="✅ up"; else status="❌ down"; FAIL+=("$name"); fi
    fi
    ROWS+=("$name|:$port|$status")
}

# Wait for core services to become healthy (bounded).
info "Waiting for core services to be ready (up to 90s)..."
wait_for "postgres" 60 docker exec "$POSTGRES_CONTAINER" pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" || true
wait_for "neo4j"    60 tcp_up localhost 7687 || true
wait_for "temporal" 60 tcp_up localhost 7233 || true
wait_for "redpanda" 60 tcp_up localhost 9094 || true
wait_for "redis"    60 tcp_up localhost 6379 || true

check "PostgreSQL" 5433 tcp
check "Neo4j"       7687 tcp
check "Temporal"    7233 tcp
check "Redpanda"    9094 tcp
check "Redis"       6379 tcp
check "Langfuse"    3000 http "$LANGFUSE_HOST" || true   # optional
check "MiniSky"     8080 http "$MINISKY_API" || true     # optional/external
for p in "${MOCKOON_PORTS[@]}"; do
    check "Mockoon :$p" "$p" http "http://localhost:$p/" || true
done

echo ""
echo "┌────────────────────────────────────────────────────────────────┐"
echo "│                    SERVICE STATUS TABLE                        │"
echo "├────────────────────────────────────────────────────────────────┤"
printf "  %-22s %-10s %s\n" "SERVICE" "PORT" "STATUS"
echo "  ──────────────────────────────────────────────────────────────"
for row in "${ROWS[@]}"; do
    IFS='|' read -r name port status <<< "$row"
    printf "  %-22s %-10s %s\n" "$name" "$port" "$status"
done
echo "└────────────────────────────────────────────────────────────────┘"
echo ""

# ── Final verdict ────────────────────────────────────────────────────────────
CORE_FAIL=0
for svc in PostgreSQL Neo4j Temporal Redpanda Redis; do
    for f in "${FAIL[@]:-}"; do
        [ "$f" = "$svc" ] && CORE_FAIL=1
    done
done

if [ "$CORE_FAIL" -eq 0 ]; then
    echo -e "${GREEN}══════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  ✅ READY — all core services healthy.${NC}"
    echo -e "${GREEN}══════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "  Temporal UI:  http://localhost:8088"
    echo "  Neo4j:        http://localhost:7474"
    echo "  Grafana:      http://localhost:3001"
    echo "  MiniSky API:  $MINISKY_API"
    echo "  MiniSky UI:   $MINISKY_CONSOLE"
    echo ""
    exit 0
else
    echo -e "${RED}  ❌ NOT READY — core services down: ${FAIL[*]}${NC}"
    echo "  Run 'bash scripts/dev/verify.sh' for details."
    exit 1
fi