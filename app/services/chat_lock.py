"""Bloqueo del chat entre las partes mientras una disputa está abierta.

Soporte puede habilitar el chat para el solicitante, para el proveedor o
para ambos. El bloqueo se evalúa por usuario: una parte habilitada puede
escribir aunque la otra siga bloqueada.
"""

from app.extensions import db
from app.models.contract import Contract, Dispute
from app.models.oferta import Oferta
from app.models.solicitud import Solicitud


def _pds_id(dispute, solicitud) -> int | None:
    if solicitud is None:
        return None
    oferta = (
        db.session.get(Oferta, dispute.oferta_id)
        if dispute.oferta_id
        else Oferta.query.filter_by(solicitud_id=solicitud.id)
        .order_by(Oferta.created_at.desc())
        .first()
    )
    return oferta.pds_id if oferta is not None else None


def is_dispute_chat_locked_for_user(user_id: int, other_user_id: int) -> bool:
    """True si la disputa abierta bloquea el chat para `user_id`.

    Se consideran las disputas abiertas de cualquiera de las negociaciones
    que comparten ambos usuarios.
    """
    user_id = int(user_id)
    other_user_id = int(other_user_id)
    disputes = Dispute.query.filter_by(status="abierta").all()
    for dispute in disputes:
        if dispute.contract_id:
            contract = db.session.get(Contract, dispute.contract_id)
            if contract is None:
                continue
            if (
                contract.solicitante_id == user_id
                and contract.proveedor_id == other_user_id
            ):
                if not dispute.chat_habilitado_solicitante:
                    return True
            elif (
                contract.proveedor_id == user_id
                and contract.solicitante_id == other_user_id
            ):
                if not dispute.chat_habilitado_proveedor:
                    return True
            continue

        if dispute.solicitud_id:
            solicitud = db.session.get(Solicitud, dispute.solicitud_id)
            if solicitud is None:
                continue
            pds_id = _pds_id(dispute, solicitud)
            if (
                solicitud.solicitante_id == user_id
                and pds_id == other_user_id
            ):
                if not dispute.chat_habilitado_solicitante:
                    return True
            elif (
                pds_id == user_id
                and solicitud.solicitante_id == other_user_id
            ):
                if not dispute.chat_habilitado_proveedor:
                    return True
    return False


def is_conversation_chat_locked(conv, user_id: int) -> bool:
    other_id = conv.user_b_id if conv.user_a_id == int(user_id) else conv.user_a_id
    return is_dispute_chat_locked_for_user(int(user_id), other_id)
