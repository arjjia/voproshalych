#!/usr/bin/env python3
"""End-to-end smoke test for Voproshalych v3 full stack.

Usage:
    python scripts/smoke_test.py              # default — from host
    python scripts/smoke_test.py --verbose     # full response bodies
    python scripts/smoke_test.py --quick       # skip LLM calls
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime

import httpx

PASS = "✅"
FAIL = "❌"
SKIP = "⏭️"

TOTAL = 0
PASSED = 0
FAILED = 0
SKIPPED = 0


def ok(msg=""):
    global PASSED
    PASSED += 1
    print(f"  {PASS} {msg}")


def fail(msg=""):
    global FAILED
    FAILED += 1
    print(f"  {FAIL} {msg}")


def show(msg):
    print(f"  {PASS} {msg}")


def skip(msg=""):
    global SKIPPED
    SKIPPED += 1
    print(f"  {SKIP} {msg}")


def section(title):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


SERVICES = {
    "agent-service": {"port": 8001},
    "kb-service": {"port": 8005},
    "litellm": {"port": 4000},
    "lobe-chat": {"port": 3210},
    "postgres": {"port": 5433},
    "redis": {"port": 6380},
    "mcp-kb": {"port": 9010},
    "mcp-news": {"port": 9011},
    "mcp-contacts": {"port": 9012},
    "mcp-library": {"port": 9013},
    "mcp-sveden": {"port": 9014},
    "mcp-fetch": {"port": 9015},
}


def check_containers():
    section("1. Проверка контейнеров")
    result = subprocess.run(
        ["docker", "compose", "ps", "--format", "{{.Name}}\t{{.Status}}"],
        capture_output=True, text=True, timeout=15,
        cwd="/Users/masha/src/github.com/arjjia/voproshalych-personal/Submodules/voproshalych_v2/v3",
    )
    if result.returncode != 0:
        fail(f"docker compose ps failed: {result.stderr.strip()}")
        return {}

    running = {}
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("\t", 1)
        name = parts[0].replace("v3-", "")
        status = parts[1] if len(parts) > 1 else "unknown"
        running[name] = status
        if "Up" in status or "Healthy" in status:
            show(f"{name} — {status}")
        else:
            fail(f"{name} — {status}")
    return running


def health(url, name, expected_code=200):
    global TOTAL
    TOTAL += 1
    try:
        r = httpx.get(url, timeout=5)
        if r.status_code == expected_code:
            ok(f"{name} ({url})")
            return r.json() if r.text else {}
        else:
            fail(f"{name} ({url}) — status {r.status_code}")
            return None
    except Exception as e:
        fail(f"{name} ({url}) — {e}")
        return None


def check_health_endpoints():
    section("2. Health endpoints")

    health("http://localhost:8001/health", "agent-service")
    health("http://localhost:8005/health", "kb-service")
    health("http://localhost:4000/health/readiness", "litellm")

    for svc in ["mcp-kb", "mcp-news", "mcp-contacts", "mcp-library", "mcp-sveden", "mcp-fetch"]:
        health(f"http://localhost:{SERVICES[svc]['port']}/health", svc)


def check_lobechat():
    section("3. LobeChat доступен")
    global TOTAL
    TOTAL += 1
    try:
        r = httpx.get("http://localhost:3210/", timeout=10, follow_redirects=False)
        if r.status_code in (200, 302):
            loc = r.headers.get("location", "")
            ok(f"LobeChat на localhost:3210 — {r.status_code} → {loc}")
            return True
        else:
            fail(f"LobeChat — статус {r.status_code}")
            return False
    except Exception as e:
        fail(f"LobeChat — {e}")
        return False


def check_v1_models():
    section("4. /v1/models (через agent-service)")
    global TOTAL
    TOTAL += 1
    try:
        r = httpx.get("http://localhost:8001/v1/models", timeout=10)
        if r.status_code == 200:
            data = r.json()
            models = data.get("data", [])
            count = len(models)
            names = [m["id"] for m in models[:5]]
            ok(f"{count} моделей: {', '.join(names)}...")
        else:
            fail(f"status {r.status_code}: {r.text[:200]}")
    except Exception as e:
        fail(f"ошибка: {e}")


def check_v1_chat_completions(quick=False):
    section(f"5. /v1/chat/completions (через agent-service){' [SKIP — quick mode]' if quick else ''}")
    global TOTAL
    if quick:
        skip("quick mode")
        return
    TOTAL += 1
    try:
        r = httpx.post(
            "http://localhost:8001/v1/chat/completions",
            json={
                "model": "deepseek-v4-flash-free",
                "messages": [{"role": "user", "content": "Привет! Ответь одним словом: какой сегодня день?"}],
                "max_tokens": 50,
            },
            timeout=30,
        )
        if r.status_code == 200:
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            ok(f"Ответ получен ({len(content)} символов): {content[:80]}...")
        else:
            fail(f"status {r.status_code}: {r.text[:200]}")
    except Exception as e:
        fail(f"ошибка: {e}")


def check_chat_endpoint(quick=False):
    section(f"6. POST /chat (через agent-service){' [SKIP — quick mode]' if quick else ''}")
    global TOTAL
    if quick:
        skip("quick mode")
        return
    TOTAL += 1
    try:
        r = httpx.post(
            "http://localhost:8001/chat",
            json={
                "query": "Какая погода? Ответь одной фразой.",
                "user_id": "smoke-test",
                "role": "guest",
            },
            timeout=60,
        )
        if r.status_code == 200:
            data = r.json()
            answer = data.get("answer", "")
            ok(f"Ответ получен ({len(answer)} символов): {answer[:80]}...")
        else:
            fail(f"status {r.status_code}: {r.text[:200]}")
    except Exception as e:
        fail(f"ошибка: {e}")


def check_streaming(quick=False):
    section(f"7. GET /chat/stream (через agent-service){' [SKIP — quick mode]' if quick else ''}")
    global TOTAL
    if quick:
        skip("quick mode")
        return
    TOTAL += 1
    try:
        with httpx.Client(timeout=60) as client:
            with client.stream(
                "GET",
                "http://localhost:8001/chat/stream",
                params={"query": "Привет! Ответь одной фразой: 2+2?", "user_id": "smoke-test", "role": "guest"},
            ) as r:
                lines = 0
                for chunk in r.iter_lines():
                    if chunk.strip():
                        lines += 1
                ok(f"SSE поток: {lines} событий")
    except Exception as e:
        fail(f"ошибка: {e}")


def check_mcp_tools():
    section("8. MCP инструменты (agent-service /mcp/tools)")
    global TOTAL
    TOTAL += 1
    try:
        r = httpx.get("http://localhost:8001/mcp/tools", timeout=10)
        if r.status_code == 200:
            data = r.json()
            servers = data.get("servers", [])
            tool_count = sum(len(s.get("tools", [])) for s in servers)
            ok(f"{len(servers)} MCP серверов, {tool_count} инструментов")
            return data
        else:
            fail(f"status {r.status_code}")
    except Exception as e:
        fail(f"ошибка: {e}")


def check_jsonrpc(url, name, method="tools/list", params=None):
    global TOTAL
    TOTAL += 1
    try:
        r = httpx.post(
            url,
            json={"jsonrpc": "2.0", "method": method, "params": params or {}, "id": 1},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            result = data.get("result", data)
            ok(f"{name} — {method} OK")
            return result
        else:
            fail(f"{name} — status {r.status_code}: {r.text[:200]}")
    except Exception as e:
        fail(f"{name} — {e}")
    return None


def check_kb_tools():
    section("9. KB-service JSON-RPC инструменты")
    check_jsonrpc("http://localhost:8005/api/v1/tools", "kb-service: tools/list", "tools/list")
    check_jsonrpc("http://localhost:8005/api/v1/tools", "kb-service: ping", "ping")


def check_mcp_servers_jsonrpc():
    section("10. MCP серверы JSON-RPC")
    for svc in ["mcp-kb", "mcp-news", "mcp-contacts", "mcp-library", "mcp-sveden", "mcp-fetch"]:
        port = SERVICES[svc]["port"]
        check_jsonrpc(f"http://localhost:{port}/api/v1/tools", svc, "tools/list")


def main():
    parser = argparse.ArgumentParser(description="Voproshalych v3 smoke test")
    parser.add_argument("-v", "--verbose", action="store_true", help="show response bodies")
    parser.add_argument("-q", "--quick", action="store_true", help="skip LLM calls")
    args = parser.parse_args()

    global VERBOSE
    VERBOSE = args.verbose

    start = time.time()
    print(f"Smoke test v3 — {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"{'Quick mode' if args.quick else 'Full mode'}")

    running = check_containers()
    check_health_endpoints()
    check_lobechat()
    check_v1_models()
    check_v1_chat_completions(args.quick)
    check_chat_endpoint(args.quick)
    check_streaming(args.quick)
    check_mcp_tools()
    check_kb_tools()
    check_mcp_servers_jsonrpc()

    elapsed = time.time() - start

    print(f"\n{'=' * 60}")
    print(f"  Итог: {PASSED}/{TOTAL} passed, {FAILED} failed, {SKIPPED} skipped")
    print(f"  Время: {elapsed:.1f}с")
    print(f"{'=' * 60}")

    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
