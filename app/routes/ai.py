"""AI blueprint: recomendaciones / motor de match (RF-05)."""

from flask import request, jsonify
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models.user import User
from app.models.solicitud import Solicitud
from app.ai.recommender import get_recommender
from app.schemas.ai import RecommendationsSchema

blp = Blueprint("ai", __name__, description="Motor de match / recomendaciones")


@blp.route("/recommendations")
class Recommendations(MethodView):
    @blp.response(200, RecommendationsSchema)
    def get(self):
        """RF-05.1/2/4: proveedores rankeados para un servicio (transparencia)."""
        service_id = request.args.get("service_id", type=int)
        if service_id is None:
            abort(400, message="El parámetro 'service_id' es requerido.")
        solicitud = db.session.get(Solicitud, service_id)
        if solicitud is None:
            abort(404, message="Solicitud no encontrada.")
        recs = get_recommender().rank_providers_for_service(solicitud)
        return {"recommendations": recs}


@blp.route("/solicitudes-for-provider")
class SolicitudesForProvider(MethodView):
    @jwt_required()
    def get(self):
        """RF-05.3: servicios afines al perfil del proveedor autenticado.

        Retorna un ARRAY PLANO de Solicitud[] (id/categoria/descripcion/
        ubicacion/presupuesto/estado/score/explicacion) para consumo directo
        del frontend (sin envoltura).
        """
        user = db.get_or_404(User, int(get_jwt_identity()))
        profile = user.profile
        recs = get_recommender().rank_services_for_provider(profile)
        return jsonify(recs)
