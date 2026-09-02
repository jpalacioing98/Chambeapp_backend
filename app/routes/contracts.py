"""Contracts blueprint: gestión contractual y órdenes de trabajo (RF-07)."""

from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from datetime import datetime, timezone

from app.extensions import db, socketio
from app.models.user import User
from app.models.solicitud import Solicitud, EstadoSolicitud
from app.models.contract import Contract, EstadoContrato
from app.schemas.contracts import ContractCreateSchema, ContractEstadoSchema, ContractSchema
from app.routes.notifications import (
    crear_notificacion,
    disparar_notificaciones_formalizacion,
)

blp = Blueprint("contracts", __name__, description="Contratos de trabajo (RF-07)")


@blp.route("/")
class ContractList(MethodView):
    @jwt_required()
    @blp.arguments(ContractCreateSchema)
    @blp.response(201, ContractSchema)
    def post(self, data):
        """RF-07.1: crea contrato. El JWT debe ser el dueño (solicitante) del servicio."""
        user_id = int(get_jwt_identity())

        solicitud = db.session.get(Solicitud, data["service_id"])
        if solicitud is None:
            abort(404, message="La solicitud no existe.")

        if solicitud.estado != EstadoSolicitud.PUBLICADO:
            abort(400, message="La solicitud no está publicada.")

        if solicitud.solicitante_id != user_id:
            abort(403, message="Solo el dueño de la solicitud puede crear el contrato.")

        proveedor = db.session.get(User, data["proveedor_id"])
        if proveedor is None:
            abort(404, message="El proveedor no existe.")

        contract = Contract(
            service_id=solicitud.id,
            proveedor_id=proveedor.id,
            solicitante_id=user_id,
            estado=EstadoContrato.PENDIENTE,
        )
        db.session.add(contract)
        db.session.flush()

        crear_notificacion(
            proveedor.id,
            "contrato_pendiente",
            "Tienes un contrato pendiente de un servicio que publicaste.",
        )
        db.session.commit()
        return contract


@blp.route("/mine")
class MyContracts(MethodView):
    @jwt_required()
    @blp.response(200, ContractSchema(many=True))
    def get(self):
        """RF-07: lista contratos donde el usuario es solicitante o proveedor.
        
        Supports optional page/per_page query params for pagination (P2-4).
        If no params, returns all items (backward compatible).
        """
        user_id = int(get_jwt_identity())
        query = Contract.query.filter(
            (Contract.solicitante_id == user_id) | (Contract.proveedor_id == user_id)
        )
        estado = request.args.get("estado")
        if estado:
            query = query.filter(Contract.estado == EstadoContrato(estado))
        query = query.order_by(Contract.creado_en.desc())

        from app.services.pagination import paginate_query
        page = request.args.get("page")
        per_page = request.args.get("per_page")
        result = paginate_query(query, page=page, per_page=per_page)

        if isinstance(result, list):
            return result
        return result


@blp.route("/<int:contract_id>")
class ContractDetail(MethodView):
    @jwt_required()
    @blp.response(200, ContractSchema)
    def get(self, contract_id):
        """RF-07: detalle de contrato (solo participantes)."""
        user_id = int(get_jwt_identity())
        contract = db.get_or_404(Contract, contract_id)
        if user_id not in (contract.solicitante_id, contract.proveedor_id):
            abort(403, message="No participas en este contrato.")
        return contract


@blp.route("/<int:contract_id>/estado")
class ContractEstado(MethodView):
    @jwt_required()
    @blp.arguments(ContractEstadoSchema)
    @blp.response(200, ContractSchema)
    def patch(self, data, contract_id):
        """RF-07.2/3/4: transición de estado del contrato."""
        user_id = int(get_jwt_identity())
        contract = db.get_or_404(Contract, contract_id)

        if user_id not in (contract.solicitante_id, contract.proveedor_id):
            abort(403, message="No participas en este contrato.")

        accion = data["estado"]

        if accion == "aceptar":
            if contract.estado != EstadoContrato.PENDIENTE:
                abort(400, message="Solo se acepta un contrato desde 'pendiente'.")
            # check-in: solo el pds (proveedor) ejecuta el trabajo.
            if user_id != contract.proveedor_id:
                abort(403, message="Solo el proveedor puede aceptar el contrato.")
            contract.estado = EstadoContrato.EN_PROGRESO
            contract.inicio_en = datetime.now(timezone.utc)
            crear_notificacion(
                contract.solicitante_id,
                "contrato_aceptado",
                "Tu contrato de trabajo fue aceptado por el proveedor.",
            )

        elif accion == "completar":
            if contract.estado != EstadoContrato.EN_PROGRESO:
                abort(400, message="Solo se completa un contrato desde 'en_progreso'.")
            # check-out: solo el pds (proveedor) finaliza el trabajo.
            if user_id != contract.proveedor_id:
                abort(403, message="Solo el proveedor puede completar el contrato.")
            # RF-23: Confirmación dual - el contrato queda en estado "completado_pendiente"
            # hasta que el solicitante confirme
            contract.estado = EstadoContrato.COMPLETADO_PENDIENTE
            contract.fin_en = datetime.now(timezone.utc)
            solicitud = db.session.get(Solicitud, contract.service_id)
            if solicitud is not None:
                solicitud.estado = EstadoSolicitud.COMPLETADO

            crear_notificacion(
                contract.solicitante_id,
                "contrato_completado_pendiente",
                "El proveedor marcó el contrato como completado. Por favor confirma que el trabajo está bien.",
            )
            crear_notificacion(
                contract.proveedor_id,
                "contrato_esperando_confirmacion",
                "El contrato fue marcado como completado. Esperando confirmación del solicitante.",
            )

        elif accion == "confirmar":
            # RF-23: Confirmación dual - solo el solicitante puede confirmar
            if contract.estado != EstadoContrato.COMPLETADO_PENDIENTE:
                abort(400, message="Solo se puede confirmar un contrato en estado 'completado_pendiente'.")
            if user_id != contract.solicitante_id:
                abort(403, message="Solo el solicitante puede confirmar la finalización del contrato.")
            
            contract.estado = EstadoContrato.COMPLETADO
            contract.confirmado_en = datetime.now(timezone.utc)

            # --- RF-25/26: Integrar billetera al confirmar contrato ---
            solicitud = db.session.get(Solicitud, contract.service_id)
            try:
                from app.services.wallet import get_modalidad, descontar_comision, acreditar_pago, dar_monedas_ganadas
                from app.config import COMMISSION_EXEMPT_THRESHOLD

                modalidad = get_modalidad(solicitud.id)
                monto_total = solicitud.presupuesto or 0

                if monto_total > 0:
                    # Determinar si hay comisión (Modalidad A, monto >= umbral)
                    comision = 0
                    if modalidad.tipo.value == "A_comision" and monto_total >= COMMISSION_EXEMPT_THRESHOLD:
                        comision = int(monto_total * 0.12)

                    # Descontar comisión del PDS
                    if comision > 0:
                        descontar_comision(
                            contract.proveedor_id,
                            comision,
                            f"COMISION-CONTRATO-{contract.id}",
                        )

                    # Acreditar pago neto al PDS
                    monto_neto = monto_total - comision
                    acreditar_pago(
                        contract.proveedor_id,
                        monto_neto,
                        f"PAGO-CONTRATO-{contract.id}",
                    )

                    # Otorgar monedas ganadas al completar servicio
                    dar_monedas_ganadas(contract.proveedor_id, 10)

            except Exception:
                # No romper el flujo de contrato si falla la billetera
                pass

            crear_notificacion(
                contract.proveedor_id,
                "contrato_confirmado",
                "El solicitante confirmó que el trabajo está completado. ¡Pago procesado!",
            )
            crear_notificacion(
                contract.solicitante_id,
                "contrato_confirmado",
                "Has confirmado la finalización del contrato.",
            )

            # P2-5: Badge awarding after contract completion
            try:
                from app.services.badges import check_and_award_all
                check_and_award_all(contract.proveedor_id)
            except Exception:
                pass

        elif accion == "cancelar":
            if contract.estado in (EstadoContrato.COMPLETADO, EstadoContrato.CANCELADO):
                abort(400, message="No se puede cancelar un contrato ya finalizado.")
            # cancelar: solicitante o pds (ya validado arriba que participa).
            motivo = data.get("motivo_cancelacion")
            if not motivo or not str(motivo).strip():
                abort(400, message="Se requiere un motivo de cancelación.")
            contract.estado = EstadoContrato.CANCELADO
            contract.motivo_cancelacion = motivo
            contraparte = (
                contract.solicitante_id
                if user_id == contract.proveedor_id
                else contract.proveedor_id
            )
            crear_notificacion(
                contraparte,
                "contrato_cancelado",
                f"El contrato de trabajo fue cancelado. Motivo: {motivo}",
            )

        else:
            abort(400, message="Acción de estado inválida.")

        db.session.commit()

        # RF-10: al completarse el contrato, notifica a ambas partes sobre
        # opciones de formalización laboral (idempotente, no rompe el flujo).
        disparar_notificaciones_formalizacion(contract)

        # Notificación en tiempo real (socket) a ambos participantes.
        payload = {
            "contract_id": contract.id,
            "estado": contract.estado.value,
            "inicio_en": contract.inicio_en.isoformat() if contract.inicio_en else None,
            "fin_en": contract.fin_en.isoformat() if contract.fin_en else None,
        }
        socketio.emit("contracto:actualizado", payload, room=f"user:{contract.solicitante_id}")
        socketio.emit("contracto:actualizado", payload, room=f"user:{contract.proveedor_id}")

        return contract
