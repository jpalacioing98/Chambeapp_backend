"""Routes package."""
from app.routes.auth import blp as auth_blp
from app.routes.users import blp as users_blp
from app.routes.solicitudes import blp as solicitudes_blp
from app.routes.ofertas import blp as ofertas_blp

__all__ = ["auth_blp", "users_blp", "solicitudes_blp", "ofertas_blp"]
