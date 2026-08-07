#!/usr/bin/env bash
#
# chaos_smoke.sh - Chaos smoke test for IterateSwarm core state services.
#
# Purpose:
#   Restart the two stateful core services (PostgreSQL + Temporal) and verify
#   they come back healthy. This simulates a crash/restart of the persistence
#   layer and confirms the compose stack recovers without manual intervention.
#
# Targets:
#   - postgres  (compose service; container name is auto-resolved)
#   - temporal  (compose service; container name is auto-resolved)
#
# Usage:
#   bash scripts/hardening/chaos_smoke.sh
#
# Exit codes:
#   0  all restarted services healthy
#   1  one or more services failed to restart / become healthy
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.yml"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=============================================="
echo "IterateSwarm Chaos Smoke Test"
echo "=============================================="
echo ""

# Resolve the actual container name for a compose service (robust to
# compose project-name prefixes / hash-prefixed names).
resolve_container() {
    local service="$1"
    local cid
    cid=$(docker compose -f "$COMPOSE_FILE" ps -q "$service" 2>/dev/null || true)
    if [ -n "$cid" ]; then
        docker inspect -f '{{.Name}}' "$cid" 2>/dev/null | tr -d '/'
    else
        echo ""
    fi
}

# Wait up to N seconds for a container to report healthy.
wait_healthy() {
    local name="$1"
    local timeout="${2:-90}"
    local waited=0
    while [ "$waited" -lt "$timeout" ]; do
        local state
        state=$(docker inspect -f '{{.State.Health.Status}}' "$name" 2>/dev/null || echo "unknown")
        if [ "$state" = "healthy" ]; then
            return 0
        fi
        # No healthcheck defined -> fall back to running state.
        if [ "$state" = "unknown" ]; then
            local running
            running=$(docker inspect -f '{{.State.Running}}' "$name" 2>/dev/null || echo "false")
            if [ "$running" = "true" ]; then
                return 0
            fi
        fi
        sleep 2
        waited=$((waited + 2))
    done
    return 1
}

# --- Snapshot before ---
echo "--- Containers BEFORE restart ---"
docker ps --format 'table {{.Names}}\t{{.Status}}'
echo ""

# --- Resolve target containers ---
POSTGRES_NAME="$(resolve_container postgres)"
TEMPORAL_NAME="$(resolve_container temporal)"

if [ -z "$POSTGRES_NAME" ]; then
    echo -e "${RED}✗ Could not resolve postgres container (is it running?)${NC}"
    exit 1
fi
if [ -z "$TEMPORAL_NAME" ]; then
    echo -e "${RED}✗ Could not resolve temporal container (is it running?)${NC}"
    exit 1
fi

echo "Restart targets:"
echo "  postgres -> $POSTGRES_NAME"
echo "  temporal -> $TEMPORAL_NAME"
echo ""

# --- Restart ---
echo "Restarting $POSTGRES_NAME and $TEMPORAL_NAME ..."
docker restart "$POSTGRES_NAME" "$TEMPORAL_NAME" >/dev/null
echo "Restart issued."
echo ""

# --- Wait for health ---
FAIL=0

echo -n "Waiting for $POSTGRES_NAME healthy ... "
if wait_healthy "$POSTGRES_NAME"; then
    echo -e "${GREEN}✓ HEALTHY${NC}"
else
    echo -e "${RED}✗ NOT HEALTHY${NC}"
    FAIL=1
fi

echo -n "Waiting for $TEMPORAL_NAME healthy ... "
if wait_healthy "$TEMPORAL_NAME"; then
    echo -e "${GREEN}✓ HEALTHY${NC}"
else
    echo -e "${RED}✗ NOT HEALTHY${NC}"
    FAIL=1
fi

echo ""
echo "--- Containers AFTER restart ---"
docker ps --format 'table {{.Names}}\t{{.Status}}'
echo ""

if [ "$FAIL" -ne 0 ]; then
    echo -e "${RED}Chaos smoke test FAILED. Inspect logs:${NC}"
    echo "  docker logs $POSTGRES_NAME"
    echo "  docker logs $TEMPORAL_NAME"
    exit 1
fi

echo -e "${GREEN}Chaos smoke test PASSED: postgres + temporal recovered.${NC}"
exit 0