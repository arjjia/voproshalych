from admin.api.routes.health import router as health_router
from admin.api.routes.stats import router as stats_router
from admin.api.routes.qa import router as qa_router
from admin.api.routes.users import router as users_router

__all__ = ["health_router", "stats_router", "qa_router", "users_router"]
