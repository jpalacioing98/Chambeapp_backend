"""Eventos en tiempo real del KYC para el panel administrativo.

Cuando un PDS/solicitante/merchant envía un documento:
  · se emite `kyc:documento_nuevo` a las salas staff de su región;
  · se crean notificaciones persistentes para el staff que puede revisarlo,
    de modo que la campana del panel admin se actualice al instante.
"""

import logging

from sqlalchemy import or_

from app.controllers.notifications import crear_notificacion
from app.extensions import db
from app.models.user import RolUsuario, User
from app.services.realtime import safe_emit
from app.services.staff_rooms import (
    KYC_STAFF_ROLES,
    staff_kyc_rooms_for_region,
)

log = logging.getLogger(__name__)


def _staff_recipients(region_id):
    """Staff activo que puede revisar documentos de esa región."""
    query = User.query.filter(
        User.activo.is_(True),
        User.status == "active",
        User.rol.in_(KYC_STAFF_ROLES),
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


def notificar_nuevo_documento_kyc(du, user, requerido=None) -> None:
    """Notifica al staff el nuevo documento KYC (socket + persistencia)."""
    nombre = (
        requerido.nombre
        if requerido is not None
        else du.documento_clave
    )
    payload = {
        "id": du.id,
        "documento_clave": du.documento_clave,
        "nombre": nombre,
        "estado": du.estado,
        "fecha_envio": du.fecha_envio.isoformat() if du.fecha_envio else None,
        "region_id": user.region_id,
        "usuario": {
            "id": user.id,
            "nombre": user.nombre,
            "email": user.email,
            "rol": user.rol.value,
        },
    }

    recipients = _staff_recipients(user.region_id)
    try:
        mensaje = (
            f"{user.nombre or user.email} envió «{nombre}» para revisión."
        )
        datos = {
            "documento_id": du.id,
            "documento_clave": du.documento_clave,
            "nombre": nombre,
            "user_id": user.id,
            "user_email": user.email,
            "region_id": user.region_id,
        }
        for recipient in recipients:
            crear_notificacion(
                recipient.id,
                "kyc_documento_nuevo",
                mensaje,
                titulo="Nuevo documento KYC",
                datos=datos,
                respetar_preferencias=False,
                forzar_push=True,
            )
        db.session.commit()
    except Exception:  # noqa: BLE001 — el documento ya quedó guardado
        db.session.rollback()
        log.exception("No se pudieron crear las notificaciones KYC del staff")

    for room in staff_kyc_rooms_for_region(user.region_id):
        safe_emit("kyc:documento_nuevo", payload, room=room)
