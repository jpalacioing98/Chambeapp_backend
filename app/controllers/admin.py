"""Admin blueprint (RBAC Fase 1-2) + División regional (Fase 4).

Todos los endpoints requieren rol admin O superadmin (ver @admin_required).
Registrado en /api/v1/admin.

División regional: un admin regional (User.region_id) opera únicamente
sobre los recursos de su región (usuarios, verificaciones, solicitudes,
contratos, disputas, tickets y contenido). El superadmin (sin región)
ve todo. El admin regional puede crear su propio personal (verificador /
soporte) mediante /admin/staff.
"""

import json
from datetime import datetime, timezone

from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import get_jwt_identity
from sqlalchemy import or_

from app.extensions import db
from app.auth.decorators import admin_required, role_required
from app.auth.region import region_scope_id
from app.models.user import User, RolUsuario, Verification
from app.models.solicitud import Solicitud, Rating, EstadoSolicitud
from app.models.oferta import Oferta
from app.models.contract import Contract, EstadoContrato, Dispute
from app.models.payment import Payment, EstadoPago
from app.models.ticket import Ticket
from app.models.chat import Conversation, Message
from app.services.realtime import safe_emit
from app.services.support_events import (
    emit_disputa_resuelta,
    emit_dispute_chat,
    emit_ticket_actualizado,
    notificar_chat_disputa_habilitado,
    notificar_disputa_resuelta,
)
from app.models.audit import write_audit
from app.schemas.chat import MessageSchema
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
    DisputeChatSchema,
    DisputeMessageSchema,
    DisputeVariablesSchema,
    TicketListResponseSchema,
    TicketDetailSchema,
    TicketPatchSchema,
    ContentReportResponseSchema,
    ContentModerateSchema,
    StaffCreateSchema,
    StaffListResponseSchema,
    TarifasCobroUpdateSchema,
    TarifasCobroResponseSchema,
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


def _assert_solicitud_in_region(solicitud: Solicitud, scope) -> None:
    """404 si la solicitud (negociación) no pertenece a la región del actor."""
    if scope is None:
        return
    solicitante = db.session.get(User, solicitud.solicitante_id)
    if solicitante is None or solicitante.region_id != scope:
        abort(404, message="Recurso no encontrado en tu región.")


def _disputa_solicitud(dispute: Dispute, contract: Contract | None) -> Solicitud | None:
    """Solicitud de una disputa (con o sin contrato)."""
    if dispute.solicitud_id:
        return db.session.get(Solicitud, dispute.solicitud_id)
    if contract is not None:
        return db.session.get(Solicitud, contract.service_id)
    return None


def _disputa_pds(dispute: Dispute, solicitud: Solicitud | None) -> User | None:
    """PDS de la negociación, para disputas abiertas antes del contrato."""
    if solicitud is None:
        return None
    oferta = (
        db.session.get(Oferta, dispute.oferta_id)
        if dispute.oferta_id
        else Oferta.query.filter_by(solicitud_id=solicitud.id)
        .order_by(Oferta.created_at.desc())
        .first()
    )
    return db.session.get(User, oferta.pds_id) if oferta is not None else None


def _disputa_oferta(dispute: Dispute, contract: Contract | None, solicitud: Solicitud | None):
    """Oferta asociada a la disputa (contrato o negociación previa)."""
    if contract is not None and contract.oferta_id:
        oferta = db.session.get(Oferta, contract.oferta_id)
        if oferta is not None:
            return oferta
    if dispute.oferta_id:
        oferta = db.session.get(Oferta, dispute.oferta_id)
        if oferta is not None:
            return oferta
    if solicitud is not None:
        return (
            Oferta.query.filter_by(solicitud_id=solicitud.id)
            .order_by(Oferta.created_at.desc())
            .first()
        )
    return None


def _negociacion_variables(contract: Contract | None, oferta) -> dict:
    """Valores efectivos de la negociación para el panel de soporte."""
    monto = contract.monto if contract is not None else None
    fecha = contract.fecha_deseada if contract is not None else None
    horario = contract.horario if contract is not None else None
    condiciones = contract.condiciones if contract is not None else None

    if oferta is not None:
        if monto is None:
            if oferta.estado == "contraoferta" and oferta.contra_monto is not None:
                monto = oferta.contra_monto
            elif oferta.monto_final is not None:
                monto = oferta.monto_final
            else:
                monto = oferta.monto
        if fecha is None:
            fecha = oferta.contra_fecha_deseada or oferta.fecha_deseada
        if horario is None:
            horario = oferta.contra_horario or oferta.horario
        if condiciones is None:
            condiciones = oferta.condiciones

    textos = []
    for condicion in condiciones or []:
        if isinstance(condicion, dict):
            texto = condicion.get("texto")
        else:
            texto = str(condicion)
        if texto:
            textos.append(texto)

    return {
        "oferta_id": oferta.id if oferta is not None else None,
        "origen": "contrato" if contract is not None else "oferta" if oferta is not None else None,
        "monto": monto,
        "fecha_deseada": fecha.isoformat() if fecha else None,
        "horario": horario,
        "condiciones": textos,
    }


def _dispute_user_ids_for_admin(contract, solicitud, dispute) -> set[int]:
    if contract is not None:
        return {contract.solicitante_id, contract.proveedor_id}
    if solicitud is None:
        return set()
    ids = {solicitud.solicitante_id}
    proveedor = _disputa_pds(dispute, solicitud)
    if proveedor is not None:
        ids.add(proveedor.id)
    return ids


def _decision_payload(dispute, variables: dict) -> dict:
    return {
        "disputeId": dispute.id,
        "estado": dispute.decision_estado,
        "solicitante": dispute.decision_solicitante,
        "proveedor": dispute.decision_proveedor,
        "negociacionCerrada": bool(dispute.negociacion_cerrada),
        "monto": variables.get("monto"),
        "fecha": variables.get("fecha_deseada"),
        "horario": variables.get("horario"),
        "condiciones": variables.get("condiciones") or [],
    }


def _encode_decision(payload: dict) -> str:
    return "⟦c:decision⟧" + json.dumps(payload, ensure_ascii=False)


def _user_brief(user) -> dict | None:
    """Datos mínimos de un usuario para detalles de disputas/tickets."""
    if user is None:
        return None
    return {
        "id": user.id,
        "nombre": user.nombre,
        "email": user.email,
        "rol": user.rol.value,
    }


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
            solicitud_ids = db.select(Solicitud.id).where(
                Solicitud.solicitante_id.in_(_region_user_ids(scope))
            )
            dq = dq.filter(
                or_(
                    Dispute.contract_id.in_(contract_ids),
                    Dispute.solicitud_id.in_(solicitud_ids),
                )
            )
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
    @role_required(["admin", "superadmin", "soporte"])
    @blp.response(200, DisputeListResponseSchema)
    def get(self):
        """Lista disputas (status por defecto 'abierta') — scoped por región.

        Una disputa pertenece a la región del solicitante del contrato.
        """
        scope = region_scope_id(_actor())
        status = request.args.get("status", "abierta")
        if status in ("cerrada", "resuelta"):
            query = Dispute.query.filter(
                Dispute.status.in_(("cerrada", "resuelta"))
            )
        else:
            query = Dispute.query.filter(Dispute.status == status)
        if scope is not None:
            region_users = _region_user_ids(scope)
            contract_ids = db.select(Contract.id).where(
                Contract.solicitante_id.in_(region_users)
            )
            solicitud_ids = db.select(Solicitud.id).where(
                Solicitud.solicitante_id.in_(region_users)
            )
            query = query.filter(
                or_(
                    Dispute.contract_id.in_(contract_ids),
                    Dispute.solicitud_id.in_(solicitud_ids),
                )
            )
        disputes = query.order_by(Dispute.created_at.desc()).all()
        return {"items": disputes, "total": len(disputes)}


@blp.route("/disputes/<int:dispute_id>")
class AdminDisputeDetail(MethodView):
    @role_required(["admin", "superadmin", "soporte"])
    @blp.response(200)
    def get(self, dispute_id):
        """Detalle de disputa + datos de contrato/pago asociados."""
        scope = region_scope_id(_actor())
        dispute = db.get_or_404(Dispute, dispute_id)
        contract = (
            db.session.get(Contract, dispute.contract_id)
            if dispute.contract_id
            else None
        )
        solicitud = _disputa_solicitud(dispute, contract)
        if contract is not None:
            _assert_contract_in_region(contract, scope)
        elif solicitud is not None:
            _assert_solicitud_in_region(solicitud, scope)
        else:
            abort(404, message="Recurso no encontrado en tu región.")

        payment = (
            Payment.query.filter_by(contract_id=dispute.contract_id).first()
            if dispute.contract_id
            else None
        )
        data = DisputeDetailSchema().dump(dispute)

        solicitante = proveedor = servicio = None
        if contract is not None:
            solicitante = db.session.get(User, contract.solicitante_id)
            proveedor = db.session.get(User, contract.proveedor_id)
            servicio = db.session.get(Solicitud, contract.service_id)
        elif solicitud is not None:
            solicitante = db.session.get(User, solicitud.solicitante_id)
            proveedor = _disputa_pds(dispute, solicitud)
            servicio = solicitud

        data["contract"] = (
            {
                "id": contract.id,
                "estado": contract.estado.value,
                "monto": contract.monto,
                "fecha_deseada": (
                    contract.fecha_deseada.isoformat()
                    if contract.fecha_deseada
                    else None
                ),
                "horario": contract.horario,
                "creado_en": (
                    contract.creado_en.isoformat() if contract.creado_en else None
                ),
                "solicitante": _user_brief(solicitante),
                "proveedor": _user_brief(proveedor),
                "servicio": (
                    {
                        "id": servicio.id,
                        "titulo": servicio.titulo,
                        "categoria": servicio.categoria,
                        "estado": servicio.estado.value,
                        "presupuesto": servicio.presupuesto,
                    }
                    if servicio
                    else None
                ),
            }
            if contract
            else None
        )
        data["solicitud"] = (
            {
                "id": solicitud.id,
                "titulo": solicitud.titulo,
                "categoria": solicitud.categoria,
                "estado": solicitud.estado.value,
                "presupuesto": solicitud.presupuesto,
                "solicitante": _user_brief(solicitante),
                "proveedor": _user_brief(proveedor),
            }
            if solicitud
            else None
        )
        data["negociacion"] = _negociacion_variables(
            contract, _disputa_oferta(dispute, contract, solicitud)
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
        data["resolved_by_user"] = (
            _user_brief(db.session.get(User, dispute.resolved_by))
            if dispute.resolved_by
            else None
        )
        return data


@blp.route("/disputes/<int:dispute_id>/chat")
class AdminDisputeChat(MethodView):
    @role_required(["admin", "superadmin", "soporte"])
    @blp.arguments(DisputeChatSchema)
    @blp.response(200)
    def patch(self, data, dispute_id):
        """Habilita o bloquea el chat entre las partes de la disputa."""
        scope = region_scope_id(_actor())
        dispute = db.get_or_404(Dispute, dispute_id)
        contract = (
            db.session.get(Contract, dispute.contract_id)
            if dispute.contract_id
            else None
        )
        solicitud = _disputa_solicitud(dispute, contract)
        if contract is not None:
            _assert_contract_in_region(contract, scope)
        elif solicitud is not None:
            _assert_solicitud_in_region(solicitud, scope)
        if dispute.status != "abierta":
            abort(400, message="La disputa ya está cerrada.")

        solicitante_id = (
            contract.solicitante_id
            if contract is not None
            else solicitud.solicitante_id
            if solicitud is not None
            else None
        )
        proveedor = (
            None
            if contract is not None
            else _disputa_pds(dispute, solicitud) if solicitud is not None else None
        )
        proveedor_id = (
            contract.proveedor_id
            if contract is not None
            else proveedor.id if proveedor is not None else None
        )

        habilitado = bool(data["habilitado"])
        usuario_id = data.get("usuario_id")
        if usuario_id is None:
            sol_habilitado = habilitado
            prov_habilitado = habilitado
        elif usuario_id == solicitante_id:
            sol_habilitado = habilitado
            prov_habilitado = dispute.chat_habilitado_proveedor
        elif usuario_id == proveedor_id:
            sol_habilitado = dispute.chat_habilitado_solicitante
            prov_habilitado = habilitado
        else:
            abort(400, message="El usuario no participa en esta disputa.")

        before = {
            "chat_habilitado": dispute.chat_habilitado,
            "chat_habilitado_solicitante": dispute.chat_habilitado_solicitante,
            "chat_habilitado_proveedor": dispute.chat_habilitado_proveedor,
        }
        dispute.chat_habilitado_solicitante = sol_habilitado
        dispute.chat_habilitado_proveedor = prov_habilitado
        dispute.chat_habilitado = sol_habilitado and prov_habilitado
        after = {
            "chat_habilitado": dispute.chat_habilitado,
            "chat_habilitado_solicitante": dispute.chat_habilitado_solicitante,
            "chat_habilitado_proveedor": dispute.chat_habilitado_proveedor,
        }
        write_audit(
            _actor_id(),
            "dispute.chat",
            "dispute",
            dispute.id,
            before,
            after,
            _client_ip(),
        )
        db.session.commit()
        habilitados_ahora = set()
        if not before["chat_habilitado_solicitante"] and sol_habilitado:
            habilitados_ahora.add(solicitante_id)
        if not before["chat_habilitado_proveedor"] and prov_habilitado:
            habilitados_ahora.add(proveedor_id)
        habilitados_ahora.discard(None)
        notificar_chat_disputa_habilitado(
            dispute, habilitados_ahora, contract, solicitud
        )
        emit_dispute_chat(dispute, contract, solicitud)
        return {"id": dispute.id, **after}


@blp.route("/disputes/<int:dispute_id>/variables")
class AdminDisputeVariables(MethodView):
    @role_required(["admin", "superadmin", "soporte"])
    @blp.arguments(DisputeVariablesSchema)
    @blp.response(200)
    def patch(self, data, dispute_id):
        """Ajusta monto, fecha, horario y condiciones de la negociación."""
        scope = region_scope_id(_actor())
        dispute = db.get_or_404(Dispute, dispute_id)
        contract = (
            db.session.get(Contract, dispute.contract_id)
            if dispute.contract_id
            else None
        )
        solicitud = _disputa_solicitud(dispute, contract)
        if contract is not None:
            _assert_contract_in_region(contract, scope)
        elif solicitud is not None:
            _assert_solicitud_in_region(solicitud, scope)
        else:
            abort(400, message="La disputa no tiene una negociación asociada.")

        oferta = _disputa_oferta(dispute, contract, solicitud)
        if contract is None and oferta is None:
            abort(400, message="La disputa no tiene una negociación asociada.")

        before = _negociacion_variables(contract, oferta)

        if "monto" in data:
            monto = data["monto"]
            if contract is not None:
                contract.monto = monto
            if oferta is not None:
                oferta.monto = monto
                oferta.contra_monto = monto
                oferta.monto_final = monto
            if solicitud is not None:
                solicitud.presupuesto = (
                    int(round(monto)) if monto is not None else None
                )

        if "fecha_deseada" in data:
            fecha = data["fecha_deseada"]
            if contract is not None:
                contract.fecha_deseada = fecha
            if oferta is not None:
                oferta.fecha_deseada = fecha
                oferta.contra_fecha_deseada = fecha
            if solicitud is not None:
                solicitud.fecha_deseada = fecha

        if "horario" in data:
            horario = data["horario"]
            if contract is not None:
                contract.horario = horario
            if oferta is not None:
                oferta.horario = horario
                oferta.contra_horario = horario
            if solicitud is not None:
                solicitud.horario = horario

        if "condiciones" in data:
            ahora = datetime.now(timezone.utc).isoformat()
            condiciones = [
                {"texto": texto.strip(), "autor": "soporte", "fecha": ahora}
                for texto in (data.get("condiciones") or [])
                if texto.strip()
            ]
            if contract is not None:
                contract.condiciones = condiciones
            if oferta is not None:
                oferta.condiciones = condiciones

        after = _negociacion_variables(contract, oferta)
        dispute.status = "cerrada"
        dispute.resolved_by = _actor_id()
        dispute.resolved_at = datetime.now(timezone.utc)
        dispute.resolution = "Decisión de soporte propuesta a las partes."
        dispute.decision_estado = "pendiente"
        dispute.decision_solicitante = None
        dispute.decision_proveedor = None
        dispute.negociacion_cerrada = False

        solicitante_id = (
            contract.solicitante_id
            if contract is not None
            else solicitud.solicitante_id if solicitud is not None else None
        )
        proveedor = (
            None
            if contract is not None
            else _disputa_pds(dispute, solicitud) if solicitud is not None else None
        )
        proveedor_id = (
            contract.proveedor_id
            if contract is not None
            else proveedor.id if proveedor is not None else None
        )
        participantes = {uid for uid in (solicitante_id, proveedor_id) if uid}
        if solicitante_id is None or proveedor_id is None:
            abort(400, message="La disputa no tiene dos partes para notificar.")

        a, b = Conversation.normalize(solicitante_id, proveedor_id)
        conv = Conversation.query.filter_by(user_a_id=a, user_b_id=b).first()
        if conv is None:
            conv = Conversation(user_a_id=a, user_b_id=b)
            db.session.add(conv)
            db.session.flush()

        payload = _decision_payload(dispute, after)
        contenido = _encode_decision(payload)
        if dispute.decision_message_id:
            decision_msg = db.session.get(Message, dispute.decision_message_id)
        else:
            decision_msg = None
        if decision_msg is None:
            decision_msg = Message(
                conversation_id=conv.id,
                sender_id=_actor_id(),
                contenido=contenido,
                leido=False,
                es_soporte=True,
            )
            db.session.add(decision_msg)
            db.session.flush()
            dispute.decision_message_id = decision_msg.id
        else:
            decision_msg.contenido = contenido
            decision_msg.es_soporte = True
        write_audit(
            _actor_id(),
            "dispute.variables",
            "dispute",
            dispute.id,
            before,
            after,
            _client_ip(),
        )
        db.session.commit()

        evento = "contrato:actualizado" if contract is not None else "oferta:actualizada"
        evento_payload = {"id": contract.id if contract is not None else oferta.id}
        for user_id in participantes:
            safe_emit(evento, evento_payload, room=f"user:{user_id}")
            safe_emit(
                "dispute:decision",
                {"id": dispute.id, **payload},
                room=f"user:{user_id}",
            )

        return {
            "id": dispute.id,
            "negociacion": after,
            "decision": payload,
        }


@blp.route("/disputes/<int:dispute_id>/messages")
class AdminDisputeMessage(MethodView):
    @role_required(["admin", "superadmin", "soporte"])
    @blp.arguments(DisputeMessageSchema)
    @blp.response(201, MessageSchema)
    def post(self, data, dispute_id):
        """Publica un mensaje de soporte en el chat de las partes."""
        scope = region_scope_id(_actor())
        dispute = db.get_or_404(Dispute, dispute_id)
        contract = (
            db.session.get(Contract, dispute.contract_id)
            if dispute.contract_id
            else None
        )
        solicitud = _disputa_solicitud(dispute, contract)
        if contract is not None:
            _assert_contract_in_region(contract, scope)
            solicitante = db.session.get(User, contract.solicitante_id)
            proveedor = db.session.get(User, contract.proveedor_id)
        elif solicitud is not None:
            _assert_solicitud_in_region(solicitud, scope)
            solicitante = db.session.get(User, solicitud.solicitante_id)
            proveedor = _disputa_pds(dispute, solicitud)
        else:
            abort(400, message="La disputa no tiene una conversación asociada.")

        if solicitante is None or proveedor is None:
            abort(400, message="La disputa no tiene dos partes asociadas.")

        a, b = Conversation.normalize(solicitante.id, proveedor.id)
        conv = Conversation.query.filter_by(user_a_id=a, user_b_id=b).first()
        if conv is None:
            conv = Conversation(user_a_id=a, user_b_id=b)
            db.session.add(conv)
            db.session.flush()

        msg = Message(
            conversation_id=conv.id,
            sender_id=_actor_id(),
            contenido=data["contenido"],
            leido=False,
            es_soporte=True,
        )
        db.session.add(msg)
        db.session.commit()

        payload = MessageSchema().dump(msg)
        if not conv.oculta:
            safe_emit("message", payload, room=f"conversation_{conv.id}")
            safe_emit("message", payload, room=f"user:{solicitante.id}")
            safe_emit("message", payload, room=f"user:{proveedor.id}")
        return msg, 201


@blp.route("/disputes/<int:dispute_id>/conversation")
class AdminDisputeConversation(MethodView):
    @role_required(["admin", "superadmin", "soporte"])
    @blp.response(200)
    def get(self, dispute_id):
        """Chat entre los usuarios de la negociación donde se radicó la disputa."""
        scope = region_scope_id(_actor())
        dispute = db.get_or_404(Dispute, dispute_id)
        contract = (
            db.session.get(Contract, dispute.contract_id)
            if dispute.contract_id
            else None
        )
        solicitud = _disputa_solicitud(dispute, contract)
        if contract is not None:
            _assert_contract_in_region(contract, scope)
            solicitante = db.session.get(User, contract.solicitante_id)
            proveedor = db.session.get(User, contract.proveedor_id)
        elif solicitud is not None:
            _assert_solicitud_in_region(solicitud, scope)
            solicitante = db.session.get(User, solicitud.solicitante_id)
            proveedor = _disputa_pds(dispute, solicitud)
        else:
            return {
                "id": None,
                "solicitante": None,
                "proveedor": None,
                "messages": [],
            }

        if solicitante is None or proveedor is None:
            return {
                "id": None,
                "solicitante": _user_brief(solicitante),
                "proveedor": _user_brief(proveedor),
                "messages": [],
            }

        a, b = Conversation.normalize(solicitante.id, proveedor.id)
        conv = Conversation.query.filter_by(user_a_id=a, user_b_id=b).first()
        messages = []
        if conv is not None:
            messages = (
                Message.query.filter_by(conversation_id=conv.id)
                .order_by(Message.creado_en.asc())
                .all()
            )
        return {
            "id": conv.id if conv is not None else None,
            "solicitante": _user_brief(solicitante),
            "proveedor": _user_brief(proveedor),
            "messages": MessageSchema().dump(messages, many=True),
        }


@blp.route("/disputes/<int:dispute_id>/resolve")
class AdminDisputeResolve(MethodView):
    @role_required(["admin", "superadmin", "soporte"])
    @blp.arguments(DisputeResolveSchema)
    @blp.response(200)
    def post(self, data, dispute_id):
        """Resuelve una disputa (solo registro; no hay retención de fondos)."""
        scope = region_scope_id(_actor())
        dispute = db.get_or_404(Dispute, dispute_id)
        contract = (
            db.session.get(Contract, dispute.contract_id)
            if dispute.contract_id
            else None
        )
        solicitud = _disputa_solicitud(dispute, contract)
        if contract is not None:
            _assert_contract_in_region(contract, scope)
        elif solicitud is not None:
            _assert_solicitud_in_region(solicitud, scope)
        if dispute.status in ("resuelta", "cerrada"):
            abort(400, message="La disputa ya está cerrada.")

        before = {
            "status": dispute.status,
            "resolution": dispute.resolution,
        }
        dispute.resolved_by = _actor_id()
        dispute.resolved_at = datetime.now(timezone.utc)
        dispute.resolution = data["resolution"]
        dispute.status = "cerrada"
        dispute.chat_habilitado = True
        dispute.chat_habilitado_solicitante = True
        dispute.chat_habilitado_proveedor = True

        write_audit(
            _actor_id(), "dispute.resolve", "dispute", dispute.id,
            before,
            {"status": "cerrada", "resolution": data["resolution"]},
            _client_ip(),
        )
        db.session.commit()

        solicitante = (
            db.session.get(User, contract.solicitante_id)
            if contract is not None
            else db.session.get(User, solicitud.solicitante_id)
            if solicitud is not None
            else None
        )
        emit_disputa_resuelta(
            dispute, solicitante.region_id if solicitante else None
        )
        emit_dispute_chat(dispute, contract, solicitud)
        notificar_disputa_resuelta(
            dispute, contract, dispute.resolution, solicitud=solicitud
        )

        return {
            "id": dispute.id,
            "status": "cerrada",
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

        actor_id = _actor_id()
        conversations = Conversation.query.filter(
            (Conversation.user_a_id == actor_id)
            | (Conversation.user_b_id == actor_id)
        ).all()
        conversacion_por_usuario = {
            (
                conv.user_b_id if conv.user_a_id == actor_id else conv.user_a_id
            ): conv.id
            for conv in conversations
        }
        for ticket in tickets:
            ticket.conversation_id = conversacion_por_usuario.get(ticket.user_id)

        return {"items": tickets, "total": total}


@blp.route("/tickets/<int:ticket_id>")
class AdminTicketPatch(MethodView):
    @role_required(["admin", "superadmin", "soporte"])
    @blp.response(200, TicketDetailSchema)
    def get(self, ticket_id):
        """Detalle completo del ticket + conversación de soporte existente."""
        scope = region_scope_id(_actor())
        ticket = db.get_or_404(Ticket, ticket_id)
        _assert_in_region(ticket.user_id, scope)

        a, b = Conversation.normalize(_actor_id(), ticket.user_id)
        conv = Conversation.query.filter_by(user_a_id=a, user_b_id=b).first()
        ticket.conversation_id = conv.id if conv is not None else None
        return ticket

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

        ticket_user = db.session.get(User, ticket.user_id)
        region_id = ticket_user.region_id if ticket_user else None
        emit_ticket_actualizado(ticket, region_id)

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
# ==========================================================================
# COBROS EN MONEDAS (configuración del superadmin)
# ==========================================================================

@blp.route("/cobros")
class AdminCobros(MethodView):
    @role_required(["superadmin"])
    @blp.response(200, TarifasCobroResponseSchema)
    def get(self):
        """Tarifas de cobro y configuración efectiva (+ última actualización)."""
        from app.services.cobros import get_config_publica, get_tarifas

        ultima = _ultima_actualizacion_tarifas()
        return {
            "tarifas": get_tarifas(),
            "config": get_config_publica(),
            "updated_at": ultima["updated_at"],
            "updated_by": ultima["updated_by"],
        }

    @role_required(["superadmin"])
    @blp.arguments(TarifasCobroUpdateSchema)
    @blp.response(200, TarifasCobroResponseSchema)
    def put(self, data):
        """Actualiza tarifas y porcentajes (recalcula paquetes si cambia la moneda)."""
        from app.services.cobros import (
            actualizar_tarifas,
            get_config_publica,
            get_tarifas,
        )

        try:
            actualizar_tarifas(data, _actor_id())
        except ValueError as e:
            abort(400, message=str(e))

        write_audit(
            _actor_id(), "cobros.update", "tarifas_cobro", None,
            None, data, _client_ip(),
        )
        db.session.commit()
        ultima = _ultima_actualizacion_tarifas()
        return {
            "tarifas": get_tarifas(),
            "config": get_config_publica(),
            "updated_at": ultima["updated_at"],
            "updated_by": ultima["updated_by"],
        }


def _ultima_actualizacion_tarifas() -> dict:
    """Última modificación de tarifas (para mostrar 'actualizado el …')."""
    from app.models.cobro import TarifaCobro

    ultima = (
        TarifaCobro.query.order_by(TarifaCobro.actualizado_en.desc()).first()
    )
    if ultima is None:
        return {"updated_at": None, "updated_by": None}
    return {
        "updated_at": (
            ultima.actualizado_en.isoformat() if ultima.actualizado_en else None
        ),
        "updated_by": ultima.actualizado_por,
    }
