"""Anuncios blueprint: ofertas laborales NO vinculantes de negocios.

Banner publicitario visible en el mapa de negocios para todos los roles
(solicitante, pds, negocio). Permite postulaciones de PDS y gestión de
contacto del negocio (contactar/descartar). Sin contratos ni chambas.
"""

from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.extensions import db, socketio
from app.models.user import User, RolUsuario
from app.models.anuncio import (
    AnuncioLaboral,
    EstadoAnuncio,
    AnuncioPostulacion,
    EstadoPostulacionAnuncio,
)
from app.schemas.anuncio import (
    AnuncioCreateSchema,
    AnuncioEstadoSchema,
    AnuncioPostulacionCreateSchema,
    AnuncioPostulacionSchema,
    AnuncioSchema,
    PostulacionEstadoSchema,
)
from app.controllers.notifications import crear_notificacion

blp = Blueprint("anuncios", __name__, description="Anuncios laborales (no vinculantes)")

ROL_NEGOCIO = RolUsuario.MERCHANT.value  # "merchant"
ROL_PDS = RolUsuario.PDS.value  # "pds"


def _emit_anuncio(event: str, anuncio: AnuncioLaboral, target_user_id: int) -> None:
    socketio.emit(
        event,
        {"anuncio_id": anuncio.id, "estado": anuncio.estado.value},
        room=f"user:{target_user_id}",
    )


def _anuncio_con_negocio(anuncio: AnuncioLaboral) -> AnuncioLaboral:
    anuncio.negocio_nombre = (
        anuncio.negocio.nombre or f"Negocio #{anuncio.negocio_id}"
    )
    return anuncio


@blp.route("/")
class AnuncioRoot(MethodView):
    @jwt_required()
    @blp.arguments(AnuncioCreateSchema)
    @blp.response(201, AnuncioSchema)
    def post(self, data):
        """El negocio publica un anuncio laboral (banner publicitario)."""
        user_id = int(get_jwt_identity())
        if get_jwt().get("role") != ROL_NEGOCIO:
            abort(403, message="Solo un negocio puede publicar anuncios laborales.")

        anuncio = AnuncioLaboral(
            negocio_id=user_id,
            titulo=data["titulo"],
            descripcion=data["descripcion"],
            categoria=data["categoria"],
            ubicacion=data.get("ubicacion"),
            latitud=data.get("latitud"),
            longitud=data.get("longitud"),
            vacantes=data.get("vacantes"),
            estado=EstadoAnuncio.PUBLICADO,
        )
        db.session.add(anuncio)
        db.session.commit()
        return _anuncio_con_negocio(anuncio)

    @jwt_required()
    @blp.response(200)
    def get(self):
        """Feed público de anuncios (todos los roles; visible en el mapa)."""
        query = (
            AnuncioLaboral.query.filter_by(estado=EstadoAnuncio.PUBLICADO)
            .order_by(AnuncioLaboral.creado_en.desc())
        )
        categoria = request.args.get("categoria")
        if categoria:
            query = query.filter(AnuncioLaboral.categoria == categoria)
        anuncios = query.all()
        for a in anuncios:
            _anuncio_con_negocio(a)
        return AnuncioSchema(many=True).dump(anuncios)


@blp.route("/negocio/<int:uid>")
class AnunciosDelNegocio(MethodView):
    @jwt_required()
    @blp.response(200)
    def get(self, uid):
        """Anuncios del negocio (dueño ve todos + contadores; otros solo publicados)."""
        user_id = int(get_jwt_identity())
        es_dueño = user_id == uid
        query = AnuncioLaboral.query.filter_by(negocio_id=uid)
        if not es_dueño:
            query = query.filter_by(estado=EstadoAnuncio.PUBLICADO)
        anuncios = query.order_by(AnuncioLaboral.creado_en.desc()).all()
        dump = AnuncioSchema(many=True).dump(anuncios)
        if es_dueño:
            for a, item in zip(anuncios, dump):
                item["postulaciones_count"] = len(a.postulaciones)
        return dump


@blp.route("/<int:anuncio_id>")
class AnuncioDetail(MethodView):
    @jwt_required()
    @blp.response(200)
    def get(self, anuncio_id):
        """Detalle del anuncio (postulaciones solo para el dueño)."""
        user_id = int(get_jwt_identity())
        anuncio = db.get_or_404(AnuncioLaboral, anuncio_id)
        es_dueño = anuncio.negocio_id == user_id
        dump = AnuncioSchema().dump(_anuncio_con_negocio(anuncio))
        if es_dueño:
            dump["postulaciones"] = AnuncioPostulacionSchema(many=True).dump(
                anuncio.postulaciones
            )
        else:
            dump["postulaciones"] = []
        dump["postulaciones_count"] = len(anuncio.postulaciones)
        return dump


@blp.route("/<int:anuncio_id>/estado")
class AnuncioEstado(MethodView):
    @jwt_required()
    @blp.arguments(AnuncioEstadoSchema)
    @blp.response(200, AnuncioSchema)
    def patch(self, data, anuncio_id):
        """El negocio cierra/reabre su anuncio."""
        user_id = int(get_jwt_identity())
        anuncio = db.get_or_404(AnuncioLaboral, anuncio_id)
        if anuncio.negocio_id != user_id:
            abort(403, message="Solo el negocio dueño puede gestionar el anuncio.")
        accion = data["accion"]
        if accion == "cerrar":
            if anuncio.estado == EstadoAnuncio.CERRADO:
                abort(400, message="El anuncio ya está cerrado.")
            anuncio.estado = EstadoAnuncio.CERRADO
        else:
            if anuncio.estado == EstadoAnuncio.PUBLICADO:
                abort(400, message="El anuncio ya está publicado.")
            anuncio.estado = EstadoAnuncio.PUBLICADO
        db.session.commit()
        return _anuncio_con_negocio(anuncio)


@blp.route("/<int:anuncio_id>/postulaciones")
class AnuncioPostulacionList(MethodView):
    @jwt_required()
    @blp.arguments(AnuncioPostulacionCreateSchema)
    @blp.response(201, AnuncioPostulacionSchema)
    def post(self, data, anuncio_id):
        """Un PDS se postula (solo contacto, no vinculante)."""
        user_id = int(get_jwt_identity())
        if get_jwt().get("role") != ROL_PDS:
            abort(403, message="Solo un pds puede postularse a un anuncio laboral.")
        anuncio = db.get_or_404(AnuncioLaboral, anuncio_id)
        if anuncio.negocio_id == user_id:
            abort(403, message="No puedes postularte a tu propio anuncio.")
        if anuncio.estado != EstadoAnuncio.PUBLICADO:
            abort(400, message="El anuncio ya no acepta postulaciones.")
        ya = AnuncioPostulacion.query.filter_by(
            anuncio_id=anuncio.id, pds_id=user_id
        ).first()
        if ya:
            abort(400, message="Ya te postulaste a este anuncio.")

        # Contacto por defecto desde los datos del PDS (telefono vive en User).
        user = User.query.get(user_id)
        postulacion = AnuncioPostulacion(
            anuncio_id=anuncio.id,
            pds_id=user_id,
            mensaje=data.get("mensaje"),
            telefono_contacto=data.get("telefono_contacto") or (user.telefono if user else None),
            email_contacto=data.get("email_contacto") or (user.email if user else None),
            estado=EstadoPostulacionAnuncio.PENDIENTE,
        )
        db.session.add(postulacion)
        db.session.commit()
        crear_notificacion(
            anuncio.negocio_id,
            "anuncio_postulacion",
            f"Un prestador se postuló a tu anuncio: {anuncio.titulo}.",
        )
        _emit_anuncio("anuncio:postulacion", anuncio, anuncio.negocio_id)
        postulacion.pds_nombre = postulacion.pds.nombre or f"Prestador #{user_id}"
        return postulacion

    @jwt_required()
    @blp.response(200)
    def get(self, anuncio_id):
        """Postulaciones del anuncio (gestión de contacto del negocio)."""
        user_id = int(get_jwt_identity())
        anuncio = db.get_or_404(AnuncioLaboral, anuncio_id)
        if anuncio.negocio_id != user_id:
            abort(403, message="Solo el negocio dueño gestiona las postulaciones.")
        postulaciones = (
            AnuncioPostulacion.query.filter_by(anuncio_id=anuncio.id)
            .order_by(AnuncioPostulacion.created_at.asc())
            .all()
        )
        for p in postulaciones:
            p.pds_nombre = p.pds.nombre or f"Prestador #{p.pds_id}"
        return AnuncioPostulacionSchema(many=True).dump(postulaciones)


@blp.route("/<int:anuncio_id>/postulaciones/<int:postulacion_id>")
class AnuncioPostulacionItem(MethodView):
    @jwt_required()
    @blp.arguments(PostulacionEstadoSchema)
    @blp.response(200, AnuncioPostulacionSchema)
    def patch(self, data, anuncio_id, postulacion_id):
        """Gestión de contacto: contactar / descartar (negocio dueño)."""
        user_id = int(get_jwt_identity())
        anuncio = db.get_or_404(AnuncioLaboral, anuncio_id)
        if anuncio.negocio_id != user_id:
            abort(403, message="Solo el negocio dueño gestiona las postulaciones.")
        postulacion = db.get_or_404(AnuncioPostulacion, postulacion_id)
        if postulacion.anuncio_id != anuncio.id:
            abort(400, message="La postulación no pertenece a este anuncio.")

        accion = data["accion"]
        if accion == "contactar":
            postulacion.estado = EstadoPostulacionAnuncio.CONTACTADO
            crear_notificacion(
                postulacion.pds_id,
                "anuncio_contactado",
                f"El negocio {anuncio.titulo} te contactó por tu postulación.",
            )
            _emit_anuncio("anuncio:contactado", anuncio, postulacion.pds_id)
        else:
            postulacion.estado = EstadoPostulacionAnuncio.DESCARTADO

        db.session.commit()
        postulacion.pds_nombre = postulacion.pds.nombre or f"Prestador #{postulacion.pds_id}"
        return postulacion