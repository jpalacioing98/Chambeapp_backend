"""AI Metrics — Dashboard de métricas del modelo ML.

Este blueprint expone métricas del modelo de ranking y resultados
de A/B testing para monitoreo y validación.

Endpoints:
    GET /api/v1/ai/metrics  → Métricas del modelo y A/B test
"""

from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required

from app.ai.ab_testing import ABTest
from app.ai.ml_ranker import MLRanker
from app.models.config import FeatureFlag

blp = Blueprint("ai_metrics", __name__, description="Métricas del modelo ML")


@blp.route("/metrics")
class AIMetrics(MethodView):
    @jwt_required()
    @blp.doc(security=[{"Bearer": []}], summary="Métricas del modelo ML")
    def get(self):
        """Retorna métricas del modelo y A/B test.
        
        Returns:
            Dict con métricas de modelo y A/B test
        """
        # Verificar que el usuario es admin/superadmin
        from app.models.user import User, RolUsuario
        from flask_jwt_extended import get_jwt_identity
        
        user = User.query.get(int(get_jwt_identity()))
        if user.rol not in (RolUsuario.ADMIN, RolUsuario.SUPERADMIN):
            abort(403, message="Acceso denegado")
        
        # Métricas del modelo
        ranker = MLRanker()
        model_metrics = {
            'version': ranker.version,
            'is_trained': ranker.is_trained(),
            'feature_importance': ranker.get_feature_importance(),
            'n_features': len(ranker.feature_names) if ranker.feature_names else 0,
        }
        
        # Estado de feature flags
        flags = {}
        for flag in FeatureFlag.query.all():
            flags[flag.key] = flag.enabled
        
        # Métricas A/B test
        ab_metrics = ABTest.get_metrics()
        
        return {
            'model': model_metrics,
            'feature_flags': flags,
            'ab_test': ab_metrics,
            'timestamp': __import__('datetime').datetime.utcnow().isoformat()
        }


@blp.route("/metrics/feature-importance")
class FeatureImportance(MethodView):
    @jwt_required()
    @blp.doc(security=[{"Bearer": []}], summary="Importancia de features")
    def get(self):
        """Retorna importancia de features del modelo."""
        from app.models.user import User, RolUsuario
        from flask_jwt_extended import get_jwt_identity
        
        user = User.query.get(int(get_jwt_identity()))
        if user.rol not in (RolUsuario.ADMIN, RolUsuario.SUPERADMIN):
            abort(403, message="Acceso denegado")
        
        ranker = MLRanker()
        return {
            'version': ranker.version,
            'feature_importance': ranker.get_feature_importance()
        }
