#!/usr/bin/env bash
# curl-based smoke tests for v3
# Run: bash scripts/test_curl.sh

set -euo pipefail
RED='\033[0;31m'; GREEN='\033[0;32m'; NC='\033[0m'
PASS=0; FAIL=0

ok()   { PASS=$((PASS+1)); echo -e "  ${GREEN}✓${NC} $1"; }
fail() { FAIL=$((FAIL+1)); echo -e "  ${RED}✗${NC} $1"; }

BASE="http://localhost:8001"

echo "---[ v3 Smoke Tests ]---"

# health
status=$(curl -sf -o /dev/null -w '%{http_code}' "$BASE/health" 2>/dev/null || true)
[[ "$status" == "200" ]] && ok "agent-service GET /health → 200" || fail "agent-service GET /health → $status"

# mcp tools list
body=$(curl -sf "$BASE/mcp/tools" 2>/dev/null || true)
if echo "$body" | grep -q '"tools"'; then
  ok "agent-service GET /mcp/tools → tools found"
else
  fail "agent-service GET /mcp/tools → no tools ($body)"
fi

# chat
body=$(curl -sf -X POST "$BASE/chat" \
  -H "Content-Type: application/json" \
  -d '{"query":"test"}' 2>/dev/null || true)
if echo "$body" | grep -q '"answer"'; then
  ok "agent-service POST /chat → JSON response"
else
  fail "agent-service POST /chat → unexpected ($body)"
fi

# MCP servers health
for svc in mcp-kb:9010 mcp-news:9011 mcp-contacts:9012 mcp-library:9013 mcp-sveden:9014; do
  name="${svc%%:*}"
  port="${svc##*:}"
  body=$(curl -sf "http://localhost:$port/api/v1/tools" \
    -X POST -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","method":"ping","id":1}' 2>/dev/null || true)
  if echo "$body" | grep -q '"result"'; then
    ok "$name POST /api/v1/tools → pong"
  else
    fail "$name POST /api/v1/tools → no response ($body)"
  fi
done

# LiteLLM
ltlm_status=$(curl -sf -o /dev/null -w '%{http_code}' "http://localhost:4000/health/readiness" 2>/dev/null || true)
[[ "$ltlm_status" == "200" ]] && ok "LiteLLM GET /health/readiness → 200" || fail "LiteLLM GET /health/readiness → $ltlm_status"

echo "---"
echo "Passed: $PASS | Failed: $FAIL"
[[ "$FAIL" -eq 0 ]] && exit 0 || exit 1
