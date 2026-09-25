"""Email verification blueprint: verificación de email al registrarse (P1)."""

import secrets
from datetime import datetime, timedelta, timezone

from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models.user import User
from app.schemas.auth import MessageResponseSchema

blp = Blueprint("email_verification", __name__, description="Verificación de email (P1)")

# Store verification tokens in memory (in production, use Redis)
_verification_tokens: dict[str, dict] = {}


def _generate_verification_token(user_id: int) -> str:
    """Genera un token de verificación de email."""
    token = secrets.token_urlsafe(32)
    _verification_tokens[token] = {
        "user_id": user_id,
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=24),
        "verified": False,
    }
    return token


def _validate_verification_token(token: str) -> int | None:
    """Valida un token de verificación. Retorna user_id o None."""
    if token not in _verification_tokens:
        return None
    
    token_data = _verification_tokens[token]
    
    if token_data["verified"]:
        return None
    
    if datetime.now(timezone.utc) > token_data["expires_at"]:
        return None
    
    return token_data["user_id"]


@blp.route("/send-verification")
class SendVerification(MethodView):
    @jwt_required()
    @blp.response(200, MessageResponseSchema)
    def post(self):
        """Envía token de verificación al email del usuario."""
        user_id = int(get_jwt_identity())
        user = db.session.get(User, user_id)
        
        if user is None:
            abort(404, message="Usuario no encontrado.")
        
        # Generar token
        token = _generate_verification_token(user.id)
        
        # TODO: Enviar email con el token
        # send_verification_email(user.email, token)
        
        return {"message": "Se ha enviado un enlace de verificación a tu email."}


@blp.route("/verify-email")
class VerifyEmail(MethodView):
    @blp.arguments({"token": {"type": "string", "required": True}})
    @blp.response(200, MessageResponseSchema)
    def post(self, data):
        """Verifica el email usando el token."""
        token = data.get("token")
        if not token:
            abort(400, message="Token requerido.")
        
        user_id = _validate_verification_token(token)
        if user_id is None:
            abort(400, message="Token inválido o expirado.")
        
        user = db.session.get(User, user_id)
        if user is None:
            abort(404, message="Usuario no encontrado.")
        
        # Marcar email como verificado
        user.email_verificado = True
        
        # Marcar token como usado
        _verification_tokens[token]["verified"] = True
        
        db.session.commit()
        
        return {"message": "Email verificado exitosamente."}


@blp.route("/email-status")
class EmailStatus(MethodView):
    @jwt_required()
    @blp.response(200)
    def get(self):
        """Consulta estado de verificación del email."""
        user_id = int(get_jwt_identity())
        user = db.session.get(User, user_id)
        
        if user is None:
            abort(404, message="Usuario no encontrado.")
        
        return {
            "email": user.email,
            "verificado": getattr(user, "email_verificado", False),
        }
