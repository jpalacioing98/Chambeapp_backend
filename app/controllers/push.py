"""Push notifications blueprint (RF-10 / HU-33)."""

import logging

from flask import request
from flask.views import MethodView
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_smorest import Blueprint, abort
from marshmallow import EXCLUDE, Schema, fields, validate

from app.extensions import db
from app.models.push import PushSubscription
from app.services.push import vapid_public_key

log = logging.getLogger(__name__)

blp = Blueprint("push", __name__, description="Web Push (RF-10 / HU-33)")


class PushKeysSchema(Schema):
    p256dh = fields.String(required=True, validate=validate.Length(min=1))
    auth = fields.String(required=True, validate=validate.Length(min=1))


class PushSubscribeSchema(Schema):
    class Meta:
        # `PushSubscription.toJSON()` incluye `expirationTime` (normalmente
        # null). Ignoramos cualquier campo extra para no devolver 422.
        unknown = EXCLUDE

    endpoint = fields.String(
        required=True, validate=validate.Length(min=10, max=4000)
    )
    keys = fields.Nested(PushKeysSchema, required=True)
    expirationTime = fields.Raw(load_default=None, allow_none=True)
    user_agent = fields.String(load_default=None)


class PushUnsubscribeSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    endpoint = fields.String(required=True, validate=validate.Length(min=10))


class VapidKeySchema(Schema):
    public_key = fields.String()


class SimpleOkSchema(Schema):
    ok = fields.Boolean()
    id = fields.Integer(allow_none=True)
    deleted = fields.Integer(allow_none=True)


@blp.route("/vapid-public-key")
class VapidPublicKey(MethodView):
    @blp.response(200, VapidKeySchema)
    def get(self):
        """Clave pública VAPID para `pushManager.subscribe()`.

        Es pública por diseño; el frontend la pide antes de suscribirse.
        """
        key = vapid_public_key()
        if not key:
            abort(
                503,
                message=(
                    "Web Push no está configurado (faltan claves VAPID). "
                    "Consulta docs/notifications.md."
                ),
            )
        return {"public_key": key}


@blp.route("/subscribe")
class PushSubscribe(MethodView):
    @jwt_required()
    @blp.arguments(PushSubscribeSchema)
    @blp.response(200, SimpleOkSchema)
    def post(self, payload):
        """Registra (o reasigna) la suscripción push del navegador actual."""
        user_id = int(get_jwt_identity())
        endpoint = payload["endpoint"].strip()
        keys = payload["keys"]

        sub = PushSubscription.query.filter_by(endpoint=endpoint).first()
        if sub is None:
            sub = PushSubscription(endpoint=endpoint, user_id=user_id)
            db.session.add(sub)

        # El mismo navegador puede cambiar de cuenta: se reasigna.
        sub.user_id = user_id
        sub.p256dh = keys["p256dh"]
        sub.auth = keys["auth"]
        sub.user_agent = (
            payload.get("user_agent")
            or request.headers.get("User-Agent", "")[:255]
            or None
        )
        db.session.commit()
        return {"ok": True, "id": sub.id}

    @jwt_required()
    @blp.arguments(PushUnsubscribeSchema)
    @blp.response(200, SimpleOkSchema)
    def delete(self, payload):
        """Elimina la suscripción del navegador (solo si es del usuario)."""
        user_id = int(get_jwt_identity())
        endpoint = payload["endpoint"].strip()
        deleted = PushSubscription.query.filter_by(
            user_id=user_id, endpoint=endpoint
        ).delete()
        db.session.commit()
        return {"ok": True, "deleted": deleted}


@blp.route("/subscriptions")
class PushSubscriptionList(MethodView):
    @jwt_required()
    def get(self):
        """Diagnóstico: cuántos dispositivos tiene suscritos el usuario."""
        user_id = int(get_jwt_identity())
        count = PushSubscription.query.filter_by(user_id=user_id).count()
        return {"count": count}


@blp.route("/test")
class PushTest(MethodView):
    @jwt_required()
    def post(self):
        """Envía una notificación push de prueba al usuario actual."""
        from app.services.push import enviar_push_prueba

        user_id = int(get_jwt_identity())
        result = enviar_push_prueba(user_id)
        db.session.commit()
        return result
