"""Blueprint Merchant: métodos de pago y preferencias del comerciante.

Endpoints (JWT requerido):
  GET    /api/v1/merchant/payment-methods       → listar métodos de pago
  POST   /api/v1/merchant/payment-methods       → agregar método de pago
  DELETE /api/v1/merchant/payment-methods/<id>   → eliminar método de pago
  GET    /api/v1/merchant/preferences           → preferencias notificación
  PUT    /api/v1/merchant/preferences           → actualizar preferencias
"""

from datetime import datetime, timezone

from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.auth.decorators import role_required
from app.models.user import User, RolUsuario
from app.models.merchant import MerchantPreference, MerchantPaymentMethod
from app.schemas.merchant import (
    MerchantPaymentMethodCreateSchema,
    MerchantPaymentMethodResponseSchema,
    MerchantPaymentMethodsListSchema,
    MerchantPreferencesResponseSchema,
    MerchantPreferencesUpdateSchema,
)

blp = Blueprint("merchant", __name__, description="Gestión de comerciante: pago y preferencias")


# ── Helpers ────────────────────────────────────────────────────────────

def _current_user() -> User:
    """Obtiene el usuario actual desde el JWT."""
    return db.get_or_404(User, int(get_jwt_identity()))


def _ensure_merchant_user(user_id: int) -> User:
    """Verifica que el usuario tenga rol merchant."""
    user = db.session.get(User, user_id)
    if not user or user.rol != RolUsuario.MERCHANT:
        abort(403, message="Solo los comerciantes pueden acceder a este recurso.")
    return user


def _get_or_create_preferences(user_id: int) -> MerchantPreference:
    """Obtiene o crea preferencias por defecto para un merchant."""
    prefs = MerchantPreference.query.filter_by(user_id=user_id).first()
    if not prefs:
        prefs = MerchantPreference(user_id=user_id)
        db.session.add(prefs)
        db.session.flush()
    return prefs


# ── Métodos de Pago ────────────────────────────────────────────────────

@blp.route("/payment-methods")
class MerchantPaymentMethodsList(MethodView):
    @role_required(["merchant"])
    @blp.response(200, MerchantPaymentMethodsListSchema)
    def get(self):
        """Lista los métodos de pago del comerciante autenticado."""
        user_id = int(get_jwt_identity())
        methods = MerchantPaymentMethod.query.filter_by(
            user_id=user_id, activo=True
        ).order_by(
            MerchantPaymentMethod.principal.desc(),
            MerchantPaymentMethod.id,
        ).all()
        return {"metodos": methods}

    @role_required(["merchant"])
    @blp.arguments(MerchantPaymentMethodCreateSchema)
    @blp.response(201, MerchantPaymentMethodResponseSchema)
    def post(self, data):
        """Agrega un método de pago al comerciante."""
        user_id = int(get_jwt_identity())

        # Si se marca como principal, desmarcar los demás
        if data.get("principal"):
            MerchantPaymentMethod.query.filter_by(
                user_id=user_id, principal=True
            ).update({"principal": False})

        method = MerchantPaymentMethod(
            user_id=user_id,
            tipo=data["tipo"],
            detalle=data["detalle"],
            principal=data.get("principal", False),
        )
        db.session.add(method)
        db.session.commit()
        return method


@blp.route("/payment-methods/<int:method_id>")
class MerchantPaymentMethodDetail(MethodView):
    @role_required(["merchant"])
    @blp.response(204)
    def delete(self, method_id):
        """Elimina (desactiva) un método de pago del comerciante."""
        user_id = int(get_jwt_identity())
        method = db.session.get(MerchantPaymentMethod, method_id)
        if not method or method.user_id != user_id:
            abort(404, message="Método de pago no encontrado.")
        method.activo = False
        db.session.commit()
        return "", 204


# ── Preferencias ───────────────────────────────────────────────────────

@blp.route("/preferences")
class MerchantPreferences(MethodView):
    @role_required(["merchant"])
    @blp.response(200, MerchantPreferencesResponseSchema)
    def get(self):
        """Obtiene las preferencias de notificación del comerciante."""
        user_id = int(get_jwt_identity())
        prefs = _get_or_create_preferences(user_id)
        return prefs

    @role_required(["merchant"])
    @blp.arguments(MerchantPreferencesUpdateSchema)
    @blp.response(200, MerchantPreferencesResponseSchema)
    def put(self, data):
        """Actualiza preferencias de notificación del comerciante."""
        user_id = int(get_jwt_identity())
        prefs = _get_or_create_preferences(user_id)

        for key, value in data.items():
            if value is not None:
                setattr(prefs, key, value)

        prefs.actualizado_en = datetime.now(timezone.utc)
        db.session.commit()
        return prefs
