#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
V3_DIR="$(dirname "$SCRIPT_DIR")"

# Use virtual environment if available
if [ -f /tmp/v3-venv/bin/activate ]; then
    source /tmp/v3-venv/bin/activate
fi

PYTHON="$(which python3)"

echo "=========================================="
echo "  Voproshalych v3 — Test Suite"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

pass=0
fail=0

run_test() {
    local name="$1"
    shift
    echo -e "${BLUE}▸ $name${NC}"
    if "$@" 2>&1; then
        echo -e "${GREEN}  ✓ PASS${NC}"
        pass=$((pass + 1))
    else
        echo -e "${RED}  ✗ FAIL${NC}"
        fail=$((fail + 1))
    fi
    echo ""
}

# === 1. Unit tests ===
echo "---[ Unit Tests ]---"

run_test "agent-service: supervisor tests" \
    $PYTHON -m pytest "$V3_DIR/agent-service/tests/test_supervisor.py" -v --tb=short

run_test "agent-service: MCP client tests" \
    $PYTHON -m pytest "$V3_DIR/agent-service/tests/test_mcp_client.py" -v --tb=short

run_test "agent-service: streaming tests" \
    $PYTHON -m pytest "$V3_DIR/agent-service/tests/test_streaming.py" -v --tb=short

run_test "mcp-kb: qa client tests" \
    $PYTHON -m pytest "$V3_DIR/mcp-servers/tests/test_kb_client.py" -v --tb=short

# === 2. Import tests ===
echo "---[ Import Tests ]---"

run_test "agent-service: imports" \
    cd "$V3_DIR/agent-service" && $PYTHON -c "from src.main import app; print('OK')"

run_test "mcp-kb: imports" \
    cd "$V3_DIR/mcp-servers" && $PYTHON -c "from src.kb.server import mcp; print('OK')"

run_test "mcp-news: imports" \
    cd "$V3_DIR/mcp-servers" && $PYTHON -c "from src.public.news_server import mcp; print('OK')"

run_test "mcp-contacts: imports" \
    cd "$V3_DIR/mcp-servers" && $PYTHON -c "from src.public.contacts_server import mcp; print('OK')"

run_test "mcp-library: imports" \
    cd "$V3_DIR/mcp-servers" && $PYTHON -c "from src.public.library_server import mcp; print('OK')"

run_test "mcp-sveden: imports" \
    cd "$V3_DIR/mcp-servers" && $PYTHON -c "from src.public.sveden_server import mcp; print('OK')"

# === 3. Structure tests ===
echo "---[ Structure Tests ]---"

run_test "v3 directory structure" \
    test -d "$V3_DIR/agent-service/src/nodes" && \
    test -d "$V3_DIR/mcp-servers/src/kb" && \
    test -d "$V3_DIR/mcp-servers/src/public" && \
    test -f "$V3_DIR/docker-compose.yml" && \
    test -f "$V3_DIR/litellm/config.yaml" && \
    echo "All directories and files present"

run_test "Dockerfiles exist" \
    test -f "$V3_DIR/agent-service/Dockerfile" && \
    test -f "$V3_DIR/mcp-servers/Dockerfile.kb" && \
    test -f "$V3_DIR/mcp-servers/Dockerfile.public" && \
    echo "All Dockerfiles present"

# === Summary ===
echo "=========================================="
total=$((pass + fail))
echo -e "Results: ${GREEN}$pass passed${NC}, ${RED}$fail failed${NC}, $total total"
echo "=========================================="

if [ "$fail" -gt 0 ]; then
    exit 1
fi
