"""Disputes blueprint: creación y gestión de disputas por usuarios (P1)."""

import json
from datetime import datetime, timezone

from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import or_

from app.extensions import db
from app.controllers.notifications import crear_notificacion
from app.models.chat import Conversation, Message
from app.models.contract import Contract, Dispute, EstadoContrato
from app.models.oferta import Oferta
from app.models.solicitud import Solicitud
from app.models.user import User
from app.services.realtime import safe_emit
from app.services.support_events import (
    notificar_decision_rechazada,
    notificar_nueva_disputa,
)
from app.schemas.contracts import (
    DisputeCreateSchema,
    DisputeDecisionSchema,
    DisputeSchema,
)

blp = Blueprint("disputes", __name__, description="Disputas de contrato (P1)")


@blp.route("/contracts/<int:contract_id>/disputes")
class DisputeList(MethodView):
    @jwt_required()
    @blp.arguments(DisputeCreateSchema)
    @blp.response(201, DisputeSchema)
    def post(self, data, contract_id):
        """Crea una disputa para un contrato. Solo participantes pueden crear."""
        user_id = int(get_jwt_identity())
        contract = db.get_or_404(Contract, contract_id)
        
        if user_id not in (contract.solicitante_id, contract.proveedor_id):
            abort(403, message="No participas en este contrato.")
        
        # No se pueden crear disputas en contratos finalizados o cancelados
        if contract.estado in (EstadoContrato.COMPLETADO, EstadoContrato.CANCELADO):
            abort(400, message="No se pueden crear disputas en contratos finalizados.")
        
        # Verificar que no exista ya una disputa abierta
        existing = Dispute.query.filter_by(
            contract_id=contract_id,
            status="abierta",
        ).first()
        if existing:
            abort(400, message="Ya existe una disputa abierta para este contrato.")
        
        dispute = Dispute(
            contract_id=contract_id,
            solicitud_id=contract.service_id,
            oferta_id=contract.oferta_id,
            reason=data["reason"],
            status="abierta",
            chat_habilitado=False,
            chat_habilitado_solicitante=False,
            chat_habilitado_proveedor=False,
        )
        db.session.add(dispute)
        db.session.commit()

        solicitante = db.session.get(User, contract.solicitante_id)
        notificar_nueva_disputa(dispute, contract, solicitante)

        return dispute

    @jwt_required()
    @blp.response(200, DisputeSchema(many=True))
    def get(self, contract_id):
        """Lista disputas de un contrato. Solo participantes pueden ver."""
        user_id = int(get_jwt_identity())
        contract = db.get_or_404(Contract, contract_id)
        
        if user_id not in (contract.solicitante_id, contract.proveedor_id):
            abort(403, message="No participas en este contrato.")
        
        return Dispute.query.filter_by(contract_id=contract_id).order_by(
            Dispute.created_at.desc()
        ).all()


@blp.route("/solicitudes/<int:solicitud_id>/disputes")
class SolicitudDisputeList(MethodView):
    @jwt_required()
    @blp.arguments(DisputeCreateSchema)
    @blp.response(201, DisputeSchema)
    def post(self, data, solicitud_id):
        """Abre una disputa durante la negociación, antes de crear contrato.

        La disputa queda ligada a la solicitud y a la oferta en negociación.
        Si ya existe un contrato para esa negociación se usa el contrato.
        """
        user_id = int(get_jwt_identity())
        solicitud = db.get_or_404(Solicitud, solicitud_id)

        oferta = None
        oferta_id = data.get("oferta_id")
        if oferta_id is not None:
            oferta = db.session.get(Oferta, oferta_id)
            if oferta is None or oferta.solicitud_id != solicitud_id:
                abort(400, message="La oferta no pertenece a esta solicitud.")
            if user_id not in (solicitud.solicitante_id, oferta.pds_id):
                abort(403, message="No participas en esta negociación.")
        elif user_id == solicitud.solicitante_id:
            oferta = (
                Oferta.query.filter_by(solicitud_id=solicitud_id)
                .order_by(Oferta.created_at.desc())
                .first()
            )
        else:
            oferta = (
                Oferta.query.filter_by(solicitud_id=solicitud_id, pds_id=user_id)
                .order_by(Oferta.created_at.desc())
                .first()
            )
            if oferta is None:
                abort(403, message="No participas en esta negociación.")

        if user_id != solicitud.solicitante_id and (
            oferta is None or oferta.pds_id != user_id
        ):
            abort(403, message="No participas en esta negociación.")

        contract = None
        if oferta is not None:
            contract = (
                Contract.query.filter_by(
                    service_id=solicitud_id,
                    solicitante_id=solicitud.solicitante_id,
                    proveedor_id=oferta.pds_id,
                )
                .order_by(Contract.id.desc())
                .first()
            )

        if contract is not None:
            if contract.estado in (
                EstadoContrato.COMPLETADO,
                EstadoContrato.CANCELADO,
            ):
                abort(
                    400,
                    message="No se pueden crear disputas en contratos finalizados.",
                )
            existing = Dispute.query.filter_by(
                contract_id=contract.id, status="abierta"
            ).first()
        else:
            existing = Dispute.query.filter_by(
                solicitud_id=solicitud_id, status="abierta"
            ).first()

        if existing is not None:
            abort(
                400,
                message="Ya existe una disputa abierta para esta negociación.",
            )

        dispute = Dispute(
            contract_id=contract.id if contract is not None else None,
            solicitud_id=solicitud_id,
            oferta_id=oferta.id if oferta is not None else oferta_id,
            reason=data["reason"],
            status="abierta",
            chat_habilitado=False,
            chat_habilitado_solicitante=False,
            chat_habilitado_proveedor=False,
        )
        db.session.add(dispute)
        db.session.commit()

        solicitante = db.session.get(User, solicitud.solicitante_id)
        notificar_nueva_disputa(dispute, contract, solicitante, solicitud)

        return dispute


@blp.route("/my-disputes")
class MyDisputes(MethodView):
    @jwt_required()
    @blp.response(200, DisputeSchema(many=True))
    def get(self):
        """Lista disputas donde el usuario es participante."""
        user_id = int(get_jwt_identity())
        
        contract_ids = [
            c.id
            for c in Contract.query.filter(
                (Contract.solicitante_id == user_id)
                | (Contract.proveedor_id == user_id)
            ).all()
        ]
        solicitud_ids = set(
            db.session.scalars(
                db.select(Solicitud.id).where(
                    Solicitud.solicitante_id == user_id
                )
            ).all()
        )
        solicitud_ids.update(
            db.session.scalars(
                db.select(Oferta.solicitud_id).where(Oferta.pds_id == user_id)
            ).all()
        )

        conditions = []
        if contract_ids:
            conditions.append(Dispute.contract_id.in_(contract_ids))
        if solicitud_ids:
            conditions.append(Dispute.solicitud_id.in_(solicitud_ids))
        if not conditions:
            return []

        return (
            Dispute.query.filter(or_(*conditions))
            .order_by(Dispute.created_at.desc())
            .all()
        )


@blp.route("/disputes/<int:dispute_id>/decision")
class DisputeDecision(MethodView):
    @jwt_required()
    @blp.arguments(DisputeDecisionSchema)
    @blp.response(200)
    def post(self, data, dispute_id):
        """Acepta o rechaza la decisión propuesta por soporte."""
        user_id = int(get_jwt_identity())
        dispute = db.get_or_404(Dispute, dispute_id)
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

        oferta = None
        if contract is not None and contract.oferta_id:
            oferta = db.session.get(Oferta, contract.oferta_id)
        if oferta is None and dispute.oferta_id:
            oferta = db.session.get(Oferta, dispute.oferta_id)
        if oferta is None and solicitud is not None:
            oferta = (
                Oferta.query.filter_by(solicitud_id=solicitud.id)
                .order_by(Oferta.created_at.desc())
                .first()
            )

        if contract is not None:
            solicitante_id = contract.solicitante_id
            proveedor_id = contract.proveedor_id
        elif solicitud is not None and oferta is not None:
            solicitante_id = solicitud.solicitante_id
            proveedor_id = oferta.pds_id
        else:
            solicitante_id = proveedor_id = None

        if user_id not in (solicitante_id, proveedor_id):
            abort(403, message="No participas en esta disputa.")
        if dispute.decision_estado != "pendiente":
            abort(400, message="La decisión de soporte ya no está pendiente.")

        rol = "solicitante" if user_id == solicitante_id else "proveedor"
        if getattr(dispute, f"decision_{rol}") is not None:
            abort(400, message="Ya respondiste a esta decisión.")

        respuesta = "aceptada" if data["accion"] == "aceptar" else "rechazada"
        setattr(dispute, f"decision_{rol}", respuesta)

        if respuesta == "rechazada":
            dispute.decision_estado = "rechazada"
            dispute.negociacion_cerrada = True
            if oferta is not None:
                oferta.estado = "cancelada"
            if contract is not None:
                contract.estado = EstadoContrato.CANCELADO
                contract.motivo_cancelacion = (
                    "Negociación cerrada por rechazo de la decisión de soporte."
                )
            if solicitante_id is not None and proveedor_id is not None:
                a, b = Conversation.normalize(solicitante_id, proveedor_id)
                conv = Conversation.query.filter_by(
                    user_a_id=a, user_b_id=b
                ).first()
                if conv is not None:
                    conv.oculta = True
        elif (
            dispute.decision_solicitante == "aceptada"
            and dispute.decision_proveedor == "aceptada"
        ):
            dispute.decision_estado = "aceptada"
            if oferta is not None and solicitud is not None:
                oferta.estado = "aceptada"
                oferta.aceptada_por_solicitante = True
                oferta.aceptada_por_pds = True
                oferta.fecha_aceptacion = datetime.now(timezone.utc)
                monto_final = (
                    oferta.monto_final
                    if oferta.monto_final is not None
                    else oferta.contra_monto
                    if oferta.contra_monto is not None
                    else oferta.monto
                )
                oferta.monto_final = monto_final
                if contract is None:
                    contract = Contract(
                        service_id=solicitud.id,
                        proveedor_id=oferta.pds_id,
                        solicitante_id=solicitud.solicitante_id,
                        estado=EstadoContrato.PENDIENTE,
                    )
                    db.session.add(contract)
                    db.session.flush()
                contract.oferta_id = oferta.id
                contract.monto = monto_final
                contract.condiciones = list(oferta.condiciones or [])
                contract.fecha_deseada = (
                    oferta.contra_fecha_deseada or oferta.fecha_deseada
                )
                contract.horario = oferta.contra_horario or oferta.horario
                otras = Oferta.query.filter(
                    Oferta.solicitud_id == solicitud.id,
                    Oferta.id != oferta.id,
                    Oferta.estado.in_(
                        ["pendiente", "contraoferta"]
                    ),
                ).all()
                for otra in otras:
                    otra.estado = "rechazada"

        decision_msg = (
            db.session.get(Message, dispute.decision_message_id)
            if dispute.decision_message_id
            else None
        )
        if decision_msg is not None and decision_msg.contenido.startswith("⟦c:decision⟧"):
            try:
                payload = json.loads(decision_msg.contenido.split("⟧", 1)[1])
                payload.update(
                    {
                        "estado": dispute.decision_estado,
                        "solicitante": dispute.decision_solicitante,
                        "proveedor": dispute.decision_proveedor,
                        "negociacionCerrada": bool(dispute.negociacion_cerrada),
                        "contratoId": contract.id if contract is not None else None,
                        "contratoEstado": (
                            contract.estado.value
                            if contract is not None
                            else None
                        ),
                    }
                )
                decision_msg.contenido = "⟦c:decision⟧" + json.dumps(
                    payload, ensure_ascii=False
                )
            except (ValueError, TypeError):
                pass

        db.session.commit()

        rejector = db.session.get(User, user_id)
        rejector_nombre = (
            (rejector.nombre or rejector.email)
            if rejector is not None
            else "Una de las partes"
        )
        if respuesta == "rechazada":
            notificar_decision_rechazada(
                dispute, contract, solicitud, rejector=rejector_nombre
            )
            aviso = f"{rejector_nombre} rechazó la decisión. La negociación se cerró."
        elif dispute.decision_estado == "aceptada":
            aviso = (
                "Ambas partes aceptaron la decisión de soporte. "
                "El contrato quedó listo para firmar."
            )
        else:
            aviso = (
                f"{rejector_nombre} aceptó la decisión de soporte. "
                "Falta la respuesta de la otra parte."
            )

        for participant_id in {solicitante_id, proveedor_id}:
            if participant_id:
                crear_notificacion(
                    participant_id,
                    "dispute_decision",
                    aviso,
                    titulo="Respuesta a la decisión de soporte",
                    datos={
                        "dispute_id": dispute.id,
                        "decision_estado": dispute.decision_estado,
                        "negociacion_cerrada": bool(dispute.negociacion_cerrada),
                        "contrato_id": contract.id if contract is not None else None,
                    },
                    respetar_preferencias=False,
                    forzar_push=True,
                )
        db.session.commit()

        event = {
            "id": dispute.id,
            "estado": dispute.decision_estado,
            "solicitante": dispute.decision_solicitante,
            "proveedor": dispute.decision_proveedor,
            "negociacionCerrada": bool(dispute.negociacion_cerrada),
            "contratoId": contract.id if contract is not None else None,
        }
        for participant_id in {solicitante_id, proveedor_id}:
            if participant_id:
                safe_emit(
                    "dispute:decision", event, room=f"user:{participant_id}"
                )
                if contract is not None:
                    safe_emit(
                        "contrato:actualizado",
                        {"id": contract.id},
                        room=f"user:{participant_id}",
                    )

        return {
            "id": dispute.id,
            **event,
        }
