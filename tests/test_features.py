"""Tests unitarios para FeatureExtractor — Pipeline de features.

Estos tests verifican:
1. Número correcto de features (22)
2. Extracción para un proveedor
3. Extracción en batch
4. Helpers privados (distancia, categoría, etc.)
"""

import pytest
from unittest.mock import patch, MagicMock


class TestFeatureExtractor:
    """Tests para FeatureExtractor."""
    
    def test_n_features(self):
        """Debe tener exactamente 22 features."""
        from app.ai.features import FeatureExtractor
        
        extractor = FeatureExtractor()
        assert extractor.n_features == 22
        assert len(extractor.FEATURE_NAMES) == 22
    
    def test_feature_names_unique(self):
        """Los nombres de features deben ser únicos."""
        from app.ai.features import FeatureExtractor
        
        names = FeatureExtractor.FEATURE_NAMES
        assert len(names) == len(set(names))
    
    def test_extract_for_provider_returns_dict(self):
        """extract_for_provider debe retornar dict con 22 keys."""
        from app.ai.features import FeatureExtractor
        
        extractor = FeatureExtractor()
        
        # Mock provider y solicitud
        provider = MagicMock()
        provider.id = 42
        provider.profile = MagicMock()
        provider.profile.latitud = 10.4806
        provider.profile.longitud = -73.2495
        provider.profile.zona = 'Valledupar'
        provider.profile.calificacion_promedio = 4.5
        provider.profile.categorias = ['plomeria']
        provider.profile.habilidades = ['electricidad']
        provider.profile.verificado = True
        
        solicitud = MagicMock()
        solicitud.categoria = 'plomeria'
        solicitud.latitud = 10.4806
        solicitud.longitud = -73.2495
        solicitud.ubicacion = 'Valledupar'
        solicitud.presupuesto = 100000
        solicitud.urgencia = 'alta'
        
        # Mock TrustScore
        trust_mock = MagicMock()
        trust_mock.puntuacion = 0.8
        trust_mock.kyc_verificado = True
        trust_mock.portfolio_calidad = 0.6
        
        with patch('app.ai.features.TrustScore') as mock_trust:
            mock_trust.query.filter_by.return_value.first.return_value = trust_mock
            
            with patch.object(extractor, '_count_badges', return_value=3):
                with patch.object(extractor, '_count_contracts', return_value=10):
                    with patch.object(extractor, '_count_ratings', return_value=5):
                        with patch.object(extractor, '_calc_tasa_aceptacion', return_value=0.8):
                            with patch.object(extractor, '_calc_tiempo_respuesta', return_value=1800.0):
                                with patch.object(extractor, '_dias_desde_ultima_actividad', return_value=5):
                                    with patch.object(extractor, '_calc_saturacion', return_value=0.3):
                                        with patch.object(extractor, '_check_disponibilidad', return_value=1.0):
                                            with patch.object(extractor, '_get_bandit_value', return_value=0.5):
                                                with patch.object(extractor, '_is_fresh', return_value=True):
                                                    with patch.object(extractor, '_get_exploration_slot', return_value=0.0):
                                                        features = extractor.extract_for_provider(provider, solicitud)
            
            assert isinstance(features, dict)
            assert len(features) == 22
            assert features['distance_km'] == 0.0  # Misma ubicación
            assert features['zona_match'] == 1.0
            assert features['category_match'] == 1.0
            assert features['trust_score'] == 0.8
            assert features['kyc_verificado'] == 1.0
            assert features['is_urgent'] == 1.0
    
    def test_extract_batch(self):
        """extract_batch debe retornar array numpy de shape (n, 22)."""
        import numpy as np
        from app.ai.features import FeatureExtractor
        
        extractor = FeatureExtractor()
        
        # Mock providers
        providers = [MagicMock() for _ in range(3)]
        for i, p in enumerate(providers):
            p.id = i
            p.profile = MagicMock()
            p.profile.latitud = 10.4806
            p.profile.longitud = -73.2495
            p.profile.zona = 'Valledupar'
            p.profile.calificacion_promedio = 4.0
            p.profile.categorias = ['plomeria']
            p.profile.habilidades = []
            p.profile.verificado = False
        
        solicitud = MagicMock()
        solicitud.categoria = 'plomeria'
        solicitud.latitud = 10.4806
        solicitud.longitud = -73.2495
        solicitud.ubicacion = 'Valledupar'
        solicitud.presupuesto = 100000
        solicitud.urgencia = 'baja'
        
        with patch('app.ai.features.TrustScore') as mock_trust:
            mock_trust.query.filter_by.return_value.first.return_value = None
            
            with patch.object(extractor, '_count_badges', return_value=0):
                with patch.object(extractor, '_count_contracts', return_value=0):
                    with patch.object(extractor, '_count_ratings', return_value=0):
                        with patch.object(extractor, '_calc_tasa_aceptacion', return_value=0.0):
                            with patch.object(extractor, '_calc_tiempo_respuesta', return_value=3600.0):
                                with patch.object(extractor, '_dias_desde_ultima_actividad', return_value=30):
                                    with patch.object(extractor, '_calc_saturacion', return_value=0.0):
                                        with patch.object(extractor, '_check_disponibilidad', return_value=1.0):
                                            with patch.object(extractor, '_get_bandit_value', return_value=0.5):
                                                with patch.object(extractor, '_is_fresh', return_value=False):
                                                    with patch.object(extractor, '_get_exploration_slot', return_value=0.1):
                                                        X = extractor.extract_batch(providers, solicitud)
            
            assert isinstance(X, np.ndarray)
            assert X.shape == (3, 22)
    
    def test_categoria_match(self):
        """_categoria_match debe verificar categorías y habilidades."""
        from app.ai.features import FeatureExtractor
        
        extractor = FeatureExtractor()
        
        profile = MagicMock()
        profile.categorias = ['plomeria', 'electricidad']
        profile.habilidades = ['pintura']
        
        assert extractor._categoria_match('plomeria', profile) is True
        assert extractor._categoria_match('electricidad', profile) is True
        assert extractor._categoria_match('pintura', profile) is True
        assert extractor._categoria_match('carpinteria', profile) is False
    
    def test_calc_distance_same_point(self):
        """_calc_distance debe retornar 0 para mismo punto."""
        from app.ai.features import FeatureExtractor
        
        extractor = FeatureExtractor()
        
        profile = MagicMock()
        profile.latitud = 10.4806
        profile.longitud = -73.2495
        
        solicitud = MagicMock()
        solicitud.latitud = 10.4806
        solicitud.longitud = -73.2495
        
        assert extractor._calc_distance(profile, solicitud) == 0.0
    
    def test_calc_distance_no_coords(self):
        """_calc_distance debe retornar 999 si falta coordenadas."""
        from app.ai.features import FeatureExtractor
        
        extractor = FeatureExtractor()
        
        profile = MagicMock()
        profile.latitud = None
        profile.longitud = None
        
        solicitud = MagicMock()
        solicitud.latitud = 10.4806
        solicitud.longitud = -73.2495
        
        assert extractor._calc_distance(profile, solicitud) == 999.0
    
    def test_mismas_zonas(self):
        """_mismas_zonas debe comparar zonas."""
        from app.ai.features import FeatureExtractor
        
        extractor = FeatureExtractor()
        
        profile = MagicMock()
        profile.zona = 'Valledupar'
        
        solicitud = MagicMock()
        solicitud.ubicacion = 'Valledupar'
        
        assert extractor._mismas_zonas(profile, solicitud) is True
        
        solicitud.ubicacion = 'Bogota'
        assert extractor._mismas_zonas(profile, solicitud) is False
    
    def test_is_fresh(self):
        """_is_fresh debe retornar True para proveedores nuevos."""
        from app.ai.features import FeatureExtractor
        from datetime import datetime, timedelta
        from app import create_app
        from app.extensions import db
        from app.models.user import User
        
        extractor = FeatureExtractor()
        
        user = MagicMock()
        user.fecha_registro = datetime.utcnow() - timedelta(days=10)
        
        app = create_app("app.config.TestingConfig")
        with app.app_context():
            db.create_all()
            mock_query = MagicMock()
            mock_query.get.return_value = user
            with patch.object(User, 'query', mock_query):
                assert extractor._is_fresh(42) is True
            
            user.fecha_registro = datetime.utcnow() - timedelta(days=60)
            with patch.object(User, 'query', mock_query):
                assert extractor._is_fresh(42) is False
            db.drop_all()
    
    def test_get_exploration_slot(self):
        """_get_exploration_slot debe retornar 0.1 para no-verificados."""
        from app.ai.features import FeatureExtractor
        from app import create_app
        from app.extensions import db
        from app.models.user import Profile
        
        extractor = FeatureExtractor()
        
        app = create_app("app.config.TestingConfig")
        with app.app_context():
            db.create_all()
            # No verificado
            profile_unverified = MagicMock()
            profile_unverified.verificado = False
            
            mock_query = MagicMock()
            mock_query.filter_by.return_value.first.return_value = profile_unverified
            with patch.object(Profile, 'query', mock_query):
                assert extractor._get_exploration_slot(42) == 0.1
            
            # Verificado
            profile_verified = MagicMock()
            profile_verified.verificado = True
            
            mock_query2 = MagicMock()
            mock_query2.filter_by.return_value.first.return_value = profile_verified
            with patch.object(Profile, 'query', mock_query2):
                assert extractor._get_exploration_slot(42) == 0.0
            db.drop_all()
