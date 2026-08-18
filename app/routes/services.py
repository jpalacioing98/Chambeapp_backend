"""Services blueprint: crear/listar/detalle/estado/ratings (RF-03, RF-04)."""

from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models.user import User, Profile
from app.models.service import Service, Rating, EstadoServicio
from app.schemas.service import (
    ServiceCreateSchema,
    ServiceEstadoSchema,
    ServiceSchema,
)
from app.schemas.rating import RatingCreateSchema, RatingSchema

blp = Blueprint("services", __name__, description="Servicios y calificaciones")


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
class ServiceList(MethodView):
    @jwt_required()
    @blp.arguments(ServiceCreateSchema, location="json")
    @blp.response(201, ServiceSchema)
    def post(self, data):
        """RF-04: crea un servicio (solicitante = usuario JWT)."""
        user_id = int(get_jwt_identity())

        for campo in ("categoria", "descripcion", "ubicacion"):
            valor = data.get(campo)
            if not valor or not str(valor).strip():
                abort(400, message=f"El campo '{campo}' es requerido.")

        presupuesto = data.get("presupuesto")
        if presupuesto is not None and presupuesto < 50000:
            abort(400, message="El presupuesto mínimo es 50000.")

        service = Service(
            solicitante_id=user_id,
            categoria=data["categoria"],
            descripcion=data["descripcion"],
            ubicacion=data["ubicacion"],
            presupuesto=presupuesto,  # None => "a convenir"
            especificaciones_tecnicas=data.get("especificaciones_tecnicas"),
            estado=EstadoServicio.PUBLICADO,
        )
        service.advertencia = None
        if service.ubicacion != "Valledupar":
            service.advertencia = (
                "La ubicación está fuera de Valledupar; verifica disponibilidad "
                "del trabajador."
            )

        db.session.add(service)
        db.session.commit()
        return service

    @blp.response(200, ServiceSchema(many=True))
    def get(self):
        """RF-04: lista servicios con filtros opcionales."""
        query = Service.query
        categoria = request.args.get("categoria")
        ubicacion = request.args.get("ubicacion")
        q = request.args.get("q")
        if categoria:
            query = query.filter(Service.categoria == categoria)
        if ubicacion:
            query = query.filter(Service.ubicacion == ubicacion)
        if q:
            query = query.filter(Service.descripcion.ilike(f"%{q}%"))
        return query.order_by(Service.creado_en.desc()).all()


@blp.route("/<int:service_id>")
class ServiceDetail(MethodView):
    @blp.response(200, ServiceSchema)
    def get(self, service_id):
        """RF-04: detalle de servicio + ratings."""
        return db.get_or_404(Service, service_id)


@blp.route("/<int:service_id>/estado")
class ServiceEstado(MethodView):
    @jwt_required()
    @blp.arguments(ServiceEstadoSchema)
    @blp.response(200, ServiceSchema)
    def patch(self, data, service_id):
        """Cambia estado; solo el dueño (solicitante_id)."""
        user_id = int(get_jwt_identity())
        service = db.get_or_404(Service, service_id)
        if service.solicitante_id != user_id:
            abort(403, message="Solo el dueño puede cambiar el estado.")
        service.estado = EstadoServicio(data["estado"])
        db.session.commit()
        return service


@blp.route("/<int:service_id>/ratings")
class ServiceRatings(MethodView):
    @jwt_required()
    @blp.arguments(RatingCreateSchema)
    @blp.response(201, RatingSchema)
    def post(self, data, service_id):
        """RF-03: crea Rating. Requiere servicio completado y autor único."""
        user_id = int(get_jwt_identity())
        service = db.get_or_404(Service, service_id)

        if service.estado != EstadoServicio.COMPLETADO:
            abort(409, message="servicio no completado")

        if Rating.query.filter_by(service_id=service_id, autor_id=user_id).first():
            abort(409, message="Ya calificaste este servicio.")

        calificado_id = data["calificado_id"]
        if not db.session.get(User, calificado_id):
            abort(404, message="El usuario calificado no existe.")

        rating = Rating(
            service_id=service_id,
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
    def get(self, service_id):
        """RF-03: lista ratings del servicio."""
        db.get_or_404(Service, service_id)
        return Rating.query.filter_by(service_id=service_id).order_by(
            Rating.creado_en.desc()
        ).all()
