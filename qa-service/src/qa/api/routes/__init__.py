"""API роутеры."""

from .qa import router as qa_router
from .health import router as health_router
from .holiday import router as holiday_router
from .kb import router as kb_router

__all__ = ["qa_router", "health_router", "holiday_router", "kb_router"]
