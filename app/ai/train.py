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
from app.models.solicitud import Solicitud, EstadoSolicitud
from app.models.contract import Contract
from app.models.user import User
from app.ai.features import FeatureExtractor
from app.ai.ml_ranker import MLRanker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def generate_training_data():
    """Genera datos de entrenamiento desde contratos completados.
    
    Returns:
        Tuple (X, y) donde:
            X: Array numpy (n_samples, n_features)
            y: Array numpy (n_samples,) con labels 0/1
    """
    contracts = Contract.query.filter_by(estado='completado').all()
    
    X = []
    y = []
    extractor = FeatureExtractor()
    
    for contract in contracts:
        solicitud = Solicitud.query.get(contract.service_id)
        provider = User.query.get(contract.proveedor_id)
        
        if not solicitud or not provider:
            continue
        
        # Extraer features
        features = extractor.extract_for_provider(provider, solicitud)
        X.append([features[k] for k in FeatureExtractor.FEATURE_NAMES])
        
        # Label: 1 si fue aceptado, 0 si fue rechazado
        # (simplificado — en producción usar clicks/conversiones)
        y.append(1 if contract.estado == 'completado' else 0)
    
    return np.array(X), np.array(y)


def train_model():
    """Entrena el modelo con datos históricos."""
    app = create_app()
    
    with app.app_context():
        X, y = generate_training_data()
        
        if len(X) < 100:
            logger.warning(f"⚠️ Solo {len(X)} samples. Necesarios >=100 para entrenar.")
            logger.info("💡 El modelo ML se activará cuando haya suficientes datos.")
            return None
        
        ranker = MLRanker()
        metrics = ranker.train(X, y, FeatureExtractor.FEATURE_NAMES)
        
        logger.info(f"✅ Modelo entrenado: {metrics['version']}")
        logger.info(f"   Samples: {metrics['n_samples']}")
        logger.info(f"   Features: {metrics['n_features']}")
        logger.info(f"   Feature importance: {metrics['feature_importance']}")
        
        return metrics


if __name__ == "__main__":
    train_model()
