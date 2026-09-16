"""TrustScore Service — Lógica de negocio para scores de confianza.

Este servicio gestiona el cálculo, consulta y actualización de scores
de confianza para proveedores (PDS).

Uso:
    from app.services.trust import TrustService

    # Obtener score de un proveedor
    trust_data = TrustService.get_trust(pds_id=42)

    # Recalcular score
    TrustService.recalculate(pds_id=42)

    # Recalcular todos los scores (tarea Celery)
    TrustService.recalculate_all()

    # Obtener ranking de proveedores por confianza
    top_providers = TrustService.get_top_trusted(n=10)
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from app.extensions import db, cache
from app.models.trust import TrustScore
from app.models.user import User, RolUsuario

logger = logging.getLogger(__name__)


class TrustService:
    """Servicio de gestión de scores de confianza."""
    
    # Cache TTL: 1 hora
    CACHE_TTL = 3600
    
    @staticmethod
    @cache.memoize(timeout=CACHE_TTL)
    def get_trust(pds_id: int) -> dict:
        """Obtiene el score de confianza de un proveedor.
        
        Args:
            pds_id: ID del usuario proveedor
            
        Returns:
            Dict con score, nivel y componentes
            
        Example:
            >>> data = TrustService.get_trust(pds_id=42)
            >>> print(data['puntuacion'], data['nivel'])
            0.75 verificado
        """
        trust = TrustScore.get_or_create(pds_id=pds_id)
        
        # Recalcular si tiene más de 1 hora sin actualizar
        if trust.calculado_en:
            tiempo_transcurrido = datetime.utcnow() - trust.calculado_en
            if tiempo_transcurrido > timedelta(hours=1):
                trust.calcular()
        else:
            trust.calcular()
        
        return {
            'pds_id': trust.pds_id,
            'puntuacion': trust.puntuacion,
            'nivel': trust.nivel,
            'componentes': {
                'kyc_verificado': trust.kyc_verificado,
                'portfolio_calidad': trust.portfolio_calidad,
                'rating_score': trust.rating_score,
                'contratos_completados': trust.contratos_completados,
                'referidos_count': trust.referidos_count,
            },
            'calculado_en': trust.calculado_en.isoformat() if trust.calculado_en else None,
            'version': trust.version,
        }
    
    @staticmethod
    def recalculate(pds_id: int) -> dict:
        """Recalcula el score de confianza de un proveedor.
        
        Args:
            pds_id: ID del usuario proveedor
            
        Returns:
            Dict con el nuevo score
        """
        trust = TrustScore.get_or_create(pds_id=pds_id)
        score = trust.calcular()
        
        # Limpiar cache
        cache.delete_memoized(TrustService.get_trust, pds_id)
        
        logger.info(f"TrustScore recalculado: pds_id={pds_id}, score={score}, nivel={trust.nivel}")
        
        return {
            'pds_id': pds_id,
            'puntuacion': score,
            'nivel': trust.nivel,
            'version': trust.version,
        }
    
    @staticmethod
    def recalculate_all() -> int:
        """Recalcula todos los scores de confianza (tarea Celery).
        
        Returns:
            Número de scores recalculados
        """
        count = TrustScore.recalculate_all()
        logger.info(f"TrustScore: {count} scores recalculados")
        return count
    
    @staticmethod
    def get_top_trusted(n: int = 10, min_score: float = 0.5) -> list[dict]:
        """Obtiene los N proveedores más confiables.
        
        Args:
            n: Número de proveedores a retornar
            min_score: Score mínimo requerido
            
        Returns:
            Lista de proveedores con su score
            
        Example:
            >>> top = TrustService.get_top_trusted(n=5, min_score=0.6)
            >>> for p in top:
            ...     print(f"{p['email']}: {p['puntuacion']}")
        """
        trusts = TrustScore.query.filter(
            TrustScore.puntuacion >= min_score
        ).order_by(
            TrustScore.puntuacion.desc()
        ).limit(n).all()
        
        results = []
        for trust in trusts:
            user = User.query.get(trust.pds_id)
            if user:
                results.append({
                    'pds_id': trust.pds_id,
                    'email': user.email,
                    'nombre': user.nombre,
                    'puntuacion': trust.puntuacion,
                    'nivel': trust.nivel,
                })
        
        return results
    
    @staticmethod
    def get_trust_distribution() -> dict:
        """Obtiene la distribución de niveles de confianza.
        
        Returns:
            Dict con conteo por nivel
            
        Example:
            >>> dist = TrustService.get_trust_distribution()
            >>> print(dist)
            {'nuevo': 45, 'confiable': 30, 'verificado': 20, 'experto': 5}
        """
        from sqlalchemy import func
        
        distribution = db.session.query(
            TrustScore.nivel,
            func.count(TrustScore.id)
        ).group_by(TrustScore.nivel).all()
        
        return {nivel: count for nivel, count in distribution}
    
    @staticmethod
    def invalidate_cache(pds_id: int):
        """Invalida el cache de un proveedor.
        
        Args:
            pds_id: ID del usuario proveedor
        """
        cache.delete_memoized(TrustService.get_trust, pds_id)
