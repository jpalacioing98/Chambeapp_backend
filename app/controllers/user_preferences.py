"""Preferencias del perfil unificado — disponibles para TODOS los roles.

Endpoints (JWT requerido):
  GET    /api/v1/users/me/preferences  → preferencias (crea por defecto).
  PUT    /api/v1/users/me/preferences  → actualizar preferencias.

Reutiliza el modelo MerchantPreference como "preferencias de usuario":
idioma/tema (UI) y toggles de notificación. A diferencia de
/merchant/preferences, NO restringe por rol.
"""

from datetime import datetime, timezone

from flask.views import MethodView
from flask_smorest import Blueprint
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models.merchant import MerchantPreference
from app.schemas.merchant import (
    MerchantPreferencesResponseSchema,
    MerchantPreferencesUpdateSchema,
)

blp = Blueprint("user_preferences", __name__, description="Preferencias del perfil (todos los roles)")


def _get_or_create_preferences(user_id: int) -> MerchantPreference:
    prefs = MerchantPreference.query.filter_by(user_id=user_id).first()
    if not prefs:
        prefs = MerchantPreference(user_id=user_id)
        db.session.add(prefs)
        db.session.flush()
    return prefs


@blp.route("/me/preferences")
class UserPreferences(MethodView):
    @jwt_required()
    @blp.response(200, MerchantPreferencesResponseSchema)
    def get(self):
        """Obtiene las preferencias del usuario autenticado."""
        user_id = int(get_jwt_identity())
        return _get_or_create_preferences(user_id)

    @jwt_required()
    @blp.arguments(MerchantPreferencesUpdateSchema)
    @blp.response(200, MerchantPreferencesResponseSchema)
    def put(self, data):
        """Actualiza las preferencias del usuario autenticado."""
        user_id = int(get_jwt_identity())
        prefs = _get_or_create_preferences(user_id)

        for key, value in data.items():
            if value is not None:
                setattr(prefs, key, value)

        prefs.actualizado_en = datetime.now(timezone.utc)
        db.session.commit()
        return prefs