"""ML Ranker — Modelo LightGBM para ranking de proveedores.

Este módulo implementa el modelo de ranking usando LightGBM con
objective='lambdarank' para optimizar NDCG.

Uso:
    from app.ai.ml_ranker import MLRanker

    ranker = MLRanker()
    ranker.train(X, y, feature_names)
    scores = ranker.predict(X)
    importance = ranker.get_feature_importance()
"""

import os
import logging
from datetime import datetime

import lightgbm as lgb
import numpy as np
import joblib

logger = logging.getLogger(__name__)


class MLRanker:
    """Ranking model basado en LightGBM (Lambdarank)."""
    
    MODEL_PATH = os.environ.get("ML_MODEL_PATH", "models/ranker_lgb.pkl")
    
    def __init__(self):
        """Inicializa el ranker y carga modelo si existe."""
        self.model = None
        self.feature_names = None
        self.version = "1.0.0"
        self._load_model()
    
    def _load_model(self):
        """Carga modelo pre-entrenado desde disco."""
        if os.path.exists(self.MODEL_PATH):
            try:
                data = joblib.load(self.MODEL_PATH)
                self.model = data['model']
                self.feature_names = data['feature_names']
                self.version = data.get('version', '1.0.0')
                logger.info(f"Modelo cargado: {self.version}")
            except Exception as e:
                logger.error(f"Error cargando modelo: {e}")
                self.model = None
    
    def train(self, X: np.ndarray, y: np.ndarray, feature_names: list[str], groups: list[int] = None):
        """Entrena el modelo con datos históricos.
        
        Args:
            X: Array de features (n_samples, n_features)
            y: Labels (0/1 o scores de relevancia)
            feature_names: Lista de nombres de features
            groups: Tamaños de cada grupo/query para Lambdarank
                   (p.ej. [n1, n2, ...]). Si es None, todo se trata
                   como una sola query.
            
        Returns:
            Dict con métricas de entrenamiento
        """
        if len(X) < 100:
            raise ValueError(f"Se requieren >=100 samples, recibidos {len(X)}")
        
        if groups is None:
            groups = [len(X)]
        
        params = {
            "objective": "lambdarank",
            "metric": "ndcg",
            "num_leaves": 31,
            "min_data_in_leaf": 20,
            "learning_rate": 0.05,
            "verbose": -1,
            "num_class": 1,
        }
        
        # Crear dataset de LightGBM (Lambdarank requiere info de grupo/query)
        train_data = lgb.Dataset(
            X,
            label=y,
            group=groups,
            feature_name=feature_names
        )
        
        # Entrenar
        self.model = lgb.train(
            params,
            train_data,
            num_boost_round=100,
        )
        
        self.feature_names = feature_names
        self.version = f"1.0.0-{datetime.utcnow().strftime('%Y%m%d%H%M')}"
        
        # Guardar
        self._save_model()
        
        return {
            'version': self.version,
            'n_samples': len(X),
            'n_features': len(feature_names),
            'feature_importance': self.get_feature_importance(),
        }
    
    def _save_model(self):
        """Guarda modelo en disco."""
        os.makedirs(os.path.dirname(self.MODEL_PATH), exist_ok=True)
        joblib.dump({
            'model': self.model,
            'version': self.version,
            'feature_names': self.feature_names,
            'trained_at': datetime.utcnow()
        }, self.MODEL_PATH)
        logger.info(f"Modelo guardado: {self.MODEL_PATH}")
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predice scores de ranking.
        
        Args:
            X: Array de features (n_samples, n_features)
            
        Returns:
            Array de scores (n_samples,)
        """
        if self.model is None:
            raise ValueError("Modelo no entrenado. Ejecuta train() primero.")
        
        raw = self.model.predict(X)
        # Normalizar a [0, 1] con sigmoid para consistencia de display/umbral
        return 1.0 / (1.0 + np.exp(-raw))
    
    def get_feature_importance(self) -> dict:
        """Retorna importancia de features (gain).
        
        Returns:
            Dict {feature_name: importance}
        """
        if self.model is None or self.feature_names is None:
            return {}
        
        importance = self.model.feature_importance(importance_type='gain')
        return dict(zip(self.feature_names, importance.tolist()))
    
    def explain(self, features: dict) -> str:
        """Genera explicación legible de la predicción.
        
        Args:
            features: Dict de features extraídas
            
        Returns:
            String con top-5 features más influyentes
        """
        importance = self.get_feature_importance()
        if not importance:
            return "Modelo no entrenado"
        
        # Calcular contribución por feature
        contributions = []
        for name, value in features.items():
            if name in importance:
                contributions.append((name, abs(value * importance[name])))
        
        # Top 5
        top = sorted(contributions, key=lambda x: x[1], reverse=True)[:5]
        
        explanations = []
        for name, contrib in top:
            explanations.append(f"{name}: {features[name]:.2f}")
        
        return " | ".join(explanations)
    
    def is_trained(self) -> bool:
        """Verifica si el modelo está entrenado."""
        return self.model is not None
