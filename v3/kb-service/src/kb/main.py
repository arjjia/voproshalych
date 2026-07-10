"""KB Service v3 — FastAPI application."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from kb.config import settings
from kb.db import Base, get_engine
from kb.tools import TOOLS, execute_tool

app = FastAPI(title="KB Service v3")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "kb-service", "version": "0.1.0"}


@app.post("/api/v1/tools")
async def handle_tools(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None},
        )

    method = body.get("method", "")
    params = body.get("params", {})
    req_id = body.get("id", 1)

    try:
        if method == "ping":
            return {"jsonrpc": "2.0", "result": "pong", "id": req_id}

        if method in ("list_tools", "tools/list"):
            return {"jsonrpc": "2.0", "result": {"tools": TOOLS}, "id": req_id}

        if method in ("tools/call",):
            name = params.get("name", "")
            arguments = params.get("arguments", {})
            result = await execute_tool(name, arguments)
            return {"jsonrpc": "2.0", "result": result, "id": req_id}

        result = await execute_tool(method, params)
        return {"jsonrpc": "2.0", "result": result, "id": req_id}

    except NotImplementedError as e:
        return JSONResponse(
            status_code=501,
            content={"jsonrpc": "2.0", "error": {"code": -32601, "message": str(e)}, "id": req_id},
        )
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"jsonrpc": "2.0", "error": {"code": -32602, "message": str(e)}, "id": req_id},
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"jsonrpc": "2.0", "error": {"code": -32603, "message": str(e)}, "id": req_id},
        )


@app.on_event("startup")
async def startup():
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.kb_port)
