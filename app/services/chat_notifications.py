"""Notificaciones y push de mensajes enviados por soporte.

Cuando un miembro del equipo de soporte escribe en un chat, el usuario
destinatario recibe una notificación persistente y un Web Push. El push
abre directamente la conversación en el módulo de Mensajes.
"""

import logging

from app.controllers.notifications import crear_notificacion
from app.extensions import db
from app.models.user import RolUsuario, User

log = logging.getLogger(__name__)

SUPPORT_ROLES = frozenset(
    {
        RolUsuario.SOPORTE,
        RolUsuario.ADMIN,
        RolUsuario.SUPERADMIN,
    }
)

_MENSAJES_BASE = {
    RolUsuario.PDS: "/pds",
    RolUsuario.SOLICITANTE: "/solicitante",
    RolUsuario.MERCHANT: "/negocio",
}

_ATTACHMENT_PREFIX = "⟦c:adjunto⟧"


def _preview(contenido: str) -> str:
    if not contenido:
        return "Nuevo mensaje de soporte."
    if contenido.startswith(_ATTACHMENT_PREFIX):
        return "Te envió un archivo adjunto."
    texto = " ".join(contenido.split())
    return texto if len(texto) <= 140 else f"{texto[:140]}…"


def notificar_mensaje_soporte(conv, message, sender_id: int) -> None:
    """Notifica al usuario si el mensaje lo envió un miembro de soporte."""
    sender = db.session.get(User, sender_id)
    if sender is None or sender.rol not in SUPPORT_ROLES:
        return

    recipient_id = (
        conv.user_b_id if conv.user_a_id == sender_id else conv.user_a_id
    )
    recipient = db.session.get(User, recipient_id)
    if recipient is None or recipient.rol in SUPPORT_ROLES:
        return

    base = _MENSAJES_BASE.get(recipient.rol)
    push_url = (
        f"{base}/mensajes?conversacion={conv.id}"
        if base is not None
        else "/notificaciones"
    )

    try:
        crear_notificacion(
            recipient.id,
            "message",
            f"Soporte ChambeApp: {_preview(message.contenido)}",
            titulo="Mensaje de soporte",
            datos={
                "conversation_id": conv.id,
                "message_id": message.id,
                "sender_id": sender_id,
            },
            respetar_preferencias=False,
            forzar_push=True,
            push_url=push_url,
        )
        db.session.commit()
    except Exception:  # noqa: BLE001 — el mensaje ya quedó persistido
        db.session.rollback()
        log.exception("No se pudo notificar el mensaje de soporte")
