"""Simple HTTP server for mcp-kb (bridge to qa-service).

Exposes POST /api/v1/tools for JSON-RPC calls.
"""

import json
import logging
import os

from fastapi import FastAPI, Request
import uvicorn

from .qa_client import QAServiceClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

qa_client = QAServiceClient(
    base_url=os.getenv("QA_SERVICE_URL", "http://qa-service:8004"),
    timeout=int(os.getenv("QA_SERVICE_TIMEOUT_SECONDS", "300")),
)


@app.post("/api/v1/tools")
async def handle_tools(request: Request):
    body = await request.json()
    method = body.get("method", "")
    req_id = body.get("id", 1)

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "result": {
                "tools": [
                    {
                        "name": "kb_search",
                        "description": "Поиск информации в базе знаний ТюмГУ. "
                        "Используй для вопросов про университет: правила, стипендии, "
                        "факультеты, общежитие, документы, контакты, расписания, учебные программы.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string", "description": "Текст запроса"},
                                "workspace": {
                                    "type": "string",
                                    "description": "Пространство поиска",
                                    "enum": ["public", "applicant", "student", "staff"],
                                    "default": "public",
                                },
                            },
                            "required": ["query"],
                        },
                    }
                ]
            },
            "id": req_id,
        }

    elif method == "tools/call":
        params = body.get("params", {})
        name = params.get("name", "")
        args = params.get("arguments", {})
        query = args.get("query", "")
        workspace = args.get("workspace", "public")

        logger.info(f"kb_search: query={query!r}, workspace={workspace!r}")

        if not query or not query.strip():
            return {
                "jsonrpc": "2.0",
                "result": {"content": [{"type": "text", "text": "Запрос не может быть пустым."}]},
                "id": req_id,
            }

        try:
            result = await qa_client.ask(query)
            if not result or not result.get("answer"):
                text = "Не удалось найти информацию по вашему запросу."
            else:
                answer = result["answer"]
                sources = result.get("sources", [])
                if sources:
                    formatted = answer + "\n\n**Источники:**\n"
                    for i, src in enumerate(sources, 1):
                        title = src.get("title", "Источник")
                        url = src.get("url", "")
                        if url:
                            formatted += f"{i}. [{title}]({url})\n"
                        else:
                            formatted += f"{i}. {title}\n"
                    text = formatted
                else:
                    text = answer

            return {
                "jsonrpc": "2.0",
                "result": {"content": [{"type": "text", "text": text}]},
                "id": req_id,
            }

        except Exception as e:
            logger.error(f"kb_search error: {e}")
            return {
                "jsonrpc": "2.0",
                "result": {"content": [{"type": "text", "text": f"Произошла ошибка при поиске: {e}"}]},
                "id": req_id,
            }

    return {"jsonrpc": "2.0", "result": None, "id": req_id}


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    port = int(os.getenv("MCP_PORT", "9010"))
    logger.info(f"Starting mcp-kb on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
