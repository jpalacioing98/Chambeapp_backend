"""Maranas blueprint: Maraña (rebusque) — adenda derivada de una chamba.

Cuando una adenda implica trabajo de otro perfil, el solicitante la lanza
como maraña: micro solicitud pública para otros PDS. Negociación tipo
ofertas (postular/contraofertar/aceptar) y pago directo dual (como chamba).

La creación vive en el blueprint de chambas (POST /chambas/<id>/marana).
"""

from datetime import datetime, timezone

from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.extensions import db, socketio
from app.models.user import RolUsuario
from app.models.marana import (
    Marana,
    EstadoMarana,
    MaranaOferta,
    EstadoMaranaOferta,
)
from app.schemas.marana import (
    MaranaEstadoSchema,
    MaranaOfertaCreateSchema,
    MaranaOfertaSchema,
    MaranaPagoSchema,
    MaranaResponderSchema,
    MaranaSchema,
)
from app.routes.notifications import crear_notificacion
from app.services.pagination import paginate_query

blp = Blueprint("maranas", __name__, description="Marañas (rebusques): adendas derivadas")

ROL_PDS = RolUsuario.PDS.value  # "pds"


def _emit_marana(event: str, marana: Marana, target_user_id: int) -> None:
    socketio.emit(
        event,
        {"marana_id": marana.id, "estado": marana.estado.value},
        room=f"user:{target_user_id}",
    )


@blp.route("/chamba/<int:chamba_id>")
class MaranaDeChamba(MethodView):
    @jwt_required()
    @blp.response(200)
    def get(self, chamba_id):
        """Marañas derivadas de una chamba (solo participantes)."""
        from app.models.chamba import Chamba

        user_id = int(get_jwt_identity())
        chamba = db.get_or_404(Chamba, chamba_id)
        if user_id not in (chamba.contract.solicitante_id, chamba.contract.proveedor_id):
            abort(403, message="No participas en esta chamba.")
        maranas = (
            Marana.query.filter_by(chamba_id=chamba.id)
            .order_by(Marana.creado_en.desc())
            .all()
        )
        return MaranaSchema(many=True).dump(maranas)


@blp.route("/")
class MaranaList(MethodView):
    @jwt_required()
    @blp.response(200)
    def get(self):
        """Feed público de marañas para PDS (filtro por categoría)."""
        query = (
            Marana.query.filter_by(estado=EstadoMarana.PUBLICADO)
            .order_by(Marana.creado_en.desc())
        )
        categoria = request.args.get("categoria")
        if categoria:
            query = query.filter(Marana.categoria == categoria)
        page = request.args.get("page")
        per_page = request.args.get("per_page")
        result = paginate_query(query, page=page, per_page=per_page)
        if isinstance(result, list):
            return MaranaSchema(many=True).dump(result)
        result["items"] = MaranaSchema(many=True).dump(result["items"])
        return result


@blp.route("/<int:marana_id>")
class MaranaDetail(MethodView):
    @jwt_required()
    @blp.response(200, MaranaSchema)
    def get(self, marana_id):
        """Detalle de la maraña (publicada o propia)."""
        marana = db.get_or_404(Marana, marana_id)
        return marana


@blp.route("/<int:marana_id>/ofertas")
class MaranaOfertaList(MethodView):
    @jwt_required()
    @blp.arguments(MaranaOfertaCreateSchema)
    @blp.response(201, MaranaOfertaSchema)
    def post(self, data, marana_id):
        """PDS postula a la maraña (monto + mensaje)."""
        user_id = int(get_jwt_identity())
        if get_jwt().get("role") != ROL_PDS:
            abort(403, message="Solo un pds puede postularse.")
        marana = db.get_or_404(Marana, marana_id)
        if marana.solicitante_id == user_id:
            abort(403, message="No puedes postularte a tu propia maraña.")
        if marana.estado != EstadoMarana.PUBLICADO:
            abort(400, message="La maraña ya no acepta postulaciones.")

        activa = MaranaOferta.query.filter(
            MaranaOferta.marana_id == marana.id,
            MaranaOferta.pds_id == user_id,
            MaranaOferta.estado.in_(
                [EstadoMaranaOferta.PENDIENTE.value, EstadoMaranaOferta.CONTRAOFERTA.value]
            ),
        ).first()
        if activa:
            abort(400, message="Ya tienes una postulación activa en esta maraña.")

        oferta = MaranaOferta(
            marana_id=marana.id,
            pds_id=user_id,
            monto=data.get("monto"),
            mensaje=data.get("mensaje"),
            estado=EstadoMaranaOferta.PENDIENTE.value,
        )
        db.session.add(oferta)
        db.session.commit()
        crear_notificacion(
            marana.solicitante_id,
            "marana_oferta",
            f"Un prestador se postuló a tu maraña: {marana.titulo}.",
        )
        _emit_marana("marana:actualizada", marana, marana.solicitante_id)
        return oferta

    @jwt_required()
    @blp.response(200)
    def get(self, marana_id):
        """Postulaciones (solicitante o el PDS postulado)."""
        user_id = int(get_jwt_identity())
        marana = db.get_or_404(Marana, marana_id)
        es_solicitante = marana.solicitante_id == user_id
        es_pds = MaranaOferta.query.filter_by(marana_id=marana.id, pds_id=user_id).first()
        if not es_solicitante and not es_pds:
            abort(403, message="No tienes acceso a las postulaciones de esta maraña.")
        ofertas = (
            MaranaOferta.query.filter_by(marana_id=marana.id)
            .order_by(MaranaOferta.created_at.asc())
            .all()
        )
        return MaranaOfertaSchema(many=True).dump(ofertas)


@blp.route("/<int:marana_id>/responder")
class MaranaResponder(MethodView):
    @jwt_required()
    @blp.arguments(MaranaResponderSchema)
    @blp.response(200, MaranaOfertaSchema)
    def post(self, data, marana_id):
        """Negociación de la postulación (aceptar/rechazar/contraofertar)."""
        user_id = int(get_jwt_identity())
        accion = data["accion"]
        marana = db.get_or_404(Marana, marana_id)
        oferta_id = request.args.get("oferta_id", type=int)
        oferta = db.get_or_404(MaranaOferta, oferta_id) if oferta_id else (
            MaranaOferta.query.filter_by(
                marana_id=marana.id, pds_id=user_id
            ).order_by(MaranaOferta.created_at.desc()).first()
        )
        if oferta is None or oferta.marana_id != marana.id:
            abort(400, message="Postulación inválida para esta maraña.")
        if marana.estado != EstadoMarana.PUBLICADO:
            abort(400, message="La maraña ya no está en negociación.")

        es_solicitante = marana.solicitante_id == user_id
        es_pds = oferta.pds_id == user_id
        en_contraoferta = oferta.estado == EstadoMaranaOferta.CONTRAOFERTA.value

        if accion in ("aceptar",):
            if not es_solicitante:
                abort(403, message="Solo el solicitante puede aceptar una postulación.")
        elif accion == "rechazar":
            if not (es_solicitante or (es_pds and en_contraoferta)):
                abort(403, message="No tienes permiso para rechazar esta postulación.")
        elif accion == "contraofertar":
            if not (es_solicitante or (es_pds and en_contraoferta)):
                abort(403, message="Solo las partes de la negociación pueden contraofertar.")
        elif accion == "aceptar_contraoferta":
            if not es_pds:
                abort(403, message="Solo el pds postulado puede aceptar la contraoferta.")
        else:
            abort(400, message="Acción inválida.")

        if accion == "contraofertar":
            oferta.estado = EstadoMaranaOferta.CONTRAOFERTA.value
            oferta.contra_monto = data.get("contra_monto")
            oferta.contra_mensaje = data.get("contra_mensaje")
            db.session.commit()
            target = marana.solicitante_id if es_pds else oferta.pds_id
            crear_notificacion(
                target,
                "marana_contraoferta",
                "Una contraoferta ajusta la maraña: " + marana.titulo + ".",
            )
            _emit_marana("marana:actualizada", marana, target)
            return oferta

        if accion == "rechazar":
            oferta.estado = EstadoMaranaOferta.RECHAZADA.value
            db.session.commit()
            target = marana.solicitante_id if es_pds else oferta.pds_id
            crear_notificacion(
                target,
                "marana_oferta_rechazada",
                "Una postulación de la maraña fue rechazada.",
            )
            _emit_marana("marana:actualizada", marana, target)
            return oferta

        # Aceptar / aceptar_contraoferta → asignar la maraña.
        monto_acordado = (
            oferta.contra_monto
            if oferta.contra_monto is not None
            and (accion == "aceptar_contraoferta" or en_contraoferta)
            else oferta.monto
        )
        oferta.estado = EstadoMaranaOferta.ACEPTADA.value
        for otra in MaranaOferta.query.filter(
            MaranaOferta.marana_id == marana.id,
            MaranaOferta.id != oferta.id,
            MaranaOferta.estado.in_(
                [EstadoMaranaOferta.PENDIENTE.value, EstadoMaranaOferta.CONTRAOFERTA.value]
            ),
        ).all():
            otra.estado = EstadoMaranaOferta.RECHAZADA.value

        marana.estado = EstadoMarana.ASIGNADO
        marana.pds_asignado_id = oferta.pds_id
        marana.fecha_asignacion = datetime.now(timezone.utc)
        if monto_acordado is not None:
            marana.presupuesto = monto_acordado

        db.session.commit()
        crear_notificacion(
            oferta.pds_id,
            "marana_asignada",
            f"¡Ganaste la maraña! {marana.titulo} te fue asignada.",
        )
        _emit_marana("marana:asignada", marana, oferta.pds_id)
        return oferta


@blp.route("/<int:marana_id>/estado")
class MaranaEstado(MethodView):
    @jwt_required()
    @blp.arguments(MaranaEstadoSchema)
    @blp.response(200, MaranaSchema)
    def patch(self, data, marana_id):
        """completar (pds asignado) / cancelar (solicitante)."""
        user_id = int(get_jwt_identity())
        marana = db.get_or_404(Marana, marana_id)
        accion = data["accion"]

        if accion == "completar":
            if marana.pds_asignado_id != user_id:
                abort(403, message="Solo el prestador asignado puede completar la maraña.")
            if marana.estado != EstadoMarana.ASIGNADO:
                abort(400, message="Solo se completa una maraña asignada.")
            marana.estado = EstadoMarana.COMPLETADO
            marana.fecha_entrega = datetime.now(timezone.utc)
            crear_notificacion(
                marana.solicitante_id,
                "marana_completada",
                f"El trabajo de la maraña '{marana.titulo}' fue entregado. Confirma el pago.",
            )
        elif accion == "cancelar":
            if marana.solicitante_id != user_id:
                abort(403, message="Solo el solicitante puede cancelar la maraña.")
            if marana.estado in (EstadoMarana.PAGADO, EstadoMarana.CANCELADO):
                abort(400, message="La maraña ya está cerrada.")
            marana.estado = EstadoMarana.CANCELADO
            if marana.pds_asignado_id:
                crear_notificacion(
                    marana.pds_asignado_id,
                    "marana_cancelada",
                    f"La maraña '{marana.titulo}' fue cancelada por el solicitante.",
                )
        else:
            abort(400, message="Acción inválida.")

        db.session.commit()
        _emit_marana("marana:actualizada", marana, marana.solicitante_id)
        return marana


@blp.route("/<int:marana_id>/pago")
class MaranaPago(MethodView):
    @jwt_required()
    @blp.arguments(MaranaPagoSchema)
    @blp.response(200, MaranaSchema)
    def post(self, data, marana_id):
        """Check-in de pago directo dual (como la chamba)."""
        user_id = int(get_jwt_identity())
        marana = db.get_or_404(Marana, marana_id)
        if marana.estado != EstadoMarana.COMPLETADO:
            abort(400, message="El pago solo se confirma tras la entrega del trabajo.")

        if user_id == marana.solicitante_id:
            marana.pago_confirmado_solicitante = True
        elif user_id == marana.pds_asignado_id:
            marana.pago_confirmado_prestador = True
        else:
            abort(403, message="No participas en esta maraña.")

        if data.get("monto_final") is not None:
            marana.pago_monto_final = data["monto_final"]

        if marana.pago_confirmado_solicitante and marana.pago_confirmado_prestador:
            marana.estado = EstadoMarana.PAGADO
            marana.fecha_pago = datetime.now(timezone.utc)

        db.session.commit()
        contraparte = (
            marana.pds_asignado_id
            if user_id == marana.solicitante_id
            else marana.solicitante_id
        )
        if contraparte:
            crear_notificacion(
                contraparte,
                "marana_pago",
                "Una de las partes confirmó el pago de la maraña.",
            )
        _emit_marana("marana:actualizada", marana, contraparte)
        return marana


@blp.route("/solicitante/<int:uid>")
class MaranaSolicitante(MethodView):
    @jwt_required()
    @blp.response(200)
    def get(self, uid):
        """Marañas donde soy solicitante."""
        user_id = int(get_jwt_identity())
        if user_id != uid:
            abort(403, message="Solo puedes ver tus propias marañas.")
        query = Marana.query.filter_by(solicitante_id=uid).order_by(Marana.creado_en.desc())
        estado = request.args.get("estado")
        if estado:
            if estado not in EstadoMarana.values():
                abort(400, message="Estado inválido.")
            query = query.filter(Marana.estado == EstadoMarana(estado))
        return MaranaSchema(many=True).dump(query.all())


@blp.route("/prestador/<int:uid>")
class MaranaPrestador(MethodView):
    @jwt_required()
    @blp.response(200)
    def get(self, uid):
        """Marañas donde soy prestador (asignadas o postuladas)."""
        user_id = int(get_jwt_identity())
        if user_id != uid:
            abort(403, message="Solo puedes ver tus propias marañas.")
        query = (
            Marana.query.filter(
                (Marana.pds_asignado_id == uid)
                | (
                    Marana.id.in_(
                        db.session.query(MaranaOferta.marana_id).filter(
                            MaranaOferta.pds_id == uid
                        )
                    )
                )
            )
            .order_by(Marana.creado_en.desc())
        )
        estado = request.args.get("estado")
        if estado:
            if estado not in EstadoMarana.values():
                abort(400, message="Estado inválido.")
            query = query.filter(Marana.estado == EstadoMarana(estado))
        return MaranaSchema(many=True).dump(query.all())