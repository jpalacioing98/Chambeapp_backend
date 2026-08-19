"""Solicitudes blueprint: crear/listar/detalle/estado/ratings (RF-03, RF-04)."""

from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models.user import User, Profile
from app.models.solicitud import Solicitud, Rating, EstadoSolicitud, UrgenciaSolicitud
from app.schemas.solicitud import (
    SolicitudCreateSchema,
    SolicitudEstadoSchema,
    SolicitudSchema,
)
from app.schemas.rating import RatingCreateSchema, RatingSchema

blp = Blueprint("solicitudes", __name__, description="Solicitudes y calificaciones")


def _recalcular_promedio(calificado_id: int) -> None:
    """Recalcula calificacion_promedio del perfil calificado."""
    ratings = Rating.query.filter_by(calificado_id=calificado_id).all()
    profile = db.session.get(Profile, calificado_id)
    if profile is None:
        return
    profile.calificacion_promedio = (
        sum(r.puntaje for r in ratings) / len(ratings) if ratings else 0.0
    )


@blp.route("/")
class SolicitudList(MethodView):
    @jwt_required()
    @blp.arguments(SolicitudCreateSchema, location="json")
    @blp.response(201, SolicitudSchema)
    def post(self, data):
        """RF-04: crea una solicitud (solicitante = usuario JWT)."""
        user_id = int(get_jwt_identity())

        for campo in ("titulo", "categoria", "descripcion", "ubicacion"):
            valor = data.get(campo)
            if not valor or not str(valor).strip():
                abort(400, message=f"El campo '{campo}' es requerido.")

        presupuesto = data.get("presupuesto")
        if presupuesto is not None and presupuesto < 50000:
            abort(400, message="El presupuesto mínimo es 50000.")

        solicitud = Solicitud(
            solicitante_id=user_id,
            titulo=data["titulo"],
            categoria=data["categoria"],
            descripcion=data["descripcion"],
            ubicacion=data["ubicacion"],
            presupuesto=presupuesto,  # None => "a convenir"
            fecha_deseada=data.get("fecha_deseada"),
            urgencia=data.get("urgencia"),
            especificaciones_tecnicas=data.get("especificaciones_tecnicas"),
            imagen_360=data.get("imagen_360"),
            estado=EstadoSolicitud.PUBLICADO,
        )
        solicitud.advertencia = None
        if solicitud.ubicacion != "Valledupar":
            solicitud.advertencia = (
                "La ubicación está fuera de Valledupar; verifica disponibilidad "
                "del pds."
            )

        db.session.add(solicitud)
        db.session.commit()
        return solicitud

    @blp.response(200, SolicitudSchema(many=True))
    def get(self):
        """RF-04: lista solicitudes con filtros opcionales."""
        query = Solicitud.query
        categoria = request.args.get("categoria")
        ubicacion = request.args.get("ubicacion")
        q = request.args.get("q")
        if categoria:
            query = query.filter(Solicitud.categoria == categoria)
        if ubicacion:
            query = query.filter(Solicitud.ubicacion == ubicacion)
        if q:
            query = query.filter(Solicitud.descripcion.ilike(f"%{q}%"))
        return query.order_by(Solicitud.creado_en.desc()).all()


@blp.route("/<int:solicitud_id>")
class SolicitudDetail(MethodView):
    @blp.response(200, SolicitudSchema)
    def get(self, solicitud_id):
        """RF-04: detalle de solicitud + ratings."""
        return db.get_or_404(Solicitud, solicitud_id)


@blp.route("/<int:solicitud_id>/estado")
class SolicitudEstado(MethodView):
    @jwt_required()
    @blp.arguments(SolicitudEstadoSchema)
    @blp.response(200, SolicitudSchema)
    def patch(self, data, solicitud_id):
        """Cambia estado; solo el dueño (solicitante_id)."""
        user_id = int(get_jwt_identity())
        solicitud = db.get_or_404(Solicitud, solicitud_id)
        if solicitud.solicitante_id != user_id:
            abort(403, message="Solo el dueño puede cambiar el estado.")
        solicitud.estado = EstadoSolicitud(data["estado"])
        db.session.commit()
        return solicitud


@blp.route("/<int:solicitud_id>/ratings")
class SolicitudRatings(MethodView):
    @jwt_required()
    @blp.arguments(RatingCreateSchema)
    @blp.response(201, RatingSchema)
    def post(self, data, solicitud_id):
        """RF-03: crea Rating. Requiere solicitud completada y autor único."""
        user_id = int(get_jwt_identity())
        solicitud = db.get_or_404(Solicitud, solicitud_id)

        if solicitud.estado != EstadoSolicitud.COMPLETADO:
            abort(409, message="solicitud no completada")

        if Rating.query.filter_by(service_id=solicitud_id, autor_id=user_id).first():
            abort(409, message="Ya calificaste esta solicitud.")

        calificado_id = data["calificado_id"]
        if not db.session.get(User, calificado_id):
            abort(404, message="El usuario calificado no existe.")

        rating = Rating(
            service_id=solicitud_id,
            autor_id=user_id,
            calificado_id=calificado_id,
            puntaje=data["puntaje"],
            comentario=data.get("comentario"),
        )
        db.session.add(rating)
        db.session.flush()
        _recalcular_promedio(calificado_id)
        db.session.commit()
        return rating

    @blp.response(200, RatingSchema(many=True))
    def get(self, solicitud_id):
        """RF-03: lista ratings de la solicitud."""
        db.get_or_404(Solicitud, solicitud_id)
        return Rating.query.filter_by(service_id=solicitud_id).order_by(
            Rating.creado_en.desc()
        ).all()
