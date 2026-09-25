"""Autenticación en dos pasos (2FA) — perfil unificado.

Endpoints (JWT requerido):
  GET    /api/v1/auth/2fa  → estado actual { enabled: bool }.
  PUT    /api/v1/auth/2fa  → activar/desactivar { enabled: bool }.

MVP: el toggle persiste la preferencia del usuario. La verificación
efectiva del segundo factor (TOTP/SMS) se integrará con el flujo de
login en una iteración posterior.
"""

from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity
from marshmallow import Schema, fields

from app.extensions import db
from app.models.user import User

blp = Blueprint("two_factor", __name__, description="Autenticación en dos pasos")


class TwoFactorStatusSchema(Schema):
    enabled = fields.Boolean()


class TwoFactorUpdateSchema(Schema):
    enabled = fields.Boolean(required=True)


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