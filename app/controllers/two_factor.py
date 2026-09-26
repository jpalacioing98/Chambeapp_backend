"""Autenticación en dos pasos (2FA) — perfil unificado y login.

Endpoints:
  GET    /api/v1/auth/2fa        → estado actual { enabled: bool } (JWT).
  PUT    /api/v1/auth/2fa        → activar/desactivar { enabled: bool } (JWT).
  POST   /api/v1/auth/2fa/verify → completa el login con el código 2FA
                                   (público: se llama tras recibir requires_2fa).
"""

from datetime import datetime, timezone

from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import (
    jwt_required,
    get_jwt_identity,
    create_access_token,
    create_refresh_token,
)
from marshmallow import Schema, fields, validate

from app.extensions import db
from app.models.user import User

blp = Blueprint("two_factor", __name__, description="Autenticación en dos pasos")


class TwoFactorStatusSchema(Schema):
    enabled = fields.Boolean()


class TwoFactorUpdateSchema(Schema):
    enabled = fields.Boolean(required=True)


class TwoFactorVerifySchema(Schema):
    email = fields.Email(required=True)
    code = fields.String(required=True, validate=validate.Length(min=6, max=6))


@blp.route("/2fa")
class TwoFactor(MethodView):
    @jwt_required()
    @blp.response(200, TwoFactorStatusSchema)
    def get(self):
        """Estado actual de la verificación en dos pasos."""
        user_id = int(get_jwt_identity())
        user = db.session.get(User, user_id)
        if user is None:
            abort(404, message="Usuario no encontrado.")
        return {"enabled": user.two_factor_enabled}

    @jwt_required()
    @blp.arguments(TwoFactorUpdateSchema)
    @blp.response(200, TwoFactorStatusSchema)
    def put(self, data):
        """Activa o desactiva la verificación en dos pasos."""
        user_id = int(get_jwt_identity())
        user = db.session.get(User, user_id)
        if user is None:
            abort(404, message="Usuario no encontrado.")
        user.two_factor_enabled = bool(data["enabled"])
        db.session.commit()
        return {"enabled": user.two_factor_enabled}


@blp.route("/2fa/verify")
class TwoFactorVerify(MethodView):
    @blp.arguments(TwoFactorVerifySchema)
    def post(self, data):
        """Valida el código 2FA del desafío de login y emite los tokens.

        Se llama después de que `/auth/login` devuelva `requires_2fa: true`.
        En dev/test el código llega en `dev_code` de la respuesta del login.
        """
        from app.services.two_factor import verify_challenge

        user = User.query.filter_by(email=data["email"]).first()
        if user is None:
            abort(401, message="Credenciales inválidas.")
        if not user.activo or user.status != "active":
            abort(403, message="Cuenta suspendida o inactiva.")

        result = verify_challenge(user.id, data["code"])
        if result is True:
            pass
        elif result == "expired":
            abort(400, message="El código expiró. Vuelve a iniciar sesión.")
        elif result == "too_many":
            abort(429, message="Demasiados intentos. Vuelve a iniciar sesión.")
        else:
            abort(400, message="Código incorrecto. Verifica e inténtalo de nuevo.")

        access = create_access_token(
            identity=str(user.id),
            additional_claims={"role": user.rol.value, "role_v": user.role_version},
        )
        refresh = create_refresh_token(
            identity=str(user.id),
            additional_claims={"role_v": user.role_version},
        )
        user.last_login = datetime.now(timezone.utc)
        db.session.commit()

        return {"access_token": access, "refresh_token": refresh}