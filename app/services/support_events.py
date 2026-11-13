"""Eventos en tiempo real de soporte: tickets y disputas.

Además de emitir a las salas de soporte, crea notificaciones persistentes
para el staff (campana del panel) usando el mismo helper que KYC.
"""

import logging

from sqlalchemy import or_

from app.controllers.notifications import crear_notificacion
from app.extensions import db
from app.models.oferta import Oferta
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
        "category": ticket.category,
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


def _dispute_user_ids(dispute, contract, solicitud) -> set[int]:
    if contract is not None:
        return {contract.solicitante_id, contract.proveedor_id}
    if solicitud is None:
        return set()
    ids = {solicitud.solicitante_id}
    oferta = (
        db.session.get(Oferta, dispute.oferta_id)
        if dispute.oferta_id
        else Oferta.query.filter_by(solicitud_id=solicitud.id)
        .order_by(Oferta.created_at.desc())
        .first()
    )
    if oferta is not None:
        ids.add(oferta.pds_id)
    return ids


def emit_dispute_chat(dispute, contract=None, solicitud=None) -> None:
    """Avisa a las partes que el chat de la disputa se bloqueó/habilitó."""
    payload = {
        "id": dispute.id,
        "chat_habilitado": bool(dispute.chat_habilitado),
    }
    for user_id in _dispute_user_ids(dispute, contract, solicitud):
        safe_emit("dispute:chat", payload, room=f"user:{user_id}")


def notificar_nueva_disputa(dispute, contract, solicitante=None, solicitud=None) -> None:
    region_id = solicitante.region_id if solicitante is not None else None
    referencia = (
        f"el contrato #{contract.id}"
        if contract is not None
        else f"la solicitud #{solicitud.id}" if solicitud is not None else "la negociación"
    )
    payload = {
        "id": dispute.id,
        "contract_id": dispute.contract_id,
        "solicitud_id": dispute.solicitud_id,
        "oferta_id": dispute.oferta_id,
        "reason": dispute.reason,
        "status": dispute.status,
        "chat_habilitado": bool(dispute.chat_habilitado),
        "region_id": region_id,
        "created_at": dispute.created_at.isoformat() if dispute.created_at else None,
    }
    _notificar_staff(
        region_id,
        "dispute_nueva",
        "Nueva disputa abierta · chat bloqueado",
        (
            f"Se abrió una disputa en {referencia}: {dispute.reason}. "
            "El chat entre las partes quedó bloqueado; habilítalo desde el "
            "panel de soporte."
        ),
        {
            "dispute_id": dispute.id,
            "contract_id": dispute.contract_id,
            "solicitud_id": dispute.solicitud_id,
            "region_id": region_id,
            "chat_habilitado": False,
        },
    )
    _emit_support("dispute:nueva", payload, region_id)
    emit_dispute_chat(dispute, contract, solicitud)


def emit_ticket_actualizado(ticket, region_id) -> None:
    payload = {
        "id": ticket.id,
        "subject": ticket.subject,
        "category": ticket.category,
        "status": ticket.status,
        "priority": ticket.priority,
        "assigned_to": ticket.assigned_to,
    }
    _emit_support("ticket:actualizado", payload, region_id)
    # El dueño del ticket también ve el cambio (lista "Mis tickets").
    safe_emit("ticket:actualizado", payload, room=f"user:{ticket.user_id}")


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


def notificar_decision_rechazada(
    dispute, contract=None, solicitud=None, rejector="Una de las partes"
) -> None:
    """Avisa al staff que una parte rechazó la decisión y se cerró la negociación."""
    solicitante = None
    if contract is not None:
        solicitante = db.session.get(User, contract.solicitante_id)
        referencia = f"contrato #{contract.id}"
    elif solicitud is not None:
        solicitante = db.session.get(User, solicitud.solicitante_id)
        referencia = f"solicitud #{solicitud.id}"
    else:
        referencia = "la disputa"
    region_id = solicitante.region_id if solicitante is not None else None
    _notificar_staff(
        region_id,
        "dispute_rechazada",
        "Decisión de disputa rechazada",
        (
            f"{rejector} rechazó la decisión de soporte en {referencia}. "
            "La negociación se cerró y el chat quedó oculto para las partes."
        ),
        {
            "dispute_id": dispute.id,
            "contract_id": dispute.contract_id,
            "solicitud_id": dispute.solicitud_id,
            "region_id": region_id,
        },
    )
    _emit_support(
        "dispute:decision",
        {
            "id": dispute.id,
            "estado": dispute.decision_estado,
            "negociacionCerrada": bool(dispute.negociacion_cerrada),
        },
        region_id,
    )


def notificar_chat_disputa_habilitado(
    dispute, user_ids, contract=None, solicitud=None
) -> None:
    """Avisa a las partes a las que soporte les habilitó el chat."""
    destinatarios = {int(user_id) for user_id in user_ids}
    if not destinatarios:
        return
    referencia = (
        f"del contrato #{contract.id}"
        if contract is not None
        else f"de la solicitud #{solicitud.id}"
        if solicitud is not None
        else "de la disputa"
    )
    datos = {
        "dispute_id": dispute.id,
        "contract_id": dispute.contract_id,
        "solicitud_id": dispute.solicitud_id,
        "chat_habilitado": True,
    }
    try:
        for user_id in destinatarios:
            crear_notificacion(
                user_id,
                "dispute_chat_habilitado",
                (
                    f"Soporte habilitó el chat {referencia}. "
                    "Ya puedes continuar la conversación."
                ),
                titulo="Chat de la disputa habilitado",
                datos=datos,
                respetar_preferencias=False,
                forzar_push=True,
            )
        db.session.commit()
    except Exception:  # noqa: BLE001 — el cambio de chat ya quedó guardado
        db.session.rollback()
        log.exception("No se pudieron notificar los chats habilitados")


def notificar_disputa_resuelta(dispute, contract, resolution, solicitud=None) -> None:
    """Avisa a ambas partes que la disputa quedó resuelta."""
    if contract is None and solicitud is None:
        return
    if contract is not None:
        destinatarios = {contract.solicitante_id, contract.proveedor_id}
        referencia = f"del contrato #{contract.id}"
        datos = {"contract_id": contract.id}
    else:
        destinatarios = {solicitud.solicitante_id}
        from app.models.oferta import Oferta

        oferta = (
            db.session.get(Oferta, dispute.oferta_id)
            if dispute.oferta_id
            else Oferta.query.filter_by(solicitud_id=solicitud.id)
            .order_by(Oferta.created_at.desc())
            .first()
        )
        if oferta is not None:
            destinatarios.add(oferta.pds_id)
        referencia = f"de la solicitud #{solicitud.id}"
        datos = {"solicitud_id": solicitud.id}
    try:
        for user_id in destinatarios:
            crear_notificacion(
                user_id,
                "dispute_resuelta",
                f"La disputa {referencia} fue resuelta: {resolution}",
                titulo="Disputa resuelta",
                datos={
                    "dispute_id": dispute.id,
                    **datos,
                    "resolution": resolution,
                },
                respetar_preferencias=False,
                forzar_push=True,
            )
        db.session.commit()
    except Exception:  # noqa: BLE001 — la disputa ya quedó resuelta
        db.session.rollback()
        log.exception("No se pudieron notificar las partes de la disputa")
