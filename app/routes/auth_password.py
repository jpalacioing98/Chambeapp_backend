"""Auth password recovery blueprint: forgot/reset password (P0)."""

import secrets
from datetime import datetime, timedelta, timezone

from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db, bcrypt
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordSchema,
    ResetPasswordSchema,
    MessageResponseSchema,
)

blp = Blueprint("auth_password", __name__, description="Recuperación de contraseña")

# Store reset tokens in memory (in production, use Redis)
_reset_tokens: dict[str, dict] = {}


def _generate_reset_token(user_id: int) -> str:
    """Genera un token de reseteo de contraseña."""
    token = secrets.token_urlsafe(32)
    _reset_tokens[token] = {
        "user_id": user_id,
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
        "used": False,
    }
    return token


def _validate_reset_token(token: str) -> int | None:
    """Valida un token de reseteo. Retorna user_id o None."""
    if token not in _reset_tokens:
        return None
    
    token_data = _reset_tokens[token]
    
    if token_data["used"]:
        return None
    
    if datetime.now(timezone.utc) > token_data["expires_at"]:
        return None
    
    return token_data["user_id"]


@blp.route("/forgot-password")
class ForgotPassword(MethodView):
    @blp.arguments(ForgotPasswordSchema)
    @blp.response(200, MessageResponseSchema)
    def post(self, data):
        """Solicita reseteo de contraseña. Envía token por email."""
        email = data["email"]
        
        user = User.query.filter_by(email=email).first()
        if user is None:
            # Por seguridad, no revelar si el email existe
            return {"message": "Si el email existe, recibirás un enlace de reseteo."}
        
        token = _generate_reset_token(user.id)
        
        # TODO: Enviar email con el token
        # Por ahora, solo retornamos el token (en producción sería un email)
        # send_reset_email(user.email, token)
        
        return {"message": "Si el email existe, recibirás un enlace de reseteo."}


@blp.route("/reset-password")
class ResetPassword(MethodView):
    @blp.arguments(ResetPasswordSchema)
    @blp.response(200, MessageResponseSchema)
    def post(self, data):
        """Resetea la contraseña usando el token."""
        token = data["token"]
        new_password = data["new_password"]
        
        user_id = _validate_reset_token(token)
        if user_id is None:
            abort(400, message="Token inválido o expirado.")
        
        user = db.session.get(User, user_id)
        if user is None:
            abort(404, message="Usuario no encontrado.")
        
        # Actualizar contraseña
        user.password_hash = bcrypt.generate_password_hash(new_password).decode("utf-8")
        
        # Marcar token como usado
        _reset_tokens[token]["used"] = True
        
        db.session.commit()
        
        return {"message": "Contraseña actualizada exitosamente."}


@blp.route("/change-password")
class ChangePassword(MethodView):
    @jwt_required()
    @blp.arguments(ResetPasswordSchema)
    @blp.response(200, MessageResponseSchema)
    def post(self, data):
        """Cambia contraseña (usuario autenticado)."""
        user_id = int(get_jwt_identity())
        user = db.session.get(User, user_id)
        
        if user is None:
            abort(404, message="Usuario no encontrado.")
        
        # Verificar contraseña actual (si se proporciona)
        current_password = data.get("current_password")
        if current_password and not bcrypt.check_password_hash(
            user.password_hash, current_password
        ):
            abort(400, message="La contraseña actual es incorrecta.")
        
        # Actualizar contraseña
        user.password_hash = bcrypt.generate_password_hash(
            data["new_password"]
        ).decode("utf-8")
        
        db.session.commit()
        
        return {"message": "Contraseña cambiada exitosamente."}
