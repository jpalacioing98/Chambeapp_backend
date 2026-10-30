"""Script de entrenamiento del modelo de ranking.

Este script genera datos de entrenamiento desde contratos completados
y entrena el modelo LightGBM.

Uso:
    cd Chambeapp_backend
    python -m app.ai.train
"""

import numpy as np
import logging

from app import create_app
from app.extensions import db
from app.models.solicitud import Solicitud
from app.models.contract import Contract
from app.models.oferta import Oferta, EstadoOferta
from app.models.recommendation_log import RecommendationLog
from app.models.user import User
from app.ai.features import FeatureExtractor
from app.ai.ml_ranker import MLRanker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def generate_training_data():
    """Genera datos de entrenamiento agrupados por solicitud (query).

    Cada solicitud con historial es un grupo de Lambdarank. Los candidatos
    salen de las ofertas recibidas y de las recomendaciones registradas;
    el label es 1 si ese PDS terminó con oferta aceptada o contrato, 0 si
    fue recomendado/ofertó y no fue elegido.

    Returns:
        Tuple (X, y, groups):
            X: Array numpy (n_samples, n_features)
            y: Array numpy (n_samples,) con labels 0/1
            groups: tamaños de cada query para lambdarank
    """
    extractor = FeatureExtractor()

    solicitud_ids = [
        row[0]
        for row in db.session.query(Solicitud.id)
        .join(Oferta, Oferta.solicitud_id == Solicitud.id)
        .distinct()
        .all()
    ]
    solicitudes = (
        db.session.query(Solicitud)
        .filter(Solicitud.id.in_(solicitud_ids))
        .all()
        if solicitud_ids
        else []
    )

    X = []
    y = []
    groups = []

    for solicitud in solicitudes:
        ofertas = Oferta.query.filter_by(solicitud_id=solicitud.id).all()
        if not ofertas:
            continue

        candidate_ids = {o.pds_id for o in ofertas}
        candidate_ids.update(
            pds_id
            for (pds_id,) in db.session.query(RecommendationLog.pds_id)
            .filter(
                RecommendationLog.solicitud_id == solicitud.id,
                RecommendationLog.pds_id.isnot(None),
            )
            .distinct()
            .all()
        )

        accepted_ids = {
            o.pds_id for o in ofertas if o.estado == EstadoOferta.ACEPTADA.value
        }
        accepted_ids.update(
            proveedor_id
            for (proveedor_id,) in db.session.query(Contract.proveedor_id)
            .filter(Contract.service_id == solicitud.id)
            .distinct()
            .all()
        )

        rows = []
        labels = []
        for pds_id in candidate_ids:
            provider = db.session.get(User, pds_id)
            if provider is None:
                continue
            features = extractor.extract_for_provider(provider, solicitud)
            rows.append([features[k] for k in FeatureExtractor.FEATURE_NAMES])
            labels.append(1 if pds_id in accepted_ids else 0)

        # Lambdarank necesita al menos un positivo y un negativo por query.
        if len(rows) < 2 or len(set(labels)) < 2:
            continue

        X.extend(rows)
        y.extend(labels)
        groups.append(len(rows))

    return np.array(X), np.array(y), groups


def train_model():
    """Entrena el modelo con datos históricos."""
    app = create_app()
    
    with app.app_context():
        X, y, groups = generate_training_data()
        
        if len(X) < 100:
            logger.warning(f"⚠️ Solo {len(X)} samples. Necesarios >=100 para entrenar.")
            logger.info("💡 El modelo ML se activará cuando haya suficientes datos.")
            return None
        
        if not groups:
            logger.warning("⚠️ No hay queries con positivos y negativos; no se entrena.")
            return None

        ranker = MLRanker()
        metrics = ranker.train(
            X, y, FeatureExtractor.FEATURE_NAMES, groups=groups
        )
        
        logger.info(f"✅ Modelo entrenado: {metrics['version']}")
        logger.info(f"   Samples: {metrics['n_samples']}")
        logger.info(f"   Queries: {len(groups)}")
        logger.info(f"   Features: {metrics['n_features']}")
        logger.info(f"   Feature importance: {metrics['feature_importance']}")
        
        return metrics


if __name__ == "__main__":
    train_model()
