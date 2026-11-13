"""Devuelve una disputa al estado de decision de soporte pendiente.

Sirve para volver a probar, cuantas veces haga falta, los dos caminos de
respuesta de las partes (aceptar y rechazar) sin tener que repetir todo el
flujo desde el panel.

Uso:
    docker exec chambeapp_backend_dev python scripts/reset_dispute_decision.py 22

El script:
- deja la disputa cerrada con decision pendiente;
- reactiva la oferta/contrato y desoculta la conversacion;
- limpia las respuestas anteriores;
- vuelve a publicar la tarjeta de decision en el chat de las partes;
- elimina notificaciones de respuestas previas de esa disputa.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models.chat import Conversation, Message
from app.models.contract import Contract, Dispute, EstadoContrato
from app.models.notification import Notification
from app.models.oferta import Oferta
from app.models.solicitud import Solicitud
from app.models.user import RolUsuario, User
from app.services.realtime import safe_emit

DECISION_MARK = "⟦c:decision⟧"


def _textos_condiciones(condiciones) -> list[str]:
    textos = []
    for condicion in condiciones or []:
        texto = condicion.get("texto") if isinstance(condicion, dict) else str(condicion)
        if texto:
            textos.append(str(texto))
    return textos


def _oferta(dispute: Dispute, contract: Contract | None, solicitud: Solicitud | None):
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


def _valor_monto(contract: Contract | None, oferta: Oferta | None):
    if contract is not None and contract.monto is not None:
        return contract.monto
    if oferta is None:
        return None
    if oferta.estado == "contraoferta" and oferta.contra_monto is not None:
        return oferta.contra_monto
    if oferta.monto_final is not None:
        return oferta.monto_final
    return oferta.monto


def _valor_fecha(contract: Contract | None, oferta: Oferta | None):
    if contract is not None and contract.fecha_deseada is not None:
        return contract.fecha_deseada
    if oferta is None:
        return None
    return oferta.contra_fecha_deseada or oferta.fecha_deseada


def _valor_horario(contract: Contract | None, oferta: Oferta | None):
    if contract is not None and contract.horario:
        return contract.horario
    if oferta is None:
        return None
    return oferta.contra_horario or oferta.horario


def _staff_user() -> User | None:
    staff = User.query.filter_by(email="staff.soporte07@sim.chambeapp.co").first()
    if staff is not None:
        return staff
    return User.query.filter(User.rol == RolUsuario.SOPORTE).first()


def reset_decision(dispute_id: int) -> None:
    dispute = db.session.get(Dispute, dispute_id)
    if dispute is None:
        raise SystemExit(f"No existe la disputa #{dispute_id}.")

    contract = (
        db.session.get(Contract, dispute.contract_id)
        if dispute.contract_id
        else None
    )
    solicitud = (
        db.session.get(Solicitud, dispute.solicitud_id)
        if dispute.solicitud_id
        else db.session.get(Solicitud, contract.service_id)
        if contract is not None
        else None
    )
    oferta = _oferta(dispute, contract, solicitud)
    staff = _staff_user()
    if staff is None:
        raise SystemExit("No hay un usuario de soporte para publicar la decision.")

    if contract is not None:
        solicitante_id = contract.solicitante_id
        proveedor_id = contract.proveedor_id
    elif solicitud is not None and oferta is not None:
        solicitante_id = solicitud.solicitante_id
        proveedor_id = oferta.pds_id
    else:
        raise SystemExit("La disputa no tiene una negociacion con dos partes.")

    # Reactivar la negociacion para poder aceptar/rechazar nuevamente.
    if oferta is not None:
        if oferta.estado in ("aceptada", "cancelada", "rechazada"):
            oferta.estado = (
                "contraoferta"
                if oferta.contra_monto is not None
                else "pendiente"
            )
        oferta.aceptada_por_solicitante = False
        oferta.aceptada_por_pds = False
        oferta.fecha_aceptacion = None

    if contract is not None and contract.estado == EstadoContrato.CANCELADO:
        contract.estado = EstadoContrato.PENDIENTE
        contract.motivo_cancelacion = None

    a, b = Conversation.normalize(solicitante_id, proveedor_id)
    conv = Conversation.query.filter_by(user_a_id=a, user_b_id=b).first()
    if conv is None:
        conv = Conversation(user_a_id=a, user_b_id=b)
        db.session.add(conv)
        db.session.flush()
    conv.oculta = False

    monto = _valor_monto(contract, oferta)
    fecha = _valor_fecha(contract, oferta)
    horario = _valor_horario(contract, oferta)
    condiciones = _textos_condiciones(
        contract.condiciones
        if contract is not None and contract.condiciones is not None
        else oferta.condiciones if oferta is not None else []
    )

    dispute.status = "cerrada"
    dispute.decision_estado = "pendiente"
    dispute.decision_solicitante = None
    dispute.decision_proveedor = None
    dispute.negociacion_cerrada = False
    dispute.chat_habilitado = False
    dispute.chat_habilitado_solicitante = False
    dispute.chat_habilitado_proveedor = False
    dispute.resolved_by = staff.id
    dispute.resolved_at = datetime.now(timezone.utc)
    dispute.resolution = "Decision de soporte propuesta a las partes."

    payload = {
        "disputeId": dispute.id,
        "estado": "pendiente",
        "solicitante": None,
        "proveedor": None,
        "negociacionCerrada": False,
        "monto": monto,
        "fecha": fecha.isoformat() if fecha else None,
        "horario": horario,
        "condiciones": condiciones,
        "contratoId": contract.id if contract is not None else None,
        "contratoEstado": (
            contract.estado.value if contract is not None else None
        ),
    }
    contenido = DECISION_MARK + json.dumps(payload, ensure_ascii=False)

    decision_msg = (
        db.session.get(Message, dispute.decision_message_id)
        if dispute.decision_message_id
        else None
    )
    if decision_msg is None:
        decision_msg = Message(
            conversation_id=conv.id,
            sender_id=staff.id,
            contenido=contenido,
            leido=False,
            es_soporte=True,
        )
        db.session.add(decision_msg)
        db.session.flush()
        dispute.decision_message_id = decision_msg.id
    else:
        decision_msg.conversation_id = conv.id
        decision_msg.sender_id = staff.id
        decision_msg.contenido = contenido
        decision_msg.es_soporte = True

    # Notificaciones de respuestas anteriores: se limpian para no confundir
    # la nueva prueba.
    for notif in Notification.query.filter(
        Notification.tipo.in_(("dispute_decision", "dispute_rechazada"))
    ).all():
        datos = notif.datos or {}
        if str(datos.get("dispute_id")) == str(dispute.id):
            db.session.delete(notif)

    db.session.commit()

    event = {
        "id": dispute.id,
        "estado": "pendiente",
        "solicitante": None,
        "proveedor": None,
        "negociacionCerrada": False,
        "contratoId": contract.id if contract is not None else None,
    }
    for user_id in {solicitante_id, proveedor_id}:
        safe_emit("dispute:decision", event, room=f"user:{user_id}")
        safe_emit(
            "dispute:chat",
            {"id": dispute.id, "chat_habilitado": False},
            room=f"user:{user_id}",
        )
        safe_emit(
            "contrato:actualizado" if contract is not None else "oferta:actualizada",
            {"id": contract.id if contract is not None else oferta.id},
            room=f"user:{user_id}",
        )

    print(
        f"Disputa #{dispute.id} lista para probar aceptar/rechazar.\n"
        f"  Solicitante: {solicitante_id}\n"
        f"  Proveedor:   {proveedor_id}\n"
        f"  Conversacion: {conv.id}\n"
        f"  Mensaje decision: {decision_msg.id}\n"
        f"  Monto: {monto} | Fecha: {payload['fecha']} | Horario: {horario}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reactiva una disputa para probar aceptar/rechazar la decision."
    )
    parser.add_argument("dispute_id", nargs="?", type=int, default=22)
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        reset_decision(args.dispute_id)


if __name__ == "__main__":
    main()
