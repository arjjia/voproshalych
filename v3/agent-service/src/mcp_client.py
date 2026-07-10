"""MCP-клиент для вызова инструментов на MCP-серверах через HTTP."""

import json
import logging

import httpx

logger = logging.getLogger(__name__)


class MCPClient:
    """HTTP-клиент для MCP-сервера (JSON-RPC over SSE transport)."""

    def __init__(self, base_url: str, timeout: int = 30):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def list_tools(self) -> list[dict]:
        """Получить список доступных инструментов."""
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "params": {},
            "id": 1,
        }
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self._timeout)) as client:
                response = await client.post(
                    f"{self._base_url}/api/v1/tools",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                return data.get("result", {}).get("tools", [])
        except Exception as e:
            logger.error(f"list_tools error for {self._base_url}: {e}")
            return []

    async def call_tool(self, name: str, arguments: dict | None = None) -> dict | None:
        """Вызвать инструмент на MCP-сервере.

        Args:
            name: Имя инструмента
            arguments: Аргументы вызова

        Returns:
            Результат вызова или None при ошибке
        """
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": arguments or {},
            },
            "id": 1,
        }

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self._timeout)) as client:
                response = await client.post(
                    f"{self._base_url}/api/v1/tools",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                data = response.json()

                if "error" in data:
                    logger.error(f"tool call error: {data['error']}")
                    return None

                return data.get("result")

        except httpx.TimeoutException:
            logger.error(f"tool {name} timeout after {self._timeout}s")
            return None
        except Exception as e:
            logger.error(f"tool {name} error: {e}")
            return None
