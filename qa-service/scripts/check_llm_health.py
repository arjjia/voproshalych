"""Скрипт для проверки здоровья LLM провайдеров."""

import asyncio
import time
import httpx


async def check_mistral():
    """Проверить Mistral напрямую."""
    print("\n[1/3] Проверка Mistral...")
    try:
        from qa.llm.config import get_llm_config
        config = get_llm_config()
        api_key = config.mistral_api_key
        model = config.mistral_model

        if not api_key:
            return {"status": "unavailable", "message": "No API key", "latency_ms": 0, "error": None}

        start_time = time.time()
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                },
            )
            latency_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                return {"status": "ok", "message": "Mistral API is accessible", "latency_ms": latency_ms, "error": None}
            elif response.status_code == 401:
                return {"status": "unavailable", "message": "Invalid API key", "latency_ms": latency_ms, "error": "401"}
            else:
                return {"status": "error", "message": f"HTTP {response.status_code}", "latency_ms": latency_ms, "error": response.text[:200]}
    except Exception as e:
        return {"status": "error", "message": str(e), "latency_ms": 0, "error": str(e)}


async def check_openrouter():
    """Проверить OpenRouter (Nemotron) напрямую."""
    print("\n[2/3] Проверка OpenRouter (Nemotron)...")
    try:
        from qa.llm.config import get_llm_config
        config = get_llm_config()
        api_key = config.openrouter_api_key
        model = config.openrouter_models[0] if config.openrouter_models else "nvidia/nemotron-3-super-120b-a12b:free"

        if not api_key:
            return {"status": "unavailable", "message": "No API key", "latency_ms": 0, "error": None}

        start_time = time.time()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://voproshalych.utmn.ru",
                    "X-Title": "Voproshalych",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                },
            )
            latency_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                return {"status": "ok", "message": f"OpenRouter ({model}) is accessible", "latency_ms": latency_ms, "error": None}
            elif response.status_code == 401:
                return {"status": "unavailable", "message": "Invalid API key", "latency_ms": latency_ms, "error": "401"}
            else:
                return {"status": "error", "message": f"HTTP {response.status_code}", "latency_ms": latency_ms, "error": response.text[:200]}
    except Exception as e:
        return {"status": "error", "message": str(e), "latency_ms": 0, "error": str(e)}


async def check_gigachat():
    """Проверить GigaChat."""
    print("\n[3/3] Проверка GigaChat...")
    try:
        from qa.llm.config import get_llm_config
        config = get_llm_config()
        client_id = config.gigachat_client_id
        client_secret = config.gigachat_client_secret

        if not client_id or not client_secret:
            return {"status": "unavailable", "message": "No credentials", "latency_ms": 0, "error": None}

        import base64
        import json

        auth_key = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

        start_time = time.time()
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Get token
            token_response = await client.post(
                "https://gigachat.devices.sberbank.ru/api/v1/oauth",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                data={"scope": "GIGACHAT_API_PERS"},
            )
            latency_ms = int((time.time() - start_time) * 1000)

            if token_response.status_code == 200:
                return {"status": "ok", "message": "GigaChat API is accessible", "latency_ms": latency_ms, "error": None}
            elif token_response.status_code == 402:
                return {"status": "unavailable", "message": "Payment Required (no credits)", "latency_ms": latency_ms, "error": "402"}
            elif token_response.status_code == 401:
                return {"status": "unavailable", "message": "Invalid credentials", "latency_ms": latency_ms, "error": "401"}
            else:
                return {"status": "error", "message": f"HTTP {token_response.status_code}", "latency_ms": latency_ms, "error": token_response.text[:200]}
    except Exception as e:
        return {"status": "error", "message": str(e), "latency_ms": 0, "error": str(e)}


async def main():
    print("=" * 60)
    print("Проверка LLM провайдеров")
    print("=" * 60)

    results = {}

    # Mistral
    result = await check_mistral()
    results["mistral"] = result
    print(f"  Status: {result['status']}")
    print(f"  Message: {result['message']}")
    print(f"  Latency: {result['latency_ms']}ms")
    if result.get("error"):
        print(f"  Error: {result['error']}")

    # OpenRouter
    result = await check_openrouter()
    results["openrouter"] = result
    print(f"  Status: {result['status']}")
    print(f"  Message: {result['message']}")
    print(f"  Latency: {result['latency_ms']}ms")
    if result.get("error"):
        print(f"  Error: {result['error']}")

    # GigaChat
    result = await check_gigachat()
    results["gigachat"] = result
    print(f"  Status: {result['status']}")
    print(f"  Message: {result['message']}")
    print(f"  Latency: {result['latency_ms']}ms")
    if result.get("error"):
        print(f"  Error: {result['error']}")

    # Summary
    print("\n" + "=" * 60)
    print("Результаты:")
    print("=" * 60)
    for name, result in results.items():
        status_symbol = "✅" if result["status"] == "ok" else "❌" if result["status"] == "unavailable" else "⚠️"
        print(f"{status_symbol} {name}: {result['status']} ({result['latency_ms']}ms)")


if __name__ == "__main__":
    asyncio.run(main())