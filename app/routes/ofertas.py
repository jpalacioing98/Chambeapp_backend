"""Ofertas blueprint: negociación pds/solicitante (RF-04 negociación).

Endpoints (prefijo /api/v1):
  POST   /solicitudes/<sid>/ofertas   -> pds crea oferta (no dueño)
  GET    /solicitudes/<sid>/ofertas   -> dueño o pds con oferta
  GET    /mis-ofertas                 -> ofertas del pds actual
  POST   /ofertas/<oid>/responder     -> aceptar/rechazar/contraofertar
"""

from datetime import datetime, timezone

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
    MisOfertasSchema,
)
from app.routes.notifications import crear_notificacion

blp = Blueprint("ofertas", __name__, description="Ofertas pds/solicitante")

# Rol que actúa como pds (valor "pds" en el enum RolUsuario).
ROL_PDS = RolUsuario.PDS.value  # "pds"


def _emit_oferta(event: str, oferta: Oferta, target_user_id: int) -> None:
    """Emite evento de oferta a la sala user:<id> del destinatario."""
    payload = {
        "oferta_id": oferta.id,
        "solicitud_id": oferta.solicitud_id,
        "estado": oferta.estado,
        "pds_id": oferta.pds_id,
    }
    socketio.emit(event, payload, room=f"user:{target_user_id}")


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

        # RF-11: límite de postulaciones mensuales para planes free/basico.
        profile = Profile.query.get(user_id)
        plan = profile.plan if profile else "free"
        if plan in ("free", "basico"):
            now = datetime.now(timezone.utc)
            inicio_mes = now.replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
            count = Oferta.query.filter(
                Oferta.pds_id == user_id,
                Oferta.created_at >= inicio_mes,
            ).count()
            if count >= 5:
                abort(
                    403,
                    message=(
                        "Has alcanzado el limite de postulaciones de tu plan "
                        "(5/mes). Suscribete a Profesional para postulaciones "
                        "ilimitadas."
                    ),
                )

        oferta = Oferta(
            pds_id=user_id,
            solicitud_id=sid,
            monto=data.get("monto"),
            mensaje=data.get("mensaje"),
            estado=EstadoOferta.PENDIENTE.value,
        )
        db.session.add(oferta)
        db.session.commit()

        # Notifica al solicitante (dueño) y emite socket a su sala.
        crear_notificacion(
            solicitud.solicitante_id,
            "oferta_nueva",
            f"Has recibido una nueva oferta de {oferta.pds.nombre or 'un pds'}.",
        )
        db.session.commit()
        _emit_oferta("oferta:nueva", oferta, solicitud.solicitante_id)
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
        """Ofertas del pds actual con resumen de la solicitud."""
        user_id = int(get_jwt_identity())
        ofertas = (
            Oferta.query.filter_by(pds_id=user_id)
            .order_by(Oferta.created_at.desc())
            .all()
        )
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
        return resultado


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
        if accion in ("aceptar", "rechazar", "contraofertar"):
            if solicitud.solicitante_id != user_id:
                abort(403, message="Solo el solicitante puede responder la oferta.")
        elif accion == "aceptar_contraoferta":
            if oferta.pds_id != user_id:
                abort(
                    403,
                    message="Solo el pds puede aceptar la contraoferta.",
                )
        else:
            abort(400, message="Acción inválida.")

        # --- Aceptación (solicitante acepta, o pds acepta contraoferta) ---
        if accion in ("aceptar", "aceptar_contraoferta"):
            monto = (
                oferta.monto
                if oferta.monto is not None
                else solicitud.presupuesto
            )
            contract = Contract(
                service_id=solicitud.id,
                proveedor_id=oferta.pds_id,
                solicitante_id=solicitud.solicitante_id,
                estado=EstadoContrato.PENDIENTE,
            )
            db.session.add(contract)
            oferta.estado = EstadoOferta.ACEPTADA.value
            solicitud.estado = EstadoSolicitud.ASIGNADA

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
                "Tu oferta fue aceptada.",
            )
            db.session.commit()
            _emit_oferta("oferta:actualizada", oferta, oferta.pds_id)
            return oferta

        # --- Rechazo ---
        if accion == "rechazar":
            oferta.estado = EstadoOferta.RECHAZADA.value
            crear_notificacion(
                oferta.pds_id,
                "oferta_rechazada",
                "Tu oferta fue rechazada.",
            )
            db.session.commit()
            _emit_oferta("oferta:actualizada", oferta, oferta.pds_id)
            return oferta

        # --- Contraoferta ---
        if accion == "contraofertar":
            oferta.estado = EstadoOferta.CONTRAOFERTA.value
            oferta.contra_monto = data.get("contra_monto")
            oferta.contra_mensaje = data.get("contra_mensaje")
            crear_notificacion(
                oferta.pds_id,
                "oferta_contraoferta",
                "El solicitante envió una contraoferta.",
            )
            db.session.commit()
            _emit_oferta("oferta:actualizada", oferta, oferta.pds_id)
            return oferta
