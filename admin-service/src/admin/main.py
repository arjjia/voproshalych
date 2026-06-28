"""FastAPI-приложение admin-service."""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from admin.api import health_router, qa_router, stats_router, tasks_router, users_router
from admin.auth import require_admin_auth
from admin.config import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="Voproshalych Admin API",
        description="Read-only analytics API",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(stats_router, dependencies=[Depends(require_admin_auth)])
    app.include_router(qa_router, dependencies=[Depends(require_admin_auth)])
    app.include_router(tasks_router, dependencies=[Depends(require_admin_auth)])
    app.include_router(users_router, dependencies=[Depends(require_admin_auth)])

    return app


app = create_app()
