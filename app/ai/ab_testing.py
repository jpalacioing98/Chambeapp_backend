"""A/B Testing — Comparación ML vs Heurístico.

Este módulo gestiona la asignación de grupos A/B y el logging
de recomendaciones para validación de modelos.

Uso:
    from app.ai.ab_testing import ABTest

    # Asignar grupo
    group = ABTest.get_group(user_id=42)

    # Log de recomendación
    ABTest.log_recommendation(
        solicitud_id=42, provider_id=7, score=0.85,
        model='lightgbm_v1', group=group
    )

    # Métricas
    metrics = ABTest.get_metrics()
"""

import random
import logging
from typing import Optional

from app.extensions import db
from app.models.recommendation_log import RecommendationLog
from app.models.config import SystemConfig

logger = logging.getLogger(__name__)


class ABTest:
    """Framework para testing A/B de modelos."""
    
    # Configuración
    TRAFFIC_PERCENT = 0.5  # 50% para cada grupo por defecto
    
    @staticmethod
    def get_group(user_id: int) -> str:
        """Asigna grupo A/B deterministicamente.
        
        Args:
            user_id: ID del usuario
            
        Returns:
            'A' o 'B'
        """
        groups = SystemConfig.get_value('ab_test_groups', {})
        if user_id in groups:
            return groups[user_id]
        
        # Asignación aleatoria según porcentaje de tráfico
        group = 'A' if random.random() < ABTest.TRAFFIC_PERCENT else 'B'
        groups[user_id] = group
        SystemConfig.set_value('ab_test_groups', groups)
        
        return group
    
    @staticmethod
    def log_recommendation(solicitud_id: int, provider_id: int, 
                          score: float, model: str, group: str,
                          ranking_pos: int = None, features: dict = None,
                          version: str = None):
        """Log para análisis A/B.
        
        Args:
            solicitud_id: ID de la solicitud
            provider_id: ID del proveedor
            score: Score asignado
            model: Nombre del modelo
            group: Grupo A/B
            ranking_pos: Posición en ranking
            features: Snapshot de features
            version: Versión del modelo
        """
        RecommendationLog.log_recommendation(
            solicitud_id=solicitud_id,
            pds_id=provider_id,
            score=score,
            model=model,
            group=group,
            ranking_pos=ranking_pos,
            features=features,
            version=version
        )
    
    @staticmethod
    def get_metrics() -> dict:
        """Calcula métricas por grupo.
        
        Returns:
            Dict con métricas por grupo
        """
        return RecommendationLog.get_metrics_by_group()
    
    @staticmethod
    def reset_groups():
        """Reinicia asignación de grupos."""
        SystemConfig.set_value('ab_test_groups', {})
        logger.info("Grupos A/B reiniciados")
