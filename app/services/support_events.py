"""Eventos en tiempo real de soporte: tickets y disputas.

Además de emitir a las salas de soporte, crea notificaciones persistentes
para el staff (campana del panel) usando el mismo helper que KYC.
"""

import logging

from sqlalchemy import or_

from app.controllers.notifications import crear_notificacion
from app.extensions import db
from app.models.user import RolUsuario, User
from app.services.realtime import safe_emit
from app.services.staff_rooms import (
    SUPPORT_STAFF_ROLES,
    staff_support_rooms_for_region,
)

log = logging.getLogger(__name__)


def _support_recipients(region_id):
    query = User.query.filter(
        User.activo.is_(True),
        User.status == "active",
        User.rol.in_(SUPPORT_STAFF_ROLES),
    )
    if region_id is None:
        return query.filter(User.rol == RolUsuario.SUPERADMIN).all()
    return query.filter(
        or_(
            User.rol == RolUsuario.SUPERADMIN,
            User.region_id == region_id,
            User.region_id.is_(None),
        )
    ).all()


def _emit_support(event: str, payload: dict, region_id) -> None:
    for room in staff_support_rooms_for_region(region_id):
        safe_emit(event, payload, room=room)


def _notificar_staff(region_id, tipo, titulo, mensaje, datos) -> None:
    try:
        for recipient in _support_recipients(region_id):
            crear_notificacion(
                recipient.id,
                tipo,
                mensaje,
                titulo=titulo,
                datos=datos,
                respetar_preferencias=False,
                forzar_push=True,
            )
        db.session.commit()
    except Exception:  # noqa: BLE001 — el recurso ya quedó guardado
        db.session.rollback()
        log.exception("No se pudieron crear las notificaciones de soporte")


def notificar_nuevo_ticket(ticket, user) -> None:
    region_id = user.region_id
    payload = {
        "id": ticket.id,
        "subject": ticket.subject,
        "status": ticket.status,
        "priority": ticket.priority,
        "user_id": user.id,
        "region_id": region_id,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
    }
    _notificar_staff(
        region_id,
        "ticket_nuevo",
        "Nuevo ticket de soporte",
        f"{user.nombre or user.email} abrió el ticket «{ticket.subject}».",
        {
            "ticket_id": ticket.id,
            "user_id": user.id,
            "user_email": user.email,
            "subject": ticket.subject,
            "region_id": region_id,
        },
    )
    _emit_support("ticket:nuevo", payload, region_id)


def notificar_nueva_disputa(dispute, contract, solicitante=None) -> None:
    region_id = solicitante.region_id if solicitante is not None else None
    payload = {
        "id": dispute.id,
        "contract_id": dispute.contract_id,
        "reason": dispute.reason,
        "status": dispute.status,
        "region_id": region_id,
        "created_at": dispute.created_at.isoformat() if dispute.created_at else None,
    }
    _notificar_staff(
        region_id,
        "dispute_nueva",
        "Nueva disputa abierta",
        f"Se abrió una disputa en el contrato #{dispute.contract_id}: {dispute.reason}",
        {
            "dispute_id": dispute.id,
            "contract_id": dispute.contract_id,
            "region_id": region_id,
        },
    )
    _emit_support("dispute:nueva", payload, region_id)


def emit_ticket_actualizado(ticket, region_id) -> None:
    _emit_support(
        "ticket:actualizado",
        {
            "id": ticket.id,
            "status": ticket.status,
            "priority": ticket.priority,
            "assigned_to": ticket.assigned_to,
        },
        region_id,
    )


def emit_disputa_resuelta(dispute, region_id) -> None:
    _emit_support(
        "dispute:resuelta",
        {
            "id": dispute.id,
            "status": dispute.status,
            "resolution": dispute.resolution,
        },
        region_id,
    )


def notificar_disputa_resuelta(dispute, contract, resolution) -> None:
    """Avisa a ambas partes que la disputa quedó resuelta."""
    if contract is None:
        return
    destinatarios = {contract.solicitante_id, contract.proveedor_id}
    try:
        for user_id in destinatarios:
            crear_notificacion(
                user_id,
                "dispute_resuelta",
                f"La disputa del contrato #{contract.id} fue resuelta: {resolution}",
                titulo="Disputa resuelta",
                datos={
                    "dispute_id": dispute.id,
                    "contract_id": contract.id,
                    "resolution": resolution,
                },
                respetar_preferencias=False,
                forzar_push=True,
            )
        db.session.commit()
    except Exception:  # noqa: BLE001 — la disputa ya quedó resuelta
        db.session.rollback()
        log.exception("No se pudieron notificar las partes de la disputa")
