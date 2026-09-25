"""Admin blueprint (RBAC Fase 1-2) + División regional (Fase 4).

Todos los endpoints requieren rol admin O superadmin (ver @admin_required).
Registrado en /api/v1/admin.

División regional: un admin regional (User.region_id) opera únicamente
sobre los recursos de su región (usuarios, verificaciones, solicitudes,
contratos, disputas, tickets y contenido). El superadmin (sin región)
ve todo. El admin regional puede crear su propio personal (verificador /
soporte) mediante /admin/staff.
"""

from datetime import datetime, timezone

from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import get_jwt_identity

from app.extensions import db
from app.auth.decorators import admin_required, role_required
from app.auth.region import region_scope_id
from app.models.user import User, RolUsuario, Verification
from app.models.solicitud import Solicitud, Rating, EstadoSolicitud
from app.models.contract import Contract, EstadoContrato, Dispute
from app.models.payment import Payment, EstadoPago
from app.models.ticket import Ticket
from app.models.audit import write_audit
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
    StaffCreateSchema,
    StaffListResponseSchema,
)

blp = Blueprint("admin", __name__, description="Panel administrativo (RBAC + regiones)")


def _actor_id() -> int:
    return int(get_jwt_identity())


def _actor() -> User:
    return db.get_or_404(User, _actor_id())


def _client_ip() -> str:
    return request.remote_addr or "127.0.0.1"


def _region_user_ids(scope: int):
    """Subconsulta de ids de usuario de una región (para filtros .in_)."""
    return db.select(User.id).where(User.region_id == scope)


def _assert_in_region(user_id: int, scope) -> None:
    """404 si el usuario dueño no pertenece a la región del actor."""
    if scope is None:
        return
    owner = db.session.get(User, user_id)
    if owner is None or owner.region_id != scope:
        abort(404, message="Recurso no encontrado en tu región.")


def _assert_contract_in_region(contract: Contract, scope) -> None:
    """404 si el contrato no pertenece a la región del actor.

    Regla anti doble-conteo: el dueño de un contrato (y de sus disputas/
    pagos) es la región del SOLICITANTE. Cada caso se modera en una sola
    región.
    """
    if scope is None:
        return
    solicitante = db.session.get(User, contract.solicitante_id)
    if solicitante is None or solicitante.region_id != scope:
        abort(404, message="Recurso no encontrado en tu región.")


def _assert_rating_in_region(rating: Rating, scope) -> None:
    """404 si el dueño de la solicitud calificada no está en la región."""
    if scope is None:
        return
    solicitud = db.session.get(Solicitud, rating.service_id)
    if solicitud is None:
        abort(404, message="Solicitud no encontrada.")
    _assert_in_region(solicitud.solicitante_id, scope)


@blp.route("/users")
class AdminUserList(MethodView):
    @admin_required
    @blp.response(200, UserListResponseSchema)
    def get(self):
        """Lista usuarios con filtros (rol, status, q) — máx 50.

        Un admin regional solo ve los usuarios de su región.
        """
        scope = region_scope_id(_actor())
        query = User.query
        if scope is not None:
            query = query.filter(User.region_id == scope)
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
        scope = region_scope_id(_actor())
        _assert_in_region(user_id, scope)
        user = db.get_or_404(User, user_id)
        return UserDetailSchema().dump(user)


@blp.route("/users/<int:user_id>/role")
class AdminUserRole(MethodView):
    @admin_required
    @blp.arguments(RolePatchSchema)
    @blp.response(200, UserDetailSchema)
    def patch(self, data, user_id):
        """Cambia el rol de un usuario (revoca tokens vía role_version++).

        Solo el superadmin puede otorgar admin/superadmin; un admin regional
        no puede ascender a nadie y solo opera dentro de su región.
        """
        actor = _actor()
        scope = region_scope_id(actor)
        _assert_in_region(user_id, scope)
        user = db.get_or_404(User, user_id)
        new_role = data["role"]
        if new_role == "superadmin":
            abort(403, message="Solo un superadmin puede asignar el rol superadmin.")
        if new_role == "admin" and scope is not None:
            abort(403, message="Solo un superadmin puede asignar el rol admin.")
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
        scope = region_scope_id(_actor())
        _assert_in_region(user_id, scope)
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
        """Métricas generales para el dashboard admin (scoped por región)."""
        scope = region_scope_id(_actor())
        uids = _region_user_ids(scope) if scope is not None else None
        # Propiedad: la región del solicitante es la única dueña del contrato
        # (y de sus pagos/disputas) → cada caso se cuenta UNA sola vez.
        contract_ids = (
            db.select(Contract.id).where(Contract.solicitante_id.in_(uids))
            if uids is not None
            else None
        )

        uq = User.query.filter(User.region_id == scope) if uids is not None else User.query
        users_total = uq.count()
        users_active = uq.filter(User.status == "active").count()

        sq = Solicitud.query.filter(Solicitud.solicitante_id.in_(uids)) if uids is not None else Solicitud.query
        services_total = sq.count()

        cq = (
            Contract.query.filter(Contract.id.in_(contract_ids))
            if contract_ids is not None
            else Contract.query
        )
        contracts_total = cq.count()

        rev_query = db.session.query(db.func.sum(Payment.monto)).filter(
            Payment.estado == EstadoPago.COMPLETADO
        )
        if contract_ids is not None:
            rev_query = rev_query.filter(Payment.contract_id.in_(contract_ids))
        revenue_total = rev_query.scalar() or 0

        dq = Dispute.query.filter(Dispute.status == "abierta")
        if contract_ids is not None:
            dq = dq.filter(Dispute.contract_id.in_(contract_ids))
        disputes_open = dq.count()

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
        scope = region_scope_id(_actor())
        status = request.args.get("status", "pending")
        query = Verification.query.filter(Verification.status == status)
        if scope is not None:
            query = query.filter(Verification.user_id.in_(_region_user_ids(scope)))
        verifs = query.order_by(Verification.created_at.desc()).all()
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
        scope = region_scope_id(_actor())
        v = db.get_or_404(Verification, verif_id)
        _assert_in_region(v.user_id, scope)
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
        scope = region_scope_id(_actor())
        v = db.get_or_404(Verification, verif_id)
        _assert_in_region(v.user_id, scope)
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
        """Lista solicitudes con filtros (q, status) — máx 50 (scoped)."""
        scope = region_scope_id(_actor())
        query = Solicitud.query
        if scope is not None:
            query = query.filter(Solicitud.solicitante_id.in_(_region_user_ids(scope)))
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
        scope = region_scope_id(_actor())
        solicitud = db.get_or_404(Solicitud, solicitud_id)
        _assert_in_region(solicitud.solicitante_id, scope)
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
        """Lista contratos con filtro opcional de status — máx 50 (scoped).

        Propiedad anti doble-conteo: cada contrato pertenece a la región de
        su SOLICITANTE (comprador), por lo que se lista en una sola región.
        """
        scope = region_scope_id(_actor())
        query = Contract.query
        if scope is not None:
            query = query.filter(Contract.solicitante_id.in_(_region_user_ids(scope)))
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
        scope = region_scope_id(_actor())
        contract = db.get_or_404(Contract, contract_id)
        _assert_contract_in_region(contract, scope)
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
# FASE 2 — Disputas / Pagos directos
# ==========================================================================
@blp.route("/disputes")
class AdminDisputeList(MethodView):
    @admin_required
    @blp.response(200, DisputeListResponseSchema)
    def get(self):
        """Lista disputas (status por defecto 'abierta') — scoped por región.

        Una disputa pertenece a la región del solicitante del contrato.
        """
        scope = region_scope_id(_actor())
        status = request.args.get("status", "abierta")
        query = Dispute.query.filter(Dispute.status == status)
        if scope is not None:
            contract_ids = db.select(Contract.id).where(
                Contract.solicitante_id.in_(_region_user_ids(scope))
            )
            query = query.filter(Dispute.contract_id.in_(contract_ids))
        disputes = query.order_by(Dispute.created_at.desc()).all()
        return {"items": disputes, "total": len(disputes)}


@blp.route("/disputes/<int:dispute_id>")
class AdminDisputeDetail(MethodView):
    @admin_required
    @blp.response(200)
    def get(self, dispute_id):
        """Detalle de disputa + datos de contrato/pago asociados."""
        scope = region_scope_id(_actor())
        dispute = db.get_or_404(Dispute, dispute_id)
        contract = db.session.get(Contract, dispute.contract_id)
        if contract is not None:
            _assert_contract_in_region(contract, scope)
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
                "comision_pds": payment.comision_pds,
                "comision_solicitante": payment.comision_solicitante,
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
        """Resuelve una disputa (solo registro; no hay retención de fondos)."""
        scope = region_scope_id(_actor())
        dispute = db.get_or_404(Dispute, dispute_id)
        contract = db.session.get(Contract, dispute.contract_id)
        if contract is not None:
            _assert_contract_in_region(contract, scope)
        if dispute.status == "resuelta":
            abort(400, message="La disputa ya está resuelta.")

        before = {
            "status": dispute.status,
            "resolution": dispute.resolution,
        }
        dispute.resolved_by = _actor_id()
        dispute.resolved_at = datetime.now(timezone.utc)
        dispute.resolution = data["resolution"]
        dispute.status = "resuelta"

        write_audit(
            _actor_id(), "dispute.resolve", "dispute", dispute.id,
            before,
            {"status": "resuelta", "resolution": data["resolution"]},
            _client_ip(),
        )
        db.session.commit()
        return {
            "id": dispute.id,
            "status": "resuelta",
        }


# ==========================================================================
# FASE 2 — Tickets de soporte (gestión admin)
# ==========================================================================
@blp.route("/tickets")
class AdminTicketList(MethodView):
    @role_required(["admin", "superadmin", "soporte"])
    @blp.response(200, TicketListResponseSchema)
    def get(self):
        """Lista tickets con filtro opcional de status — máx 50 (scoped).

        El soporte regional gestiona los tickets de los usuarios de su región.
        """
        scope = region_scope_id(_actor())
        query = Ticket.query
        if scope is not None:
            query = query.filter(Ticket.user_id.in_(_region_user_ids(scope)))
        status = request.args.get("status")
        if status:
            query = query.filter(Ticket.status == status)
        total = query.count()
        tickets = query.order_by(Ticket.created_at.desc()).limit(50).all()
        return {"items": tickets, "total": total}


@blp.route("/tickets/<int:ticket_id>")
class AdminTicketPatch(MethodView):
    @role_required(["admin", "superadmin", "soporte"])
    @blp.arguments(TicketPatchSchema)
    @blp.response(200)
    def patch(self, data, ticket_id):
        """Actualiza estado/asignación/prioridad de un ticket."""
        scope = region_scope_id(_actor())
        ticket = db.get_or_404(Ticket, ticket_id)
        _assert_in_region(ticket.user_id, scope)
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
        """Lista ratings recientes (moderación de contenido) — scoped."""
        scope = region_scope_id(_actor())
        query = Rating.query
        if scope is not None:
            solicitud_ids = db.select(Solicitud.id).where(
                Solicitud.solicitante_id.in_(_region_user_ids(scope))
            )
            query = query.filter(Rating.service_id.in_(solicitud_ids))
        ratings = query.order_by(Rating.creado_en.desc()).limit(50).all()
        return {"items": ratings, "total": len(ratings)}


@blp.route("/content/<int:rating_id>/moderate")
class AdminContentModerate(MethodView):
    @admin_required
    @blp.arguments(ContentModerateSchema)
    @blp.response(200)
    def patch(self, data, rating_id):
        """Oculta (soft, reportado=True) o elimina una calificación."""
        scope = region_scope_id(_actor())
        rating = db.get_or_404(Rating, rating_id)
        _assert_rating_in_region(rating, scope)
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


# ==========================================================================
# DIVISIÓN REGIONAL — Personal de la región (verificador/soporte)
# ==========================================================================
_STAFF_ROLES = [RolUsuario.VERIFICADOR, RolUsuario.SOPORTE]


@blp.route("/staff")
class AdminStaff(MethodView):
    @admin_required
    @blp.response(200, StaffListResponseSchema)
    def get(self):
        """Lista el personal (verificador/soporte) de la región del admin."""
        actor = _actor()
        scope = actor.region_id
        if scope is None:
            abort(400, message="Tu cuenta de admin no tiene una región asignada.")
        staff = (
            User.query.filter(User.rol.in_(_STAFF_ROLES), User.region_id == scope)
            .order_by(User.id)
            .all()
        )
        return {"items": staff, "total": len(staff)}

    @admin_required
    @blp.arguments(StaffCreateSchema)
    @blp.response(201, StaffListResponseSchema)
    def post(self, data):
        """Crea un verificador o soporte dentro de la región del admin."""
        actor = _actor()
        scope = actor.region_id
        if scope is None:
            abort(400, message="Tu cuenta de admin no tiene una región asignada.")
        if User.query.filter_by(email=data["email"]).first():
            abort(409, message="El email ya está registrado.")
        user = User(
            email=data["email"],
            rol=RolUsuario(data["rol"]),
            nombre=data["nombre"],
            acepto_tyc=True,
            activo=True,
            status="active",
            region_id=scope,
        )
        user.set_password(data["password"])
        db.session.add(user)
        db.session.flush()
        write_audit(
            _actor_id(), f"staff.create.{data['rol']}", "user", user.id,
            None,
            {"email": user.email, "rol": user.rol.value, "region_id": scope},
            _client_ip(),
        )
        db.session.commit()
        return {"items": [user], "total": 1}