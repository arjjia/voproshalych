"""Тесты MCP-клиента."""

import pytest


@pytest.mark.asyncio
async def test_mcp_client_list_tools(httpx_mock):
    """Проверяет list_tools."""
    from src.mcp_client import MCPClient

    httpx_mock.add_response(
        url="http://test:9010/api/v1/tools",
        method="POST",
        json={
            "jsonrpc": "2.0",
            "result": {
                "tools": [
                    {"name": "test_tool", "description": "A test tool"}
                ]
            },
            "id": 1,
        },
    )

    client = MCPClient("http://test:9010")
    tools = await client.list_tools()
    assert len(tools) == 1
    assert tools[0]["name"] == "test_tool"


@pytest.mark.asyncio
async def test_mcp_client_call_tool(httpx_mock):
    """Проверяет call_tool."""
    from src.mcp_client import MCPClient

    httpx_mock.add_response(
        url="http://test:9010/api/v1/tools",
        method="POST",
        json={
            "jsonrpc": "2.0",
            "result": {
                "content": [{"type": "text", "text": "result"}]
            },
            "id": 1,
        },
    )

    client = MCPClient("http://test:9010")
    result = await client.call_tool("test", {"arg": "val"})
    assert result is not None
    assert result["content"][0]["text"] == "result"


@pytest.mark.asyncio
async def test_mcp_client_call_tool_error():
    """Проверяет обработку ошибок при вызове."""
    from src.mcp_client import MCPClient

    client = MCPClient("http://nonexistent:9010", timeout=1)
    result = await client.call_tool("test", {})
    assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
