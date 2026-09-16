"""AI blueprint: recomendaciones / motor de match (RF-05)."""

import logging

from flask import request, jsonify
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models.user import User
from app.models.solicitud import Solicitud
from app.ai.recommender import get_recommender
from app.ai.ab_testing import ABTest
from app.schemas.ai import RecommendationsSchema

blp = Blueprint("ai", __name__, description="Motor de match / recomendaciones")
logger = logging.getLogger(__name__)


def _get_recommender_model(recommender) -> str:
    """Infer model name from recommender type for A/B logging."""
    return type(recommender).__name__


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
        recommender = get_recommender()
        recs = recommender.rank_providers_for_service(solicitud)

        # ── A/B: assign group + log each recommendation ──────────────
        try:
            ab_group = ABTest.get_group(solicitud.solicitante_id)
            model_name = _get_recommender_model(recommender)
            for i, rec in enumerate(recs):
                ABTest.log_recommendation(
                    solicitud_id=solicitud.id,
                    provider_id=rec["user_id"],
                    score=rec["score"],
                    model=model_name,
                    group=ab_group,
                    ranking_pos=i + 1,
                )
                rec["ab_group"] = ab_group
        except Exception:
            logger.exception("A/B logging failed for recommendations")

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
        recommender = get_recommender()
        recs = recommender.rank_services_for_provider(profile)

        # ── A/B: assign group + log each recommendation ──────────────
        try:
            ab_group = ABTest.get_group(user.id)
            model_name = _get_recommender_model(recommender)
            for i, rec in enumerate(recs):
                ABTest.log_recommendation(
                    solicitud_id=rec["id"],
                    provider_id=user.id,
                    score=rec["score"],
                    model=model_name,
                    group=ab_group,
                    ranking_pos=i + 1,
                )
                rec["ab_group"] = ab_group
        except Exception:
            logger.exception("A/B logging failed for solicitudes-for-provider")

        return jsonify(recs)
