#!/usr/bin/env bash
# Integration Tests Runner
# Executes all Shannon integration tests in sequence

set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-deploy/compose/docker-compose.yml}"
TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Utilities
pass() { echo -e "[\033[32mPASS\033[0m] $1"; }
fail() { echo -e "[\033[31mFAIL\033[0m] $1"; exit 1; }
info() { echo -e "[\033[34mINFO\033[0m] $1"; }
warn() { echo -e "[\033[33mWARN\033[0m] $1"; }

echo ""
echo "=========================================="
echo "Shannon Integration Tests Suite"
echo "=========================================="
echo "Test Directory: $TEST_DIR"
echo "Compose File: $COMPOSE_FILE"
echo "Start Time: $(date)"
echo "=========================================="

# Pre-flight checks
info "Running pre-flight system checks..."

# Check if services are running
REQUIRED_SERVICES=(
  "localhost:50051"  # Agent Core gRPC
  "localhost:50052"  # Orchestrator gRPC  
  "localhost:2112"   # Orchestrator metrics
  "localhost:5432"   # PostgreSQL (via Docker)
  "localhost:6379"   # Redis (via Docker)
)

for service in "${REQUIRED_SERVICES[@]}"; do
  host=${service%:*}
  port=${service#*:}
  if ! nc -z "$host" "$port" 2>/dev/null; then
    fail "Required service not available: $service"
  fi
done

# Quick health checks
curl -fsS http://localhost:2112/metrics > /dev/null || fail "Orchestrator metrics not responding"
pass "Pre-flight checks completed"
info "Vector search is disabled by default; optional Qdrant checks are not part of the default integration suite"

# Make test scripts executable
chmod +x "$TEST_DIR"/*.sh

# Track test results
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0
declare -a FAILED_TESTS=()

echo ""
echo "=========================================="
echo "Starting Integration Tests"
echo "=========================================="

# Test 1: Single Agent Flow
echo ""
info "🚀 Running Test 1: Single Agent Flow Integration Test"
echo "----------------------------------------"
if bash "$TEST_DIR/single_agent_flow_test.sh"; then
  ((TESTS_PASSED++))
  pass "Test 1: Single Agent Flow - PASSED"
else
  ((TESTS_FAILED++))
  FAILED_TESTS+=("Single Agent Flow")
  warn "Test 1: Single Agent Flow - FAILED"
fi
((TESTS_RUN++))

# Brief pause between tests
sleep 2

# Test 2: Session Memory 
echo ""
info "🧠 Running Test 2: Session Memory Integration Test"
echo "----------------------------------------"
if bash "$TEST_DIR/session_memory_test.sh"; then
  ((TESTS_PASSED++))
  pass "Test 2: Session Memory - PASSED"
else
  ((TESTS_FAILED++))
  FAILED_TESTS+=("Session Memory")
  warn "Test 2: Session Memory - FAILED"
fi
((TESTS_RUN++))

# Brief pause between tests
sleep 2

echo ""
echo "=========================================="
echo "Integration Test Suite Results"
echo "=========================================="
echo "End Time: $(date)"
echo ""
echo "Tests Run: $TESTS_RUN"
echo "Tests Passed: $TESTS_PASSED"
echo "Tests Failed: $TESTS_FAILED"
echo ""

if [ $TESTS_FAILED -gt 0 ]; then
  echo "Failed Tests:"
  for test in "${FAILED_TESTS[@]}"; do
    echo "  ❌ $test"
  done
  echo ""
fi

echo "Coverage: $(( (TESTS_PASSED * 100) / TESTS_RUN ))%"
echo ""

# Summary assessment
if [ $TESTS_PASSED -eq $TESTS_RUN ]; then
  pass "🎉 ALL INTEGRATION TESTS PASSED"
  echo ""
  echo "Shannon integration test suite completed successfully!"
  echo "Core functionality validated:"
  echo "  ✅ Single-agent task execution flow"
  echo "  ✅ Session persistence and memory continuity"
  echo ""
  exit 0
elif [ $TESTS_PASSED -gt 0 ]; then
  warn "⚠️  PARTIAL SUCCESS: $TESTS_PASSED/$TESTS_RUN tests passed"
  echo ""
  echo "Some functionality is working, but there are issues to address:"
  for test in "${FAILED_TESTS[@]}"; do
    echo "  🔧 Fix required: $test"
  done
  echo ""
  exit 1
else
  fail "❌ ALL INTEGRATION TESTS FAILED"
fi
