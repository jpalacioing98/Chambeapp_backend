"""Admin blueprint (RBAC Fase 1): gestión de usuarios, verificaciones y stats.

Todos los endpoints requieren rol admin O superadmin (ver @admin_required).
Registrado en /api/v1/admin.
"""

from datetime import datetime, timezone

from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import get_jwt_identity

from app.extensions import db
from app.auth.decorators import admin_required
from app.models.user import User, RolUsuario, Verification
from app.models.service import Service, Rating, EstadoServicio
from app.models.order import Order, EstadoOrden, Dispute
from app.models.payment import Payment, EstadoPago
from app.models.ticket import Ticket
from app.models.audit import write_audit
from app.services.payments import liberar_escrow, reembolsar
from app.schemas.admin import (
    UserListSchema,
    UserDetailSchema,
    UserListResponseSchema,
    RolePatchSchema,
    StatusPatchSchema,
    RejectSchema,
    VerificationListSchema,
    VerificationListResponseSchema,
    VerificationActionSchema,
    StatsOverviewSchema,
    ServiceModerateSchema,
    ServiceListResponseSchema,
    OrderModerateSchema,
    OrderListSchema,
    OrderListResponseSchema,
    DisputeListResponseSchema,
    DisputeDetailSchema,
    DisputeResolveSchema,
    TicketListResponseSchema,
    TicketPatchSchema,
    ContentReportResponseSchema,
    ContentModerateSchema,
)

blp = Blueprint("admin", __name__, description="Panel administrativo (RBAC)")


def _actor_id() -> int:
    return int(get_jwt_identity())


def _client_ip() -> str:
    return request.remote_addr or "127.0.0.1"


@blp.route("/users")
class AdminUserList(MethodView):
    @admin_required
    @blp.response(200, UserListResponseSchema)
    def get(self):
        """Lista usuarios con filtros (rol, status, q) — máx 50."""
        query = User.query
        role = request.args.get("role")
        if role:
            query = query.filter(User.rol == RolUsuario(role))
        status = request.args.get("status")
        if status:
            query = query.filter(User.status == status)
        q = request.args.get("q")
        if q:
            like = f"%{q}%"
            query = query.filter(
                (User.email.ilike(like)) | (User.nombre.ilike(like))
            )
        total = query.count()
        users = query.order_by(User.id).limit(50).all()
        return {"items": users, "total": total}


@blp.route("/users/<int:user_id>")
class AdminUserDetail(MethodView):
    @admin_required
    @blp.response(200, UserDetailSchema)
    def get(self, user_id):
        """Detalle de un usuario."""
        user = db.get_or_404(User, user_id)
        return UserDetailSchema().dump(user)


@blp.route("/users/<int:user_id>/role")
class AdminUserRole(MethodView):
    @admin_required
    @blp.arguments(RolePatchSchema)
    @blp.response(200, UserDetailSchema)
    def patch(self, data, user_id):
        """Cambia el rol de un usuario (revoca tokens vía role_version++)."""
        user = db.get_or_404(User, user_id)
        new_role = data["role"]
        # Solo superadmin puede otorgar superadmin (el decorador ya admite admin).
        if new_role == "superadmin":
            abort(403, message="Solo un superadmin puede asignar el rol superadmin.")
        before = {"rol": user.rol.value}
        user.rol = RolUsuario(new_role)
        user.role_version += 1
        write_audit(
            _actor_id(), "user.role.update", "user", user.id,
            before, {"rol": new_role}, _client_ip(),
        )
        db.session.commit()
        return user


@blp.route("/users/<int:user_id>/status")
class AdminUserStatus(MethodView):
    @admin_required
    @blp.arguments(StatusPatchSchema)
    @blp.response(200, UserDetailSchema)
    def patch(self, data, user_id):
        """Suspende / bloquea / reactiva una cuenta."""
        user = db.get_or_404(User, user_id)
        new_status = data["status"]
        before = {"status": user.status}
        user.status = new_status
        user.role_version += 1  # revoca tokens activos
        write_audit(
            _actor_id(), "user.status.update", "user", user.id,
            before, {"status": new_status}, _client_ip(),
        )
        db.session.commit()
        return user


@blp.route("/stats/overview")
class AdminStats(MethodView):
    @admin_required
    @blp.response(200, StatsOverviewSchema)
    def get(self):
        """Métricas generales para el dashboard admin."""
        users_total = User.query.count()
        users_active = User.query.filter(User.status == "active").count()
        services_total = Service.query.count()
        orders_total = Order.query.count()
        revenue_total = (
            db.session.query(db.func.sum(Payment.monto))
            .filter(Payment.estado == EstadoPago.LIBERADO)
            .scalar()
            or 0
        )
        disputes_open = Dispute.query.filter(Dispute.status == "abierta").count()
        return {
            "users_total": users_total,
            "users_active": users_active,
            "services_total": services_total,
            "orders_total": orders_total,
            "revenue_total": int(revenue_total),
            "disputes_open": disputes_open,
        }


@blp.route("/verifications")
class AdminVerificationList(MethodView):
    @admin_required
    @blp.response(200, VerificationListResponseSchema)
    def get(self):
        """Lista solicitudes de verificación (filtra por status, def. pending)."""
        status = request.args.get("status", "pending")
        verifs = (
            Verification.query.filter(Verification.status == status)
            .order_by(Verification.created_at.desc())
            .all()
        )
        items = []
        for v in verifs:
            user = db.session.get(User, v.user_id)
            d = VerificationListSchema().dump(v)
            d["nombre"] = user.nombre if user else None
            items.append(d)
        return {"items": items, "total": len(items)}


@blp.route("/verifications/<int:verif_id>/approve")
class AdminVerificationApprove(MethodView):
    @admin_required
    @blp.response(200, VerificationActionSchema)
    def post(self, verif_id):
        """Aprueba una verificación (KYC)."""
        v = db.get_or_404(Verification, verif_id)
        before = {"status": v.status}
        v.status = "approved"
        v.reviewed_by = _actor_id()
        v.reviewed_at = datetime.now(timezone.utc)
        write_audit(
            _actor_id(), "verification.approve", "verification", v.id,
            before, {"status": "approved"}, _client_ip(),
        )
        db.session.commit()
        return {"id": v.id, "status": v.status}


@blp.route("/verifications/<int:verif_id>/reject")
class AdminVerificationReject(MethodView):
    @admin_required
    @blp.arguments(RejectSchema)
    @blp.response(200, VerificationActionSchema)
    def post(self, data, verif_id):
        """Rechaza una verificación con motivo."""
        v = db.get_or_404(Verification, verif_id)
        before = {"status": v.status}
        v.status = "rejected"
        v.reviewed_by = _actor_id()
        v.reviewed_at = datetime.now(timezone.utc)
        v.reason = data["reason"]
        write_audit(
            _actor_id(), "verification.reject", "verification", v.id,
            before, {"status": "rejected", "reason": data["reason"]}, _client_ip(),
        )
        db.session.commit()
        return {"id": v.id, "status": v.status}


# ==========================================================================
# FASE 2 — Moderación de servicios
# ==========================================================================
_SERVICE_ACTION_ESTADO = {
    "approve": EstadoServicio.PUBLICADO,
    "reject": EstadoServicio.RECHAZADO,
    "hide": EstadoServicio.OCULTO,
}


@blp.route("/services")
class AdminServiceList(MethodView):
    @admin_required
    @blp.response(200, ServiceListResponseSchema)
    def get(self):
        """Lista servicios con filtros (q, status) — máx 50."""
        query = Service.query
        q = request.args.get("q")
        if q:
            like = f"%{q}%"
            query = query.filter(
                (Service.titulo.ilike(like)) | (Service.descripcion.ilike(like))
            )
        status = request.args.get("status")
        if status:
            query = query.filter(Service.estado == EstadoServicio(status))
        total = query.count()
        services = query.order_by(Service.creado_en.desc()).limit(50).all()
        return {"items": services, "total": total}


@blp.route("/services/<int:service_id>/moderate")
class AdminServiceModerate(MethodView):
    @admin_required
    @blp.arguments(ServiceModerateSchema)
    @blp.response(200)
    def patch(self, data, service_id):
        """Modera un servicio: approve | reject | hide."""
        service = db.get_or_404(Service, service_id)
        nuevo = _SERVICE_ACTION_ESTADO[data["action"]]
        before = {"estado": service.estado.value}
        service.estado = nuevo
        write_audit(
            _actor_id(), f"service.moderate.{data['action']}", "service",
            service.id, before, {"estado": nuevo.value}, _client_ip(),
        )
        db.session.commit()
        return {"id": service.id, "estado": service.estado.value}


# ==========================================================================
# FASE 2 — Moderación de órdenes
# ==========================================================================
_ORDER_ACTION_ESTADO = {
    "cancel": EstadoOrden.CANCELADO,
    "flag": EstadoOrden.MARCADO,
}


@blp.route("/orders")
class AdminOrderList(MethodView):
    @admin_required
    @blp.response(200, OrderListResponseSchema)
    def get(self):
        """Lista órdenes con filtro opcional de status — máx 50."""
        query = Order.query
        status = request.args.get("status")
        if status:
            query = query.filter(Order.estado == EstadoOrden(status))
        total = query.count()
        orders = query.order_by(Order.creado_en.desc()).limit(50).all()
        for o in orders:
            payment = Payment.query.filter_by(order_id=o.id).first()
            o.monto = payment.monto if payment else None
        return {"items": orders, "total": total}


@blp.route("/orders/<int:order_id>/moderate")
class AdminOrderModerate(MethodView):
    @admin_required
    @blp.arguments(OrderModerateSchema)
    @blp.response(200)
    def patch(self, data, order_id):
        """Modera una orden: cancel | flag."""
        order = db.get_or_404(Order, order_id)
        nuevo = _ORDER_ACTION_ESTADO[data["action"]]
        before = {"estado": order.estado.value}
        order.estado = nuevo
        write_audit(
            _actor_id(), f"order.moderate.{data['action']}", "order",
            order.id, before, {"estado": nuevo.value}, _client_ip(),
        )
        db.session.commit()
        return {"id": order.id, "estado": order.estado.value}


# ==========================================================================
# FASE 2 — Disputas / Escrow
# ==========================================================================
@blp.route("/disputes")
class AdminDisputeList(MethodView):
    @admin_required
    @blp.response(200, DisputeListResponseSchema)
    def get(self):
        """Lista disputas (status por defecto 'abierta')."""
        status = request.args.get("status", "abierta")
        disputes = (
            Dispute.query.filter(Dispute.status == status)
            .order_by(Dispute.created_at.desc())
            .all()
        )
        return {"items": disputes, "total": len(disputes)}


@blp.route("/disputes/<int:dispute_id>")
class AdminDisputeDetail(MethodView):
    @admin_required
    @blp.response(200)
    def get(self, dispute_id):
        """Detalle de disputa + datos de orden/pago asociados."""
        dispute = db.get_or_404(Dispute, dispute_id)
        order = db.session.get(Order, dispute.order_id)
        payment = Payment.query.filter_by(order_id=dispute.order_id).first()
        data = DisputeDetailSchema().dump(dispute)
        data["order"] = (
            {
                "id": order.id,
                "estado": order.estado.value,
                "comprador_id": order.solicitante_id,
                "vendedor_id": order.proveedor_id,
                "servicio_id": order.service_id,
            }
            if order
            else None
        )
        data["payment"] = (
            {
                "id": payment.id,
                "estado": payment.estado.value,
                "monto": payment.monto,
                "comision": payment.comision,
            }
            if payment
            else None
        )
        return data


@blp.route("/disputes/<int:dispute_id>/resolve")
class AdminDisputeResolve(MethodView):
    @admin_required
    @blp.arguments(DisputeResolveSchema)
    @blp.response(200)
    def post(self, data, dispute_id):
        """Resuelve una disputa y aplica la acción de escrow."""
        dispute = db.get_or_404(Dispute, dispute_id)
        if dispute.status == "resuelta":
            abort(400, message="La disputa ya está resuelta.")
        order = db.session.get(Order, dispute.order_id)
        payment = Payment.query.filter_by(order_id=dispute.order_id).first()

        before = {
            "status": dispute.status,
            "escrow_action": dispute.escrow_action,
            "payment_estado": payment.estado.value if payment else None,
        }
        dispute.resolved_by = _actor_id()
        dispute.resolved_at = datetime.now(timezone.utc)
        dispute.resolution = data["resolution"]
        dispute.escrow_action = data["escrow_action"]
        dispute.status = "resuelta"

        if payment is not None:
            try:
                if data["escrow_action"] == "release":
                    liberar_escrow(payment.id)
                elif data["escrow_action"] == "refund":
                    reembolsar(payment.id, data["resolution"])
                    # Revierte la comisión de plataforma en reembolso.
                    payment.comision = 0
                    db.session.commit()
            except (ValueError, RuntimeError) as e:
                abort(400, message=str(e))

        write_audit(
            _actor_id(), "dispute.resolve", "dispute", dispute.id,
            before,
            {
                "status": "resuelta",
                "escrow_action": data["escrow_action"],
                "payment_estado": payment.estado.value if payment else None,
            },
            _client_ip(),
        )
        db.session.commit()
        return {
            "id": dispute.id,
            "status": "resuelta",
            "escrow_action": data["escrow_action"],
        }


# ==========================================================================
# FASE 2 — Tickets de soporte (gestión admin)
# ==========================================================================
@blp.route("/tickets")
class AdminTicketList(MethodView):
    @admin_required
    @blp.response(200, TicketListResponseSchema)
    def get(self):
        """Lista tickets con filtro opcional de status — máx 50."""
        query = Ticket.query
        status = request.args.get("status")
        if status:
            query = query.filter(Ticket.status == status)
        total = query.count()
        tickets = query.order_by(Ticket.created_at.desc()).limit(50).all()
        return {"items": tickets, "total": total}


@blp.route("/tickets/<int:ticket_id>")
class AdminTicketPatch(MethodView):
    @admin_required
    @blp.arguments(TicketPatchSchema)
    @blp.response(200)
    def patch(self, data, ticket_id):
        """Actualiza estado/asignación/prioridad de un ticket."""
        ticket = db.get_or_404(Ticket, ticket_id)
        before = {
            "status": ticket.status,
            "assigned_to": ticket.assigned_to,
            "priority": ticket.priority,
        }
        if "status" in data:
            ticket.status = data["status"]
            if data["status"] == "closed":
                ticket.resolved_at = datetime.now(timezone.utc)
            else:
                ticket.resolved_at = None
        if "assigned_to" in data:
            ticket.assigned_to = data["assigned_to"]
        if "priority" in data:
            ticket.priority = data["priority"]
        write_audit(
            _actor_id(), "ticket.update", "ticket", ticket.id,
            before,
            {
                "status": ticket.status,
                "assigned_to": ticket.assigned_to,
                "priority": ticket.priority,
            },
            _client_ip(),
        )
        db.session.commit()
        return {"id": ticket.id, "status": ticket.status}


# ==========================================================================
# FASE 2 — Moderación de contenido (ratings)
# ==========================================================================
@blp.route("/content/reports")
class AdminContentReports(MethodView):
    @admin_required
    @blp.response(200, ContentReportResponseSchema)
    def get(self):
        """Lista ratings recientes (moderación de contenido)."""
        ratings = Rating.query.order_by(Rating.creado_en.desc()).limit(50).all()
        return {"items": ratings, "total": len(ratings)}


@blp.route("/content/<int:rating_id>/moderate")
class AdminContentModerate(MethodView):
    @admin_required
    @blp.arguments(ContentModerateSchema)
    @blp.response(200)
    def patch(self, data, rating_id):
        """Oculta (soft, reportado=True) o elimina una calificación."""
        rating = db.get_or_404(Rating, rating_id)
        action = data["action"]
        before = {"reportado": rating.reportado}
        if action == "hide":
            rating.reportado = True
            after = {"reportado": True, "action": "hide"}
        else:  # delete
            db.session.delete(rating)
            after = {"action": "delete"}
        write_audit(
            _actor_id(), f"content.moderate.{action}", "rating",
            rating_id, before, after, _client_ip(),
        )
        db.session.commit()
        return {"id": rating_id, "action": action}
