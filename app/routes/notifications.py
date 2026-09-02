"""Notifications blueprint: centro de notificaciones persistente (RF-10)."""

from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models.notification import Notification
from app.schemas.notification import NotificationSchema
from app.services.pagination import paginate_query


blp = Blueprint("notifications", __name__, description="Centro de notificaciones (RF-10)")


def crear_notificacion(user_id, tipo, mensaje, titulo=None, datos=None):
    """Helper: persiste (sin commit) una notificación para user_id."""
    notif = Notification(
        user_id=user_id,
        tipo=tipo,
        titulo=titulo,
        mensaje=mensaje,
        datos=datos,
    )
    db.session.add(notif)
    return notif


MENSAJE_FORMALIZACION = (
    "Tu trabajo informal quedó completado. ChambeApp te recuerda que puedes "
    "acceder a beneficios de formalización laboral en Colombia (afiliación a "
    "salud/pensión, prestaciones sociales, certificado de ingresos)."
)


def disparar_notificaciones_formalizacion(contract):
    """RF-10: al completarse un contrato, notifica a ambas partes sobre formalización.

    Idempotente (no duplica si ya existe para el contrato) y a prueba de fallos:
    cualquier excepción se revierte y no interrumpe el flujo del contrato.
    """
    try:
        datos = {"contract_id": contract.id, "service_id": contract.service_id}
        for uid in (contract.solicitante_id, contract.proveedor_id):
            ya = Notification.query.filter_by(user_id=uid, tipo="formalizacion").all()
            if not any(
                n.datos and n.datos.get("contract_id") == contract.id for n in ya
            ):
                crear_notificacion(
                    uid,
                    "formalizacion",
                    MENSAJE_FORMALIZACION,
                    titulo="Solicitud completada: considera formalizar",
                    datos=datos,
                )
        db.session.commit()
    except Exception:
        db.session.rollback()


@blp.route("/")
class NotificationList(MethodView):
    @jwt_required()
    @blp.response(200, NotificationSchema(many=True))
    def get(self):
        """RF-10: lista notificaciones del usuario actual (recientes primero).
        
        Supports optional page/per_page query params for pagination (P2-4).
        If no params, returns all items (backward compatible).
        """
        user_id = int(get_jwt_identity())
        query = (
            Notification.query.filter_by(user_id=user_id)
            .order_by(Notification.creado_en.desc())
        )

        page = request.args.get("page")
        per_page = request.args.get("per_page")
        result = paginate_query(query, page=page, per_page=per_page)

        if isinstance(result, list):
            return result
        return result


@blp.route("/no-leidas")
class NotificationUnreadCount(MethodView):
    @jwt_required()
    def get(self):
        """RF-10: conteo de notificaciones no leídas del usuario actual."""
        user_id = int(get_jwt_identity())
        count = Notification.query.filter_by(user_id=user_id, leida=False).count()
        return {"count": count}


@blp.route("/<int:notif_id>/marcar-leida")
class NotificationMarcarLeida(MethodView):
    @jwt_required()
    @blp.response(200, NotificationSchema)
    def post(self, notif_id):
        """RF-10: marca una notificación como leída (solo si es del usuario)."""
        user_id = int(get_jwt_identity())
        notif = db.session.get(Notification, notif_id)
        if notif is None or notif.user_id != user_id:
            abort(404, message="Notificación no encontrada.")
        notif.leida = True
        db.session.commit()
        return notif


@blp.route("/marcar-todas-leidas")
class NotificationMarcarTodasLeidas(MethodView):
    @jwt_required()
    def post(self):
        """RF-10: marca todas las notificaciones del usuario como leídas."""
        user_id = int(get_jwt_identity())
        Notification.query.filter_by(user_id=user_id, leida=False).update(
            {Notification.leida: True}
        )
        db.session.commit()
        return {"updated": True}


# ---- Endpoints legacy (RF-16) mantenidos por compatibilidad con tests/clientes ----
@blp.route("/me")
class MyNotifications(MethodView):
    @jwt_required()
    @blp.response(200, NotificationSchema(many=True))
    def get(self):
        """Lista notificaciones del usuario (no leídas primero).
        
        Supports optional page/per_page query params for pagination (P2-4).
        If no params, returns all items (backward compatible).
        """
        user_id = int(get_jwt_identity())
        query = (
            Notification.query.filter_by(user_id=user_id)
            .order_by(Notification.leida.asc(), Notification.creado_en.desc())
        )

        page = request.args.get("page")
        per_page = request.args.get("per_page")
        result = paginate_query(query, page=page, per_page=per_page)

        if isinstance(result, list):
            return result
        return result


@blp.route("/<int:notif_id>/read")
class NotificationRead(MethodView):
    @jwt_required()
    @blp.response(200, NotificationSchema)
    def patch(self, notif_id):
        """Marca una notificación como leída (solo dueño; 403 si no)."""
        user_id = int(get_jwt_identity())
        notif = db.session.get(Notification, notif_id)
        if notif is None:
            abort(404, message="Notificación no encontrada.")
        if notif.user_id != user_id:
            abort(403, message="No es tu notificación.")
        notif.leida = True
        db.session.commit()
        return notif
