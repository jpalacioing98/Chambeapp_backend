"""Orders blueprint: gestión contractual y órdenes de trabajo (RF-07)."""

from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models.user import User
from app.models.service import Service, EstadoServicio
from app.models.order import Order, EstadoOrden
from app.schemas.order import OrderCreateSchema, OrderEstadoSchema, OrderSchema
from app.routes.notifications import crear_notificacion

blp = Blueprint("orders", __name__, description="Órdenes de trabajo (RF-07)")


@blp.route("/")
class OrderList(MethodView):
    @jwt_required()
    @blp.arguments(OrderCreateSchema)
    @blp.response(201, OrderSchema)
    def post(self, data):
        """RF-07.1: crea orden. El JWT debe ser el dueño (solicitante) del servicio."""
        user_id = int(get_jwt_identity())

        service = db.session.get(Service, data["service_id"])
        if service is None:
            abort(404, message="El servicio no existe.")

        if service.estado != EstadoServicio.PUBLICADO:
            abort(400, message="El servicio no está publicado.")

        if service.solicitante_id != user_id:
            abort(403, message="Solo el dueño del servicio puede crear la orden.")

        proveedor = db.session.get(User, data["proveedor_id"])
        if proveedor is None:
            abort(404, message="El proveedor no existe.")

        order = Order(
            service_id=service.id,
            proveedor_id=proveedor.id,
            solicitante_id=user_id,
            estado=EstadoOrden.PENDIENTE,
        )
        db.session.add(order)
        db.session.flush()

        crear_notificacion(
            proveedor.id,
            "orden_pendiente",
            "Tienes una orden pendiente de un servicio que publicaste.",
        )
        db.session.commit()
        return order


@blp.route("/mine")
class MyOrders(MethodView):
    @jwt_required()
    @blp.response(200, OrderSchema(many=True))
    def get(self):
        """RF-07: lista órdenes donde el usuario es solicitante o proveedor."""
        user_id = int(get_jwt_identity())
        query = Order.query.filter(
            (Order.solicitante_id == user_id) | (Order.proveedor_id == user_id)
        )
        estado = request.args.get("estado")
        if estado:
            query = query.filter(Order.estado == EstadoOrden(estado))
        return query.order_by(Order.creado_en.desc()).all()


@blp.route("/<int:order_id>")
class OrderDetail(MethodView):
    @jwt_required()
    @blp.response(200, OrderSchema)
    def get(self, order_id):
        """RF-07: detalle de orden (solo participantes)."""
        user_id = int(get_jwt_identity())
        order = db.get_or_404(Order, order_id)
        if user_id not in (order.solicitante_id, order.proveedor_id):
            abort(403, message="No participas en esta orden.")
        return order


@blp.route("/<int:order_id>/estado")
class OrderEstado(MethodView):
    @jwt_required()
    @blp.arguments(OrderEstadoSchema)
    @blp.response(200, OrderSchema)
    def patch(self, data, order_id):
        """RF-07.2/3/4: transición de estado de la orden."""
        user_id = int(get_jwt_identity())
        order = db.get_or_404(Order, order_id)

        if user_id not in (order.solicitante_id, order.proveedor_id):
            abort(403, message="No participas en esta orden.")

        accion = data["estado"]

        if accion == "aceptar":
            if order.estado != EstadoOrden.PENDIENTE:
                abort(400, message="Solo se acepta una orden desde 'pendiente'.")
            if user_id != order.proveedor_id:
                abort(403, message="Solo el proveedor puede aceptar la orden.")
            order.estado = EstadoOrden.EN_PROGRESO
            crear_notificacion(
                order.solicitante_id,
                "orden_aceptada",
                "Tu orden de trabajo fue aceptada por el proveedor.",
            )

        elif accion == "completar":
            if order.estado != EstadoOrden.EN_PROGRESO:
                abort(400, message="Solo se completa una orden desde 'en_progreso'.")
            order.estado = EstadoOrden.COMPLETADO
            service = db.session.get(Service, order.service_id)
            if service is not None:
                service.estado = EstadoServicio.COMPLETADO
            crear_notificacion(
                order.solicitante_id,
                "orden_completada",
                "Tu orden de trabajo fue marcada como completada.",
            )
            crear_notificacion(
                order.proveedor_id,
                "orden_completada",
                "La orden de trabajo fue marcada como completada.",
            )

        elif accion == "cancelar":
            if order.estado in (EstadoOrden.COMPLETADO, EstadoOrden.CANCELADO):
                abort(400, message="No se puede cancelar una orden ya finalizada.")
            motivo = data.get("motivo_cancelacion")
            if not motivo or not str(motivo).strip():
                abort(400, message="Se requiere un motivo de cancelación.")
            order.estado = EstadoOrden.CANCELADO
            order.motivo_cancelacion = motivo
            contraparte = (
                order.solicitante_id
                if user_id == order.proveedor_id
                else order.proveedor_id
            )
            crear_notificacion(
                contraparte,
                "orden_cancelada",
                f"La orden de trabajo fue cancelada. Motivo: {motivo}",
            )

        else:
            abort(400, message="Acción de estado inválida.")

        db.session.commit()
        return order
