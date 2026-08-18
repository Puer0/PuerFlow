#!/usr/bin/env bash
# E2E test for user-level persistent memory (/memory mount)
# Tests the WASI sandbox path (local containers, not Firecracker)
#
# Prerequisites:
#   - Docker Compose services running (make dev)
#   - GATEWAY_SKIP_AUTH=1 in .env (or provide API key)
#
# Usage:
#   ./tests/e2e/test_user_memory.sh

set -euo pipefail

API_URL="${API_URL:-http://localhost:8080}"
API_KEY="${API_KEY:-}"
PASS=0
FAIL=0
TOTAL=0

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

log() { echo -e "${YELLOW}[TEST]${NC} $1"; }
pass() { PASS=$((PASS + 1)); TOTAL=$((TOTAL + 1)); echo -e "${GREEN}[PASS]${NC} $1"; }
fail() { FAIL=$((FAIL + 1)); TOTAL=$((TOTAL + 1)); echo -e "${RED}[FAIL]${NC} $1"; }

# Auth header
AUTH_HEADER=""
if [ -n "$API_KEY" ]; then
    AUTH_HEADER="-H \"X-API-Key: $API_KEY\""
fi

# Helper: submit task and wait for completion
submit_task() {
    local query="$1"
    local session_id="${2:-test-memory-$(date +%s)}"

    local response
    response=$(curl -sS -X POST "$API_URL/api/v1/tasks" \
        -H "Content-Type: application/json" \
        ${API_KEY:+-H "X-API-Key: $API_KEY"} \
        -d "{
            \"query\": \"$query\",
            \"session_id\": \"$session_id\",
            \"mode\": \"simple\"
        }" 2>&1)

    echo "$response"
}

# Helper: poll task until completion
poll_task() {
    local task_id="$1"
    local timeout="${2:-120}"
    local start=$(date +%s)

    while true; do
        local now=$(date +%s)
        local elapsed=$((now - start))
        if [ $elapsed -ge $timeout ]; then
            echo "TIMEOUT"
            return 1
        fi

        local status
        status=$(curl -sS "$API_URL/api/v1/tasks/$task_id" \
            ${API_KEY:+-H "X-API-Key: $API_KEY"} 2>&1)

        local state=$(echo "$status" | jq -r '.status // .state // "UNKNOWN"' 2>/dev/null)

        if [[ "$state" == *"COMPLETED"* ]] || [[ "$state" == *"completed"* ]]; then
            echo "$status"
            return 0
        elif [[ "$state" == *"FAILED"* ]] || [[ "$state" == *"failed"* ]]; then
            echo "$status"
            return 1
        fi

        sleep 2
    done
}

echo "========================================"
echo "User Memory E2E Tests"
echo "API: $API_URL"
echo "========================================"
echo ""

# Test 0: Health check
log "Test 0: Health check"
health=$(curl -sS "$API_URL/health" 2>&1)
if echo "$health" | jq -e '.status' >/dev/null 2>&1; then
    pass "Health check OK"
else
    fail "Health check failed: $health"
    echo "Services may not be running. Aborting."
    exit 1
fi

# Test 1: Verify SHANNON_USER_MEMORY_DIR is set in agent-core
log "Test 1: Check agent-core has SHANNON_USER_MEMORY_DIR"
mem_dir=$(docker compose -f deploy/compose/docker-compose.yml exec -T agent-core printenv SHANNON_USER_MEMORY_DIR 2>/dev/null || echo "NOT_SET")
if [ "$mem_dir" != "NOT_SET" ] && [ -n "$mem_dir" ]; then
    pass "SHANNON_USER_MEMORY_DIR=$mem_dir"
else
    fail "SHANNON_USER_MEMORY_DIR not set in agent-core"
fi

# Test 2: Verify SHANNON_USER_MEMORY_DIR is set in llm-service
log "Test 2: Check llm-service has SHANNON_USER_MEMORY_DIR"
mem_dir=$(docker compose -f deploy/compose/docker-compose.yml exec -T llm-service printenv SHANNON_USER_MEMORY_DIR 2>/dev/null || echo "NOT_SET")
if [ "$mem_dir" != "NOT_SET" ] && [ -n "$mem_dir" ]; then
    pass "SHANNON_USER_MEMORY_DIR=$mem_dir in llm-service"
else
    fail "SHANNON_USER_MEMORY_DIR not set in llm-service"
fi

# Test 3: Seed memory file via container, then read via tool API
# file_write is a dangerous tool (blocked from direct execution), so we seed
# the file directly into the shared volume and verify read path works.
log "Test 3: Seed /memory file and verify via file_read tool API"

# Determine the anonymous user_id (skip-auth fallback)
TEST_USER_ID="00000000-0000-0000-0000-000000000002"
COMPOSE_FILE="deploy/compose/docker-compose.yml"

# Seed file into shared volume
docker compose -f "$COMPOSE_FILE" exec -T agent-core sh -c \
    "mkdir -p /tmp/shannon-users/${TEST_USER_ID}/memory && \
     printf '# E2E Test Note\nThis is a test memory note from E2E testing.\n' \
     > /tmp/shannon-users/${TEST_USER_ID}/memory/test-note.md" 2>/dev/null

# Verify file exists in volume
SEEDED=$(docker compose -f "$COMPOSE_FILE" exec -T agent-core \
    cat /tmp/shannon-users/${TEST_USER_ID}/memory/test-note.md 2>/dev/null)
if echo "$SEEDED" | grep -q "E2E Test Note"; then
    pass "Memory file seeded in shared volume"
else
    fail "Failed to seed memory file"
fi

# Test 4: Read seeded file via file_read tool API (deterministic, no LLM)
log "Test 4: Read /memory/test-note.md via file_read tool API"
SESSION2="test-memory-read-$(date +%s)"
READ_RESP=$(curl -sS -X POST "$API_URL/api/v1/tools/file_read/execute" \
    -H "Content-Type: application/json" \
    ${API_KEY:+-H "X-API-Key: $API_KEY"} \
    -d "{
        \"arguments\": {
            \"path\": \"/memory/test-note.md\"
        },
        \"session_id\": \"$SESSION2\"
    }" 2>&1)
READ_SUCCESS=$(echo "$READ_RESP" | jq -r '.success // false' 2>/dev/null)
READ_CONTENT=$(echo "$READ_RESP" | jq -r '.output // empty' 2>/dev/null)

if [[ "$READ_SUCCESS" == "true" ]]; then
    if echo "$READ_CONTENT" | grep -qi "E2E Test Note"; then
        pass "Memory persisted — file_read returned seeded content via /memory mount"
    else
        log "Content: ${READ_CONTENT:0:200}"
        fail "file_read succeeded but content doesn't match seeded data"
    fi
else
    READ_ERR=$(echo "$READ_RESP" | jq -r '.error // empty' 2>/dev/null)
    fail "file_read from /memory failed: $READ_ERR"
fi

# Cleanup seeded test file
docker compose -f "$COMPOSE_FILE" exec -T agent-core \
    rm -f /tmp/shannon-users/${TEST_USER_ID}/memory/test-note.md 2>/dev/null

echo ""
echo "========================================"
echo "Results: $PASS passed, $FAIL failed (total: $TOTAL)"
echo "========================================"

[ $FAIL -eq 0 ] && exit 0 || exit 1
