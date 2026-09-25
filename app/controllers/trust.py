"""Blueprint Trust público: score de confianza de un proveedor (RF-Public).

Endpoints:
  GET /api/v1/trust/<user_id> → score de confianza público (sin JWT requerido)
"""

from flask.views import MethodView
from flask_smorest import Blueprint, abort

from app.extensions import db
from app.models.trust import TrustScore
from app.models.user import User
from app.schemas.merchant import TrustScorePublicSchema

blp = Blueprint("trust", __name__, description="Score de confianza público de proveedores")


@blp.route("/<int:user_id>")
class TrustScorePublic(MethodView):
    @blp.response(200, TrustScorePublicSchema)
    @blp.doc(summary="Obtiene el score de confianza público de un proveedor")
    def get(self, user_id):
        """Retorna el score de confianza público de un usuario proveedor.

        No requiere autenticación. Muestra: puntuación, nivel, componente
        KYC verificado, rating, contratos completados.
        """
        user = db.session.get(User, user_id)
        if not user:
            abort(404, message="Usuario no encontrado.")

        trust = TrustScore.query.filter_by(pds_id=user_id).first()
        if not trust:
            # Retornar datos por defecto sin calcular (evitar side effects en GET público)
            return {
                "user_id": user_id,
                "puntuacion": 0.0,
                "nivel": "nuevo",
                "kyc_verificado": False,
                "rating_score": 0.0,
                "contratos_completados": 0,
                "nivel_label": "Nuevo",
            }

        nivel_labels = {
            "nuevo": "Nuevo",
            "confiable": "Confiable",
            "verificado": "Verificado",
            "experto": "Experto",
        }

        return {
            "user_id": user_id,
            "puntuacion": trust.puntuacion,
            "nivel": trust.nivel,
            "kyc_verificado": trust.kyc_verificado,
            "rating_score": trust.rating_score,
            "contratos_completados": trust.contratos_completados,
            "nivel_label": nivel_labels.get(trust.nivel, "Nuevo"),
        }
