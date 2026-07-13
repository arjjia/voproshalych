"""Simple HTTP server for public data MCP servers.

Exposes POST /api/v1/tools for JSON-RPC calls.
Automatically selects the tool implementation based on MCP_SERVER_TYPE.
"""

import logging
import os

from fastapi import FastAPI, Request
import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
server_type = os.getenv("MCP_SERVER_TYPE", "")


def _get_tools_definition():
    """Возвращает список инструментов в зависимости от типа сервера."""
    if server_type == "news":
        return [
            {
                "name": "get_news",
                "description": "Получить последние новости ТюмГУ.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Количество новостей (1-20)", "default": 5}
                    },
                },
            },
            {
                "name": "get_events",
                "description": "Получить список ближайших мероприятий ТюмГУ.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Количество мероприятий (1-20)", "default": 5}
                    },
                },
            },
        ]
    elif server_type == "contacts":
        return [
            {
                "name": "search_contacts",
                "description": "Поиск контактов подразделений ТюмГУ: приёмная комиссия, деканат, пресс-служба.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Поисковый запрос (название подразделения)"}
                    },
                },
            }
        ]
    elif server_type == "library":
        return [
            {
                "name": "get_library_info",
                "description": "Получить информацию о библиотеке ТюмГУ: адрес, телефон, часы работы.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "get_library_services",
                "description": "Получить список услуг и сервисов библиотеки ТюмГУ.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "get_library_guides",
                "description": "Получить гайды по работе с библиотекой ТюмГУ.",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ]
    elif server_type == "sveden":
        return [
            {
                "name": "get_sveden_info",
                "description": "Поиск по разделу «Сведения об организации» ТюмГУ.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string", "description": "Тема запроса (руководство, структура, питание)"}
                    },
                },
            },
            {
                "name": "get_structure",
                "description": "Получить структуру и органы управления ТюмГУ.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "get_management",
                "description": "Получить информацию о руководстве ТюмГУ.",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ]
    elif server_type == "fetch":
        return [
            {
                "name": "fetch_url",
                "description": "Загрузить содержимое веб-страницы по URL. "
                "Возвращает очищенный текст страницы. "
                "Полезно, когда пользователь ссылается на конкретную страницу.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL страницы для загрузки"},
                        "max_length": {
                            "type": "integer",
                            "description": "Максимальная длина текста (500-50000)",
                            "default": 8000,
                        },
                    },
                    "required": ["url"],
                },
            },
        ]
    return []


@app.post("/api/v1/tools")
async def handle_tools(request: Request):
    body = await request.json()
    method = body.get("method", "")
    req_id = body.get("id", 1)

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "result": {"tools": _get_tools_definition()},
            "id": req_id,
        }

    elif method == "tools/call":
        params = body.get("params", {})
        name = params.get("name", "")
        args = params.get("arguments", {})
        return await _call_tool_impl(name, args, req_id)

    return {"jsonrpc": "2.0", "result": None, "id": req_id}


async def _call_tool_impl(name: str, args: dict, req_id: int) -> dict:
    """Вызывает реализацию инструмента в зависимости от типа сервера."""
    try:
        if server_type == "news":
            from .news_server import get_news, get_events

            if name == "get_news":
                text = await get_news(limit=args.get("limit", 5))
            elif name == "get_events":
                text = await get_events(limit=args.get("limit", 5))
            else:
                text = f"Unknown tool: {name}"

        elif server_type == "contacts":
            from .contacts_server import search_contacts

            if name == "search_contacts":
                text = await search_contacts(query=args.get("query", ""))
            else:
                text = f"Unknown tool: {name}"

        elif server_type == "library":
            from .library_server import get_library_info, get_library_services, get_library_guides

            if name == "get_library_info":
                text = await get_library_info()
            elif name == "get_library_services":
                text = await _call(get_library_services)
            elif name == "get_library_guides":
                text = await _call(get_library_guides)
            else:
                text = f"Unknown tool: {name}"

        elif server_type == "sveden":
            from .sveden_server import get_sveden_info, get_structure, get_management

            if name == "get_sveden_info":
                text = await get_sveden_info(topic=args.get("topic", ""))
            elif name == "get_structure":
                text = await get_structure()
            elif name == "get_management":
                text = await get_management()
            else:
                text = f"Unknown tool: {name}"

        elif server_type == "fetch":
            from .fetch_server import fetch_url

            if name == "fetch_url":
                text = await fetch_url(
                    url=args.get("url", ""),
                    max_length=args.get("max_length", 8000),
                )
            else:
                text = f"Unknown tool: {name}"

        else:
            text = f"Unknown server type: {server_type}"

        return {
            "jsonrpc": "2.0",
            "result": {"content": [{"type": "text", "text": text}]},
            "id": req_id,
        }

    except Exception as e:
        logger.error(f"tool {name} error: {e}")
        return {
            "jsonrpc": "2.0",
            "result": {"content": [{"type": "text", "text": f"Ошибка: {e}"}]},
            "id": req_id,
        }


@app.get("/health")
async def health():
    return {"status": "ok"}


async def _call(func, *args, **kwargs):
    """Вызывает sync или async функцию."""
    import inspect
    if inspect.iscoroutinefunction(func):
        return await func(*args, **kwargs)
    return func(*args, **kwargs)


if __name__ == "__main__":
    port = int(os.getenv("MCP_PORT", "9010"))
    logger.info(f"Starting mcp-{server_type} on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
