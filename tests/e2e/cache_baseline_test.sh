#!/usr/bin/env bash
# Cache Baseline E2E Test
# Runs tasks across different workflow types, then queries cache stats
set -euo pipefail

API_URL="${API_URL:-http://localhost:8080}"
TS=$(date +%s)

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

log() { echo -e "${CYAN}[$(date +%H:%M:%S)]${NC} $*"; }
ok()  { echo -e "${GREEN}✓${NC} $*"; }
warn(){ echo -e "${YELLOW}⚠${NC} $*"; }
fail(){ echo -e "${RED}✗${NC} $*"; }

TASK_IDS=()
TASK_LABELS=()

submit_task() {
    local label="$1"
    local payload="$2"
    local timeout="${3:-120}"

    log "Submitting: $label"
    local resp
    resp=$(curl -sS -X POST "$API_URL/api/v1/tasks" \
        -H "Content-Type: application/json" \
        -d "$payload" 2>&1) || { fail "curl failed for $label"; return 1; }

    local task_id
    task_id=$(echo "$resp" | jq -r '.task_id // .workflow_id // empty' 2>/dev/null) || true
    if [ -z "$task_id" ]; then
        fail "$label — no task_id in response: $(echo "$resp" | head -c 200)"
        return 1
    fi
    ok "$label → task_id=$task_id"
    TASK_IDS+=("$task_id")
    TASK_LABELS+=("$label")
}

poll_task() {
    local task_id="$1"
    local label="$2"
    local timeout="${3:-180}"
    local start=$SECONDS
    local status=""

    while (( SECONDS - start < timeout )); do
        status=$(curl -sS "$API_URL/api/v1/tasks/$task_id" 2>/dev/null \
            | jq -r '.status // empty' 2>/dev/null) || true
        case "$status" in
            COMPLETED|TASK_STATUS_COMPLETED)
                ok "$label completed ($(( SECONDS - start ))s)"
                return 0 ;;
            FAILED|TASK_STATUS_FAILED)
                fail "$label FAILED after $(( SECONDS - start ))s"
                return 1 ;;
            "")
                # Workflow might not be registered yet, retry silently
                ;;
        esac
        sleep 8
    done
    fail "$label timed out after ${timeout}s (last status: $status)"
    return 1
}

print_response_cache() {
    local task_id="$1"
    local label="$2"
    local resp
    resp=$(curl -sS "$API_URL/api/v1/tasks/$task_id" 2>/dev/null)

    local cache_read cache_create input_tokens
    cache_read=$(echo "$resp" | jq -r '.usage.cache_read_tokens // .metadata.usage.cache_read_tokens // 0' 2>/dev/null)
    cache_create=$(echo "$resp" | jq -r '.usage.cache_creation_tokens // .metadata.usage.cache_creation_tokens // 0' 2>/dev/null)
    input_tokens=$(echo "$resp" | jq -r '.usage.input_tokens // .metadata.usage.input_tokens // 0' 2>/dev/null)

    local total=$(( input_tokens + cache_read + cache_create ))
    local pct=0
    if [ "$total" -gt 0 ]; then
        pct=$(( cache_read * 100 / total ))
    fi

    echo -e "  ${label}: input=${input_tokens} cache_read=${cache_read} cache_write=${cache_create} hit=${pct}%"

    # Model breakdown
    echo "$resp" | jq -r '.metadata.model_breakdown[]? | "    \(.model): calls=\(.executions) cache_read=\(.cache_read_tokens // 0) cache_write=\(.cache_creation_tokens // 0)"' 2>/dev/null || true
}

# ============================================================
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  Cache Baseline E2E Test"
echo "  $(date)"
echo "═══════════════════════════════════════════════════════"
echo ""

# --- Test 1: Simple task (single-shot, no multi-turn) ---
submit_task "1-simple" "{
    \"query\": \"What are the main benefits of prompt caching in LLMs?\",
    \"session_id\": \"cache-e2e-simple-$TS\"
}"
sleep 2

# --- Test 2: Research (multi-agent, multi-phase) ---
submit_task "2-research" "{
    \"query\": \"Compare prompt caching strategies across major LLM providers\",
    \"session_id\": \"cache-e2e-research-$TS\",
    \"context\": {\"force_research\": true, \"research_strategy\": \"quick\"}
}"
sleep 2

# --- Test 3: Swarm (Lead + workers, most cache-intensive) ---
submit_task "3-swarm" "{
    \"query\": \"Write a brief analysis of caching strategies in distributed systems: in-memory vs disk-based vs CDN\",
    \"session_id\": \"cache-e2e-swarm-$TS\",
    \"context\": {\"force_swarm\": true}
}"

# ============================================================
echo ""
log "Waiting for tasks to complete..."
echo ""

FAILED=0
for i in "${!TASK_IDS[@]}"; do
    timeout=180
    # Swarm and research need more time
    case "${TASK_LABELS[$i]}" in
        3-swarm) timeout=600 ;;
        2-research) timeout=300 ;;
    esac
    poll_task "${TASK_IDS[$i]}" "${TASK_LABELS[$i]}" "$timeout" || FAILED=$((FAILED + 1))
done

# ============================================================
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  Cache Results (from API responses)"
echo "═══════════════════════════════════════════════════════"
echo ""

for i in "${!TASK_IDS[@]}"; do
    print_response_cache "${TASK_IDS[$i]}" "${TASK_LABELS[$i]}"
done

# ============================================================
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  Cache Results (from DB — per-agent detail)"
echo "═══════════════════════════════════════════════════════"
echo ""

# Query DB for detailed per-agent cache stats for these tasks
WORKFLOW_IDS=$(printf "'%s'," "${TASK_IDS[@]}")
WORKFLOW_IDS="${WORKFLOW_IDS%,}"  # trim trailing comma

docker compose -f deploy/compose/docker-compose.yml exec -T postgres psql -U shannon -d shannon -c "
SELECT
  te.query,
  tu.agent_id,
  tu.model,
  COUNT(*) as calls,
  SUM(COALESCE(tu.cache_read_tokens,0)) as cache_read,
  SUM(COALESCE(tu.cache_creation_tokens,0)) as cache_write,
  SUM(tu.prompt_tokens) as uncached,
  CASE WHEN SUM(tu.prompt_tokens + COALESCE(tu.cache_read_tokens,0) + COALESCE(tu.cache_creation_tokens,0)) > 0
    THEN ROUND(100.0 * SUM(COALESCE(tu.cache_read_tokens,0)) /
      SUM(tu.prompt_tokens + COALESCE(tu.cache_read_tokens,0) + COALESCE(tu.cache_creation_tokens,0)), 1)
    ELSE 0 END as hit_pct,
  ROUND(SUM(tu.cost_usd)::numeric, 4) as cost
FROM token_usage tu
JOIN task_executions te ON tu.task_id = te.id
WHERE te.workflow_id IN ($WORKFLOW_IDS)
GROUP BY te.query, tu.agent_id, tu.model
ORDER BY te.query, calls DESC;
" 2>/dev/null || warn "DB query failed"

# Summary
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  Overall Summary"
echo "═══════════════════════════════════════════════════════"
echo ""

docker compose -f deploy/compose/docker-compose.yml exec -T postgres psql -U shannon -d shannon -c "
SELECT
  LEFT(te.query, 40) as query,
  COUNT(tu.id) as llm_calls,
  SUM(COALESCE(tu.cache_read_tokens,0)) as cache_read,
  SUM(COALESCE(tu.cache_creation_tokens,0)) as cache_write,
  SUM(tu.prompt_tokens) as uncached,
  CASE WHEN SUM(tu.prompt_tokens + COALESCE(tu.cache_read_tokens,0) + COALESCE(tu.cache_creation_tokens,0)) > 0
    THEN ROUND(100.0 * SUM(COALESCE(tu.cache_read_tokens,0)) /
      SUM(tu.prompt_tokens + COALESCE(tu.cache_read_tokens,0) + COALESCE(tu.cache_creation_tokens,0)), 1)
    ELSE 0 END as hit_pct,
  ROUND(SUM(tu.cost_usd)::numeric, 4) as cost
FROM token_usage tu
JOIN task_executions te ON tu.task_id = te.id
WHERE te.workflow_id IN ($WORKFLOW_IDS)
GROUP BY te.query
ORDER BY llm_calls DESC;
" 2>/dev/null || warn "DB query failed"

echo ""
if [ "$FAILED" -gt 0 ]; then
    fail "$FAILED task(s) failed"
    exit 1
else
    ok "All tasks completed successfully"
fi
