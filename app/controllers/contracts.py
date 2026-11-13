"""Contracts blueprint: gestión contractual y órdenes de trabajo (RF-07)."""

from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from datetime import datetime, timezone

from app.extensions import db
from app.services.realtime import safe_emit
from app.models.user import User
from app.models.solicitud import Solicitud, EstadoSolicitud
from app.models.contract import Contract, EstadoContrato
from app.schemas.contracts import ContractCreateSchema, ContractEstadoSchema, ContractSchema
from app.controllers.notifications import (
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

        # Feedback loop: el contrato confirma la recomendación aceptada.
        try:
            from app.models.recommendation_log import RecommendationLog
            RecommendationLog.mark_accepted(solicitud.id, proveedor.id)
        except Exception:
            db.session.rollback()
        return contract


@blp.route("/mine")
class MyContracts(MethodView):
    @jwt_required()
    @blp.response(200)
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
            return ContractSchema(many=True).dump(result)
        # `paginate_query` devuelve un dict cuando hay page/per_page. Hay que
        # serializar los items AQUÍ: si se devuelve el dict tal cual,
        # flask-smorest aplica `many=True` al diccionario y marshmallow
        # serializa sus claves → [{}, {}, ...] (bug que rompía la lista).
        result["items"] = ContractSchema(many=True).dump(result["items"])
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
            # Firma bilateral y paralela: cada parte firma por su cuenta, sin
            # esperar a la contraparte. El contrato se activa cuando ambos
            # han firmado.
            if contract.estado != EstadoContrato.PENDIENTE:
                abort(400, message="Solo se firma un contrato desde 'pendiente'.")
            if contract.firma_solicitante and contract.firma_proveedor:
                abort(400, message="El contrato ya fue firmado por ambas partes.")

            es_solicitante = user_id == contract.solicitante_id
            firma = data.get("firma") or {}
            ahora = datetime.now(timezone.utc)

            if es_solicitante and contract.firma_solicitante:
                abort(400, message="Ya firmaste este contrato.")
            if not es_solicitante and contract.firma_proveedor:
                abort(400, message="Ya firmaste este contrato.")

            # Cobro en monedas ANTES de registrar la firma. La plataforma
            # no intermedia el pago del trabajo; solo cobra la tarifa de uso.
            from app.services.cobros import calcular_monedas_contrato, cobrar_monedas

            solicitud = db.session.get(Solicitud, contract.service_id)
            monto_base = (
                contract.monto
                if contract.monto is not None
                else (solicitud.presupuesto if solicitud is not None else 0)
            )
            monedas = calcular_monedas_contrato(monto_base)
            referencia = f"COBRO-FIRMA-{contract.id}-{user_id}"
            try:
                cobrar_monedas(
                    user_id,
                    monedas,
                    referencia,
                    f"Cobro por firma del contrato #{contract.id}",
                )
            except ValueError:
                abort(
                    400,
                    message=(
                        f"MONEDAS_INSUFICIENTES:{monedas}:Necesitas {monedas} "
                        "monedas para firmar este contrato. Recarga tu "
                        "billetera y vuelve a intentarlo."
                    ),
                )

            if es_solicitante:
                contract.firma_solicitante = True
                contract.firmado_solicitante_en = ahora
                contract.datos_firma_solicitante = firma
                contract.cobro_solicitante_monedas = monedas
                contract.cobro_solicitante_ref = referencia
                contract.cobro_solicitante_en = ahora
                contraparte = contract.proveedor_id
                rol = "solicitante"
            else:
                contract.firma_proveedor = True
                contract.firmado_proveedor_en = ahora
                contract.datos_firma_proveedor = firma
                contract.cobro_proveedor_monedas = monedas
                contract.cobro_proveedor_ref = referencia
                contract.cobro_proveedor_en = ahora
                contraparte = contract.solicitante_id
                rol = "proveedor"

            if contract.firma_solicitante and contract.firma_proveedor:
                # Contrato firmado por ambas partes: se activa el trabajo.
                contract.estado = EstadoContrato.EN_PROGRESO
                contract.inicio_en = ahora

                # Firma completa del contrato: la solicitud pasa a "en curso"
                # (ASIGNADA) y se genera la chamba del módulo de gestión (hito 1).
                solicitud = db.session.get(Solicitud, contract.service_id)
                if solicitud is not None:
                    solicitud.estado = EstadoSolicitud.ASIGNADA
                    from app.models.chamba import Chamba, EstadoChamba

                    if Chamba.query.filter_by(contract_id=contract.id).first() is None:
                        chamba = Chamba(
                            contract_id=contract.id,
                            estado=EstadoChamba.PROGRAMADA,
                            fecha_activacion=datetime.now(timezone.utc),
                            evidencia_entrada=[],
                            evidencia_salida=[],
                            adendas=[],
                            novedades=[],
                            habilidades_validadas=[],
                        )
                        db.session.add(chamba)

                crear_notificacion(
                    contract.solicitante_id,
                    "contrato_aceptado",
                    "Ambas partes firmaron el contrato. La solicitud está en curso: gestiona la chamba.",
                )
                crear_notificacion(
                    contract.proveedor_id,
                    "contrato_aceptado",
                    "Ambas partes firmaron el contrato. La solicitud está en curso: gestiona la chamba.",
                )
            else:
                # Solo una parte firmó: se espera a la contraparte.
                crear_notificacion(
                    contraparte,
                    "contrato_firma_pendiente",
                    (
                        "El solicitante firmó el contrato. Falta tu firma para activarlo."
                        if rol == "solicitante"
                        else "El prestador firmó el contrato. Falta tu firma para activarlo."
                    ),
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

            # --- Pago directo entre las partes: la plataforma NO intermedia ---
            # No hay comisión ni acreditación del monto del trabajo. Solo se
            # otorga la recompensa de fidelidad por completar el servicio.
            try:
                from app.services.wallet import dar_monedas_ganadas

                dar_monedas_ganadas(contract.proveedor_id, 10)
            except Exception:
                pass

            crear_notificacion(
                contract.proveedor_id,
                "contrato_confirmado",
                "El solicitante confirmó que el trabajo está completado.",
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

            # Reembolso de monedas si el contrato nunca llegó a activarse
            # (no se completaron ambas firmas).
            if contract.estado == EstadoContrato.PENDIENTE and not contract.cobros_reembolsados:
                from app.services.wallet import reembolsar_monedas

                for uid, monto, ref in (
                    (
                        contract.solicitante_id,
                        contract.cobro_solicitante_monedas,
                        contract.cobro_solicitante_ref,
                    ),
                    (
                        contract.proveedor_id,
                        contract.cobro_proveedor_monedas,
                        contract.cobro_proveedor_ref,
                    ),
                ):
                    if monto and ref:
                        reembolsar_monedas(
                            uid,
                            int(monto),
                            f"REEMBOLSO-{ref}",
                            f"Reembolso por cancelación del contrato #{contract.id}",
                        )
                contract.cobros_reembolsados = True

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
        payload = ContractSchema().dump(contract)
        safe_emit("contrato:actualizado", payload, room=f"user:{contract.solicitante_id}")
        safe_emit("contrato:actualizado", payload, room=f"user:{contract.proveedor_id}")

        return contract


@blp.route("/<int:contract_id>/cobro")
class ContractCobro(MethodView):
    @jwt_required()
    @blp.doc(summary="Estimación del cobro en monedas al firmar")
    def get(self, contract_id):
        """Monedas que pagaría este usuario al firmar el contrato."""
        from app.services.cobros import calcular_monedas_contrato, get_config_publica

        user_id = int(get_jwt_identity())
        contract = db.get_or_404(Contract, contract_id)
        if user_id not in (contract.solicitante_id, contract.proveedor_id):
            abort(403, message="No participas en este contrato.")

        solicitud = db.session.get(Solicitud, contract.service_id)
        monto = (
            contract.monto
            if contract.monto is not None
            else (solicitud.presupuesto if solicitud is not None else 0)
        )
        config = get_config_publica()
        return {
            "monto": monto or 0,
            "monedas": calcular_monedas_contrato(monto),
            "pct_contrato": config["pct_contrato"],
            "precio_moneda_cop": config["precio_moneda_cop"],
        }
