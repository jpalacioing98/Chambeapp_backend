"""Routes package."""
from app.routes.auth import blp as auth_blp
from app.routes.users import blp as users_blp
from app.routes.services import blp as services_blp

__all__ = ["auth_blp", "users_blp", "services_blp"]
