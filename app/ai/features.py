"""Feature Pipeline — Extracción y transformación de features para ML.

Este módulo extrae 22 features para el modelo de ranking de proveedores,
combinando señales geoespaciales, de confianza, historial y negocio.

Uso:
    from app.ai.features import FeatureExtractor

    extractor = FeatureExtractor()
    features = extractor.extract_for_provider(provider, solicitud)
    X = extractor.extract_batch(providers, solicitud)
"""

import numpy as np
from datetime import datetime, timedelta
from typing import Optional

from app.extensions import db
from app.models.user import User, Profile
from app.models.solicitud import Solicitud
from app.models.trust import TrustScore
from app.ai.geo import haversine_km


class FeatureExtractor:
    """Extrae features para el modelo de ranking."""
    
    # Lista de nombres de features (orden importa para el modelo)
    FEATURE_NAMES = [
        # Geoespaciales (2)
        'distance_km', 'zona_match',
        
        # Confianza (5)
        'trust_score', 'kyc_verificado', 'portfolio_calidad',
        'badges_count', 'contratos_completados',
        
        # Historial (5)
        'rating_avg', 'rating_count', 'tasa_aceptacion',
        'tiempo_respuesta_promedio', 'ultima_actividad_dias',
        
        # Negocio (4)
        'category_match', 'price_match', 'saturacion_pen', 'disponibilidad',
        
        # Rotación (3)
        'bandit_arm_value', 'fresh_provider_bonus', 'exploration_slot',
        
        # Metadata (3)
        'hour_of_day', 'day_of_week', 'is_urgent',
    ]
    
    def __init__(self):
        """Inicializa el extractor."""
        self.n_features = len(self.FEATURE_NAMES)
    
    def extract_for_provider(self, provider: User, solicitud: Solicitud) -> dict:
        """Extrae features para un proveedor dado una solicitud.
        
        Args:
            provider: Usuario proveedor (User)
            solicitud: Solicitud de servicio (Solicitud)
            
        Returns:
            Dict con 22 features
            
        Example:
            >>> extractor = FeatureExtractor()
            >>> features = extractor.extract_for_provider(provider, solicitud)
            >>> print(features['distance_km'], features['trust_score'])
        """
        profile = provider.profile
        
        # Geoespaciales
        distance = self._calc_distance(profile, solicitud)
        zona_match = 1.0 if self._mismas_zonas(profile, solicitud) else 0.0
        
        # Confianza
        trust = TrustScore.query.filter_by(pds_id=provider.id).first()
        trust_score = trust.puntuacion if trust else 0.0
        kyc = 1.0 if trust and trust.kyc_verificado else 0.0
        portfolio = trust.portfolio_calidad if trust else 0.0
        badges = self._count_badges(provider.id)
        contratos = self._count_contracts(provider.id)
        
        # Historial
        rating = (profile.calificacion_promedio or 0) / 5.0
        rating_count = self._count_ratings(provider.id)
        tasa_acept = self._calc_tasa_aceptacion(provider.id)
        tiempo_resp = self._calc_tiempo_respuesta(provider.id)
        ultima_act = self._dias_desde_ultima_actividad(provider.id)
        
        # Negocio
        category_match = 1.0 if self._categoria_match(solicitud.categoria, profile) else 0.0
        price_match = self._calc_price_match(solicitud, profile)
        saturacion = self._calc_saturacion(provider.id)
        disponibilidad = self._check_disponibilidad(provider.id)
        
        # Rotación
        bandit_val = self._get_bandit_value(provider.id, solicitud.categoria)
        fresh = 1.0 if self._is_fresh(provider.id) else 0.0
        exploration = self._get_exploration_slot(provider.id)
        
        # Metadata
        now = datetime.utcnow()
        hour = now.hour / 24.0
        day = now.weekday() / 7.0
        urgent = 1.0 if solicitud.urgencia == 'alta' else 0.0
        
        return {
            'distance_km': distance,
            'zona_match': zona_match,
            'trust_score': trust_score,
            'kyc_verificado': kyc,
            'portfolio_calidad': portfolio,
            'badges_count': badges,
            'contratos_completados': contratos,
            'rating_avg': rating,
            'rating_count': rating_count,
            'tasa_aceptacion': tasa_acept,
            'tiempo_respuesta_promedio': tiempo_resp,
            'ultima_actividad_dias': ultima_act,
            'category_match': category_match,
            'price_match': price_match,
            'saturacion_pen': saturacion,
            'disponibilidad': disponibilidad,
            'bandit_arm_value': bandit_val,
            'fresh_provider_bonus': fresh,
            'exploration_slot': exploration,
            'hour_of_day': hour,
            'day_of_week': day,
            'is_urgent': urgent,
        }
    
    def extract_batch(self, providers: list[User], solicitud: Solicitud) -> np.ndarray:
        """Extrae features para múltiples proveedores.
        
        Args:
            providers: Lista de usuarios proveedor
            solicitud: Solicitud de servicio
            
        Returns:
            Array numpy de shape (n_providers, n_features)
        """
        features = []
        for p in providers:
            f = self.extract_for_provider(p, solicitud)
            features.append([f[k] for k in self.FEATURE_NAMES])
        return np.array(features)
    
    # --- Helpers privados ---
    
    def _calc_distance(self, profile, solicitud):
        """Calcula distancia entre proveedor y solicitud."""
        if profile.latitud and solicitud.latitud:
            return haversine_km(
                profile.latitud, profile.longitud,
                solicitud.latitud, solicitud.longitud
            )
        return 999.0  # Default lejano
    
    def _mismas_zonas(self, profile, solicitud):
        """Verifica si proveedor y solicitud están en la misma zona."""
        return (profile.zona or '').lower() == (solicitud.ubicacion or '').lower()
    
    def _categoria_match(self, categoria, profile):
        """Verifica match de categoría."""
        cats = list(profile.categorias or [])
        habs = list(profile.habilidades or [])
        return categoria in cats or categoria in habs
    
    def _count_badges(self, user_id):
        """Cuenta badges activos del usuario."""
        from app.models.badges import Badge
        return Badge.query.filter_by(usuario_id=user_id, activo=True).count()
    
    def _count_contracts(self, user_id):
        """Cuenta contratos completados."""
        from app.models.contract import Contract
        return Contract.query.filter(
            (Contract.proveedor_id == user_id) | (Contract.solicitante_id == user_id),
            Contract.estado == 'completado'
        ).count()
    
    def _count_ratings(self, user_id):
        """Cuenta ratings recibidos."""
        from app.models.solicitud import Rating
        return Rating.query.filter_by(calificado_id=user_id).count()
    
    def _calc_tasa_aceptacion(self, user_id):
        """Calcula tasa de aceptación de ofertas."""
        from app.models.oferta import Oferta
        total = Oferta.query.filter_by(pds_id=user_id).count()
        aceptadas = Oferta.query.filter_by(pds_id=user_id, estado='aceptada').count()
        return aceptadas / total if total > 0 else 0.0
    
    def _calc_tiempo_respuesta(self, user_id):
        """Calcula tiempo promedio de respuesta (segundos)."""
        # Placeholder — usar created_at de ofertas
        return 3600.0  # 1 hora default
    
    def _dias_desde_ultima_actividad(self, user_id):
        """Días desde última actividad."""
        user = User.query.get(user_id)
        if user and user.last_login:
            return (datetime.utcnow() - user.last_login).days
        return 30  # Default
    
    def _calc_price_match(self, solicitud, profile):
        """Calcula match de precio (0-1)."""
        if not solicitud.presupuesto:
            return 0.5
        # Placeholder — comparar con precio sugerido
        return 0.5
    
    def _calc_saturacion(self, user_id):
        """Calcula penalización por saturación (0-1)."""
        from app.models.contract import Contract
        activos = Contract.query.filter_by(
            proveedor_id=user_id, estado='activo'
        ).count()
        return min(activos / 10, 1.0)  # Tope 10
    
    def _check_disponibilidad(self, user_id):
        """Verifica disponibilidad (0-1)."""
        # Placeholder — verificar horarios
        return 1.0
    
    def _get_bandit_value(self, user_id, categoria):
        """Obtiene valor del bandit para la categoría."""
        from app.ai.bandit import ThompsonBandit
        
        try:
            bandit = ThompsonBandit()
            return bandit.get_arm_value(categoria)
        except Exception:
            return 0.5
    
    def _is_fresh(self, user_id):
        """Verifica si es proveedor nuevo (<=30 días)."""
        user = User.query.get(user_id)
        if user and user.fecha_registro:
            dias = (datetime.utcnow() - user.fecha_registro).days
            return dias <= 30
        return False
    
    def _get_exploration_slot(self, user_id):
        """Obtiene slot de exploración para no-verificados."""
        profile = Profile.query.filter_by(user_id=user_id).first()
        if profile and not profile.verificado:
            return 0.1  # 10% de slots
        return 0.0
