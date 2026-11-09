"""Ofertas blueprint: negociación pds/solicitante (RF-04 negociación).

Endpoints (prefijo /api/v1):
  POST   /solicitudes/<sid>/ofertas   -> pds crea oferta (no dueño)
  GET    /solicitudes/<sid>/ofertas   -> dueño o pds con oferta
  GET    /mis-ofertas                 -> ofertas del pds actual
  POST   /ofertas/<oid>/responder     -> aceptar/rechazar/contraofertar
  POST   /ofertas/<oid>/condiciones   -> agrega una condición al acuerdo

La negociación es bilateral: cada parte acepta el valor vigente y el
acuerdo (con su contrato) se cierra cuando ambas aceptan.
"""

from datetime import datetime, timezone
import json

from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.extensions import db, socketio
from app.models.user import User, Profile, RolUsuario
from app.models.solicitud import Solicitud, EstadoSolicitud
from app.models.oferta import Oferta, EstadoOferta
from app.models.contract import Contract, EstadoContrato
from app.schemas.oferta import (
    OfertaSchema,
    OfertaCreateSchema,
    OfertaResponderSchema,
    OfertaCondicionesSchema,
    MisOfertasSchema,
)
from app.controllers.notifications import crear_notificacion
from app.controllers.subscriptions import PLANES_LIMITE_POSTULACIONES
from app.models.chat import Conversation, Message

blp = Blueprint("ofertas", __name__, description="Ofertas pds/solicitante")

# Rol que actúa como pds (valor "pds" en el enum RolUsuario).
ROL_PDS = RolUsuario.PDS.value  # "pds"

# Marcador de mensajes estructurados del chat (mismo formato que el
# frontend: ⟦c:<tipo>⟧<json>).
MARCA_CHAT = "⟦c:"
MARCA_CHAT_FIN = "⟧"


def _publicar_en_chat(
    emisor_id: int,
    destinatario_id: int,
    tipo: str,
    payload: dict,
) -> None:
    """Crea (o reutiliza) la conversación 1:1 y deja un mensaje estructurado.

    Así la negociación vive en el hilo de chat: la oferta del PDS aparece
    en la conversación con el solicitante sin que este tenga que abrir la
    card de chambas. No falla la operación si el chat no puede escribirse.
    """
    try:
        a, b = Conversation.normalize(emisor_id, destinatario_id)
        conv = Conversation.query.filter_by(user_a_id=a, user_b_id=b).first()
        if conv is None:
            conv = Conversation(user_a_id=a, user_b_id=b)
            db.session.add(conv)
            db.session.flush()

        contenido = (
            f"{MARCA_CHAT}{tipo}{MARCA_CHAT_FIN}"
            f"{json.dumps(payload, ensure_ascii=False)}"
        )
        msg = Message(
            conversation_id=conv.id,
            sender_id=emisor_id,
            contenido=contenido,
            leido=False,
        )
        db.session.add(msg)
        db.session.commit()

        socketio.emit(
            "message",
            {
                "id": msg.id,
                "conversation_id": conv.id,
                "sender_id": emisor_id,
                "contenido": contenido,
                "leido": False,
                "creado_en": msg.creado_en.isoformat() if msg.creado_en else None,
            },
            room=f"conversation_{conv.id}",
        )
    except Exception:
        db.session.rollback()


def _emit_oferta(event: str, oferta: Oferta, target_user_id: int) -> None:
    """Emite evento de oferta a la sala user:<id> del destinatario."""
    payload = {
        "oferta_id": oferta.id,
        "solicitud_id": oferta.solicitud_id,
        "estado": oferta.estado,
        "pds_id": oferta.pds_id,
        "aceptada_por_solicitante": oferta.aceptada_por_solicitante,
        "aceptada_por_pds": oferta.aceptada_por_pds,
        "monto_final": oferta.monto_final,
    }
    socketio.emit(event, payload, room=f"user:{target_user_id}")


def _emit_contrato_creado(contract: Contract, target_user_id: int) -> None:
    """Avisa a una parte que el contrato de la negociación está listo."""
    socketio.emit(
        "contrato:creado",
        {
            "contract_id": contract.id,
            "service_id": contract.service_id,
            "proveedor_id": contract.proveedor_id,
            "solicitante_id": contract.solicitante_id,
            "estado": contract.estado.value,
            "monto": contract.monto,
        },
        room=f"user:{target_user_id}",
    )


def _contraparte_oferta(oferta: Oferta, user_id: int) -> int:
    """Devuelve el id del otro participante de la negociación."""
    return oferta.solicitud.solicitante_id if user_id == oferta.pds_id else oferta.pds_id


def _valor_vigente(oferta: Oferta, solicitud: Solicitud):
    """Valor, fecha y horario actualmente en negociación.

    Si hay una contraoferta en curso manda el contravalor (contra_monto /
    contra_fecha / contra_horario); si no, la propuesta original. Los huecos
    se completan con la oferta original o con lo que tuviera la solicitud.
    """
    if oferta.contra_autor is not None and oferta.estado == EstadoOferta.CONTRAOFERTA.value:
        monto = oferta.contra_monto
        fecha = oferta.contra_fecha_deseada
        horario = oferta.contra_horario
    else:
        monto = oferta.monto
        fecha = oferta.fecha_deseada
        horario = oferta.horario

    if monto is None:
        monto = solicitud.presupuesto
    if fecha is None:
        fecha = (
            oferta.contra_fecha_deseada
            if oferta.contra_autor is not None
            else oferta.fecha_deseada
        )
    if not horario:
        horario = oferta.contra_horario or oferta.horario
    return monto, fecha, horario


def _contrato_de_oferta(oferta: Oferta, solicitud: Solicitud) -> Contract | None:
    """Contrato ya generado por esta oferta (evita duplicados)."""
    contract = Contract.query.filter_by(oferta_id=oferta.id).first()
    if contract is None:
        contract = (
            Contract.query.filter_by(
                service_id=solicitud.id,
                proveedor_id=oferta.pds_id,
            )
            .filter(
                Contract.estado.in_(
                    [
                        EstadoContrato.PENDIENTE.value,
                        EstadoContrato.EN_PROGRESO.value,
                    ]
                )
            )
            .first()
        )
    return contract


def _crear_contrato_por_oferta(
    oferta: Oferta,
    solicitud: Solicitud,
    monto,
    fecha_deseada,
    horario,
) -> Contract:
    """Crea (o completa) el contrato con los datos de la negociación."""
    contract = _contrato_de_oferta(oferta, solicitud)
    if contract is None:
        contract = Contract(
            service_id=solicitud.id,
            proveedor_id=oferta.pds_id,
            solicitante_id=solicitud.solicitante_id,
            estado=EstadoContrato.PENDIENTE.value,
        )
        db.session.add(contract)
    contract.oferta_id = oferta.id
    contract.monto = monto
    contract.condiciones = list(oferta.condiciones or [])
    contract.fecha_deseada = fecha_deseada
    contract.horario = horario
    db.session.flush()
    return contract


@blp.route("/solicitudes/<int:sid>/ofertas")
class OfertaList(MethodView):
    @jwt_required()
    @blp.arguments(OfertaCreateSchema)
    @blp.response(201, OfertaSchema)
    def post(self, data, sid):
        """Crea oferta. Solo pds y NO ser el dueño de la solicitud."""
        user_id = int(get_jwt_identity())
        if get_jwt().get("role") != ROL_PDS:
            abort(403, message="Solo un pds puede enviar ofertas.")

        solicitud = db.get_or_404(Solicitud, sid)
        if solicitud.solicitante_id == user_id:
            abort(403, message="No puedes ofertar en tu propia solicitud.")

        # RF-11: límite de postulaciones mensuales escalonado por plan.
        profile = Profile.query.get(user_id)
        plan = profile.plan if profile else "free"
        limite = PLANES_LIMITE_POSTULACIONES.get(plan)
        if limite is not None:
            now = datetime.now(timezone.utc)
            inicio_mes = now.replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
            count = Oferta.query.filter(
                Oferta.pds_id == user_id,
                Oferta.created_at >= inicio_mes,
            ).count()
            if count >= limite:
                abort(
                    403,
                    message=(
                        f"Has alcanzado el limite de postulaciones de tu plan "
                        f"({limite}/mes). Suscribete a un plan superior para "
                        f"mas postulaciones."
                    ),
                )

        oferta = Oferta(
            pds_id=user_id,
            solicitud_id=sid,
            monto=data.get("monto"),
            mensaje=data.get("mensaje"),
            # Parámetros "a convenir" concretados por el PDS en su propuesta.
            fecha_deseada=data.get("fecha_deseada"),
            horario=data.get("horario"),
            estado=EstadoOferta.PENDIENTE.value,
            # Quien propone acepta su propia propuesta: el acuerdo se cierra
            # cuando la otra parte acepta el valor vigente.
            aceptada_por_pds=True,
        )
        db.session.add(oferta)
        db.session.commit()

        # Feedback loop: el PDS respondió a una recomendación del motor.
        try:
            from app.models.recommendation_log import RecommendationLog
            RecommendationLog.mark_response(solicitud.id, user_id)
        except Exception:
            db.session.rollback()

        # Notifica al solicitante (dueño) y emite socket a su sala.
        crear_notificacion(
            solicitud.solicitante_id,
            "oferta_nueva",
            f"Has recibido una nueva oferta de {oferta.pds.nombre or 'un pds'}.",
        )
        db.session.commit()
        _emit_oferta("oferta:nueva", oferta, solicitud.solicitante_id)

        # La oferta también queda en el hilo de chat con el solicitante:
        # la negociación se ve y se continúa desde el chat.
        _publicar_en_chat(
            user_id,
            solicitud.solicitante_id,
            "oferta",
            {
                "ofertaId": oferta.id,
                "solicitudId": sid,
                "monto": oferta.monto,
                "mensaje": oferta.mensaje,
                "fecha": oferta.fecha_deseada,
                "horario": oferta.horario,
            },
        )
        return oferta

    @jwt_required()
    @blp.response(200, OfertaSchema(many=True))
    def get(self, sid):
        """Lista ofertas. Solo dueño o pds con oferta en la solicitud."""
        user_id = int(get_jwt_identity())
        solicitud = db.get_or_404(Solicitud, sid)
        es_dueno = solicitud.solicitante_id == user_id
        es_pds_participante = (
            Oferta.query.filter_by(solicitud_id=sid, pds_id=user_id).first()
            is not None
        )
        if not (es_dueno or es_pds_participante):
            abort(403, message="No tienes acceso a estas ofertas.")
        return (
            Oferta.query.filter_by(solicitud_id=sid)
            .order_by(Oferta.created_at.desc())
            .all()
        )


@blp.route("/mis-ofertas")
class MisOfertas(MethodView):
    @jwt_required()
    @blp.response(200, MisOfertasSchema(many=True))
    def get(self):
        """Ofertas del pds actual con resumen de la solicitud.

        Supports optional page/per_page query params for pagination (P2-4).
        If no params, returns all items (backward compatible).
        """
        user_id = int(get_jwt_identity())
        query = (
            Oferta.query.filter_by(pds_id=user_id)
            .order_by(Oferta.created_at.desc())
        )

        from app.services.pagination import paginate_query
        page = request.args.get("page")
        per_page = request.args.get("per_page")
        result = paginate_query(query, page=page, per_page=per_page)

        if isinstance(result, list):
            ofertas = result
        else:
            ofertas = result["items"]

        resultado = []
        for o in ofertas:
            s = o.solicitud
            resultado.append(
                {
                    "id": o.id,
                    "solicitud_id": o.solicitud_id,
                    "monto": o.monto,
                    "mensaje": o.mensaje,
                    "estado": o.estado,
                    "contra_monto": o.contra_monto,
                    "contra_mensaje": o.contra_mensaje,
                    "contra_autor": o.contra_autor,
                    "aceptada_por_solicitante": o.aceptada_por_solicitante,
                    "aceptada_por_pds": o.aceptada_por_pds,
                    "monto_final": o.monto_final,
                    "condiciones": o.condiciones or [],
                    "created_at": o.created_at,
                    "solicitud": (
                        {
                            "id": s.id,
                            "titulo": s.titulo,
                            "estado": (
                                s.estado.value
                                if isinstance(s.estado, EstadoSolicitud)
                                else s.estado
                            ),
                        }
                        if s
                        else None
                    ),
                }
            )

        if isinstance(result, list):
            return resultado
        result["items"] = resultado
        return result


@blp.route("/ofertas/<int:oid>/responder")
class OfertaResponder(MethodView):
    @jwt_required()
    @blp.arguments(OfertaResponderSchema)
    @blp.response(200, OfertaSchema)
    def post(self, data, oid):
        """Responde una oferta: aceptar/rechazar/contraofertar/aceptar_contraoferta."""
        user_id = int(get_jwt_identity())
        oferta = db.get_or_404(Oferta, oid)
        solicitud = db.session.get(Solicitud, oferta.solicitud_id)
        if solicitud is None:
            abort(404, message="La solicitud asociada no existe.")
        accion = data["accion"]

        # Autorización por acción.
        if accion in ("aceptar", "aceptar_contraoferta"):
            # Aceptación bilateral: tanto el solicitante como el pds pueden
            # aceptar el valor vigente. "aceptar_contraoferta" es el alias
            # histórico del pds.
            if user_id not in (solicitud.solicitante_id, oferta.pds_id):
                abort(403, message="Solo las partes de la negociación pueden aceptar.")
        elif accion == "rechazar":
            # Solicitante desde pendiente/contraoferta; PDS rechaza una
            # contraoferta que no le conviene (negociación "a convenir").
            es_pds_en_contraoferta = (
                oferta.pds_id == user_id
                and oferta.estado == EstadoOferta.CONTRAOFERTA.value
            )
            if solicitud.solicitante_id != user_id and not es_pds_en_contraoferta:
                abort(403, message="No tienes permiso para rechazar esta oferta.")
        elif accion == "contraofertar":
            # Solicitante contraoferta desde pendiente/contraoferta; el PDS
            # puede ajustar el precio cuando el solicitante contraofertó
            # (contra-contraoferta): el valor "a convenir" se negocia en el chat.
            es_pds_en_contraoferta = (
                oferta.pds_id == user_id
                and oferta.estado == EstadoOferta.CONTRAOFERTA.value
            )
            if solicitud.solicitante_id != user_id and not es_pds_en_contraoferta:
                abort(403, message="Solo las partes de la negociación pueden contraofertar.")
        else:
            abort(400, message="Acción inválida.")

        # --- Aceptación bilateral: cada parte acepta el valor vigente ---
        if accion in ("aceptar", "aceptar_contraoferta"):
            # Idempotencia: si la oferta ya está aceptada no se duplica el
            # contrato ni se vuelven a cobrar monedas.
            if oferta.estado == EstadoOferta.ACEPTADA.value:
                db.session.commit()
                return oferta

            es_pds = user_id == oferta.pds_id
            monto, fecha_convenida, horario_convenido = _valor_vigente(
                oferta, solicitud
            )

            if es_pds:
                oferta.aceptada_por_pds = True
            else:
                oferta.aceptada_por_solicitante = True

            if not (oferta.aceptada_por_pds and oferta.aceptada_por_solicitante):
                #-Acceptación parcial: el valor queda proposes pero falta la
                # otra parte. La solicitud y el contrato se cierran cuando
                # ambos aceptan.
                contraparte = _contraparte_oferta(oferta, user_id)
                crear_notificacion(
                    contraparte,
                    "oferta_aceptacion_pendiente",
                    (
                        "Aceptaste el valor propuesto. Falta tu contraparte para "
                        "cerrar el acuerdo."
                        if user_id == solicitud.solicitante_id
                        else "El solicitante aceptó el valor propuesto. Falta tu "
                        "confirmación para cerrar el acuerdo."
                    ),
                )
                db.session.commit()
                _emit_oferta("oferta:actualizada", oferta, contraparte)
                return oferta

            # --- Acuerdo bilateral ---
            oferta.estado = EstadoOferta.ACEPTADA.value
            oferta.monto_final = monto
            oferta.fecha_aceptacion = datetime.now(timezone.utc)

            # --- RF-26/27: Validar monedas en Modalidad B (sin comisión) ---
            # El cobro ocurre UNA vez, al cerrarse el acuerdo.
            try:
                from app.services.wallet import get_modalidad, usar_monedas

                modalidad = get_modalidad(solicitud.id)
                if modalidad.tipo.value == "B_sin_comision":
                    # Descontar 50 monedas al PDS por usar modalidad B
                    usar_monedas(
                        oferta.pds_id, 50, f"MODALIDAD-B-SOLICITUD-{solicitud.id}"
                    )
            except ValueError as e:
                abort(400, message=str(e))
            except Exception:
                pass  # Si no existe modalidad, continuar

            # El monto acordado se convierte en el nuevo precio de la
            # solicitud (el contrato lleva el valor final en `monto`).
            if monto is not None:
                solicitud.presupuesto = monto
            if fecha_convenida is not None:
                solicitud.fecha_deseada = fecha_convenida
            if horario_convenido:
                solicitud.horario = horario_convenido

            contract = _crear_contrato_por_oferta(
                oferta, solicitud, monto, fecha_convenida, horario_convenido
            )

            # La solicitud NO pasa a "en curso" todavía: solo cuando ambas
            # partes firman el contrato (PATCH /contracts/<id>/estado aceptar)
            # se marca ASIGNADA y se genera la chamba del módulo de gestión.

            # Las demás ofertas de la misma solicitud quedan rechazadas.
            otras = Oferta.query.filter(
                Oferta.solicitud_id == solicitud.id,
                Oferta.id != oferta.id,
                Oferta.estado.in_(
                    [EstadoOferta.PENDIENTE.value, EstadoOferta.CONTRAOFERTA.value]
                ),
            ).all()
            for o in otras:
                o.estado = EstadoOferta.RECHAZADA.value

            crear_notificacion(
                oferta.pds_id,
                "oferta_aceptada",
                "Acordaron el valor: el contrato quedó creado. Fírmalo para activar la chamba.",
            )
            crear_notificacion(
                solicitud.solicitante_id,
                "oferta_aceptada",
                "Acordaron el valor: el contrato quedó creado. Fírmalo para activar la chamba.",
            )
            db.session.commit()
            _emit_oferta("oferta:actualizada", oferta, oferta.pds_id)
            _emit_oferta("oferta:actualizada", oferta, solicitud.solicitante_id)
            _emit_contrato_creado(contract, oferta.pds_id)
            _emit_contrato_creado(contract, solicitud.solicitante_id)

            # Feedback loop: la recomendación terminó en contrato aceptado.
            try:
                from app.models.recommendation_log import RecommendationLog
                RecommendationLog.mark_accepted(solicitud.id, oferta.pds_id)
            except Exception:
                db.session.rollback()
            return oferta

        # --- Rechazo (solicitante o PDS) ---
        if accion == "rechazar":
            oferta.estado = EstadoOferta.RECHAZADA.value
            contraparte = _contraparte_oferta(oferta, user_id)
            mensaje = (
                "El prestador rechazó la contraoferta."
                if user_id == oferta.pds_id
                else "Tu oferta fue rechazada."
            )
            crear_notificacion(contraparte, "oferta_rechazada", mensaje)
            db.session.commit()
            _emit_oferta("oferta:actualizada", oferta, contraparte)
            return oferta

        # --- Contraoferta (solicitante o PDS ajustan precio/fecha/horario) ---
        if accion == "contraofertar":
            oferta.estado = EstadoOferta.CONTRAOFERTA.value
            oferta.contra_monto = data.get("contra_monto")
            oferta.contra_mensaje = data.get("contra_mensaje")
            # Ajustes negociados de parámetros "a convenir".
            oferta.contra_fecha_deseada = data.get("fecha_deseada")
            oferta.contra_horario = data.get("horario")
            # Quién propone la contraoferta y a quién le queda aceptar.
            oferta.contra_autor = "pds" if user_id == oferta.pds_id else "solicitante"
            if user_id == oferta.pds_id:
                oferta.aceptada_por_pds = True
                oferta.aceptada_por_solicitante = False
            else:
                oferta.aceptada_por_solicitante = True
                oferta.aceptada_por_pds = False
            if user_id == oferta.pds_id:
                crear_notificacion(
                    solicitud.solicitante_id,
                    "oferta_contraoferta",
                    "El prestador respondió con una contraoferta.",
                )
            else:
                crear_notificacion(
                    oferta.pds_id,
                    "oferta_contraoferta",
                    "El solicitante envió una contraoferta.",
                )
            db.session.commit()
            _emit_oferta("oferta:actualizada", oferta, _contraparte_oferta(oferta, user_id))
            return oferta


@blp.route("/ofertas/<int:oid>/condiciones")
class OfertaCondiciones(MethodView):
    @jwt_required()
    @blp.arguments(OfertaCondicionesSchema)
    @blp.response(200, OfertaSchema)
    def post(self, data, oid):
        """Agrega una condición acordada a la negociación.

        Las condiciones quedan guardadas en la oferta y se trasladan al
        contrato cuando ambas partes aceptan el valor.
        """
        user_id = int(get_jwt_identity())
        oferta = db.get_or_404(Oferta, oid)
        solicitud = db.session.get(Solicitud, oferta.solicitud_id)
        if solicitud is None:
            abort(404, message="La solicitud asociada no existe.")
        if user_id not in (solicitud.solicitante_id, oferta.pds_id):
            abort(403, message="Solo las partes de la negociación pueden agregar condiciones.")

        texto = (data.get("texto") or "").strip()
        if not texto:
            abort(400, message="La condición no puede estar vacía.")

        condiciones = list(oferta.condiciones or [])
        condiciones.append(
            {
                "texto": texto,
                "autor": data.get("autor")
                or ("solicitante" if user_id == solicitud.solicitante_id else "pds"),
                "fecha": datetime.now(timezone.utc).isoformat(),
            }
        )
        oferta.condiciones = condiciones

        # Si el contrato ya existe, la condición también se incorpora.
        contract = _contrato_de_oferta(oferta, solicitud)
        if contract is not None:
            contract.condiciones = condiciones

        db.session.commit()
        _emit_oferta("oferta:actualizada", oferta, _contraparte_oferta(oferta, user_id))
        return oferta
