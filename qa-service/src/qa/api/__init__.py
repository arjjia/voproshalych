"""API модуль."""

from .routes import qa_router, health_router, holiday_router, kb_router

__all__ = ["qa_router", "health_router", "holiday_router", "kb_router"]
