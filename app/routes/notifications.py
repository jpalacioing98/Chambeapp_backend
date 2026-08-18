"""Notifications blueprint: in-app notifications (RF-16 parcial)."""

from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models.notification import Notification
from app.schemas.notification import NotificationSchema

blp = Blueprint("notifications", __name__, description="Notificaciones in-app")


def crear_notificacion(user_id: int, tipo: str, mensaje: str) -> Notification:
    """Helper: persiste una notificación para user_id."""
    notif = Notification(user_id=user_id, tipo=tipo, mensaje=mensaje)
    db.session.add(notif)
    return notif


@blp.route("/me")
class MyNotifications(MethodView):
    @jwt_required()
    @blp.response(200, NotificationSchema(many=True))
    def get(self):
        """RF-16: lista notificaciones del usuario (no leídas primero)."""
        user_id = int(get_jwt_identity())
        return (
            Notification.query.filter_by(user_id=user_id)
            .order_by(Notification.leida.asc(), Notification.creado_en.desc())
            .all()
        )


@blp.route("/<int:notif_id>/read")
class NotificationRead(MethodView):
    @jwt_required()
    @blp.response(200, NotificationSchema)
    def patch(self, notif_id):
        """RF-16: marca una notificación como leída."""
        user_id = int(get_jwt_identity())
        notif = db.get_or_404(Notification, notif_id)
        if notif.user_id != user_id:
            abort(403, message="No es tu notificación.")
        notif.leida = True
        db.session.commit()
        return notif
