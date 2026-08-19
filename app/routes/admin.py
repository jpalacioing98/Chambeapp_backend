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
from app.models.solicitud import Solicitud, Rating, EstadoSolicitud
from app.models.contract import Contract, EstadoContrato, Dispute
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
    SolicitudModerateSchema,
    SolicitudListResponseSchema,
    ContractModerateSchema,
    ContractListSchema,
    ContractListResponseSchema,
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
        services_total = Solicitud.query.count()
        contracts_total = Contract.query.count()
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
            "contracts_total": contracts_total,
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
# FASE 2 — Moderación de solicitudes
# ==========================================================================
_SOLICITUD_ACTION_ESTADO = {
    "approve": EstadoSolicitud.PUBLICADO,
    "reject": EstadoSolicitud.RECHAZADO,
    "hide": EstadoSolicitud.OCULTO,
}


@blp.route("/solicitudes")
class AdminSolicitudList(MethodView):
    @admin_required
    @blp.response(200, SolicitudListResponseSchema)
    def get(self):
        """Lista solicitudes con filtros (q, status) — máx 50."""
        query = Solicitud.query
        q = request.args.get("q")
        if q:
            like = f"%{q}%"
            query = query.filter(
                (Solicitud.titulo.ilike(like)) | (Solicitud.descripcion.ilike(like))
            )
        status = request.args.get("status")
        if status:
            query = query.filter(Solicitud.estado == EstadoSolicitud(status))
        total = query.count()
        solicitudes = query.order_by(Solicitud.creado_en.desc()).limit(50).all()
        return {"items": solicitudes, "total": total}


@blp.route("/solicitudes/<int:solicitud_id>/moderate")
class AdminSolicitudModerate(MethodView):
    @admin_required
    @blp.arguments(SolicitudModerateSchema)
    @blp.response(200)
    def patch(self, data, solicitud_id):
        """Modera una solicitud: approve | reject | hide."""
        solicitud = db.get_or_404(Solicitud, solicitud_id)
        nuevo = _SOLICITUD_ACTION_ESTADO[data["action"]]
        before = {"estado": solicitud.estado.value}
        solicitud.estado = nuevo
        write_audit(
            _actor_id(), f"solicitud.moderate.{data['action']}", "solicitud",
            solicitud.id, before, {"estado": nuevo.value}, _client_ip(),
        )
        db.session.commit()
        return {"id": solicitud.id, "estado": solicitud.estado.value}


# ==========================================================================
# FASE 2 — Moderación de contratos
# ==========================================================================
_CONTRACT_ACTION_ESTADO = {
    "cancel": EstadoContrato.CANCELADO,
    "flag": EstadoContrato.MARCADO,
}


@blp.route("/contracts")
class AdminContractList(MethodView):
    @admin_required
    @blp.response(200, ContractListResponseSchema)
    def get(self):
        """Lista contratos con filtro opcional de status — máx 50."""
        query = Contract.query
        status = request.args.get("status")
        if status:
            query = query.filter(Contract.estado == EstadoContrato(status))
        total = query.count()
        contracts = query.order_by(Contract.creado_en.desc()).limit(50).all()
        for o in contracts:
            payment = Payment.query.filter_by(contract_id=o.id).first()
            o.monto = payment.monto if payment else None
        return {"items": contracts, "total": total}


@blp.route("/contracts/<int:contract_id>/moderate")
class AdminContractModerate(MethodView):
    @admin_required
    @blp.arguments(ContractModerateSchema)
    @blp.response(200)
    def patch(self, data, contract_id):
        """Modera un contrato: cancel | flag."""
        contract = db.get_or_404(Contract, contract_id)
        nuevo = _CONTRACT_ACTION_ESTADO[data["action"]]
        before = {"estado": contract.estado.value}
        contract.estado = nuevo
        write_audit(
            _actor_id(), f"contract.moderate.{data['action']}", "contract",
            contract.id, before, {"estado": nuevo.value}, _client_ip(),
        )
        db.session.commit()
        return {"id": contract.id, "estado": contract.estado.value}


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
        """Detalle de disputa + datos de contrato/pago asociados."""
        dispute = db.get_or_404(Dispute, dispute_id)
        contract = db.session.get(Contract, dispute.contract_id)
        payment = Payment.query.filter_by(contract_id=dispute.contract_id).first()
        data = DisputeDetailSchema().dump(dispute)
        data["contract"] = (
            {
                "id": contract.id,
                "estado": contract.estado.value,
                "comprador_id": contract.solicitante_id,
                "vendedor_id": contract.proveedor_id,
                "servicio_id": contract.service_id,
            }
            if contract
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
        contract = db.session.get(Contract, dispute.contract_id)
        payment = Payment.query.filter_by(contract_id=dispute.contract_id).first()

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
