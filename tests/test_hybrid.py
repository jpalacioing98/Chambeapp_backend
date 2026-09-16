"""Tests unitarios para HybridRecommender y ShadowRecommender.

Estos tests verifican:
1. HybridRecommender usa geoespacial + ML
2. Fallback a heurístico si ML falla
3. ShadowRecommender loguea ML pero usa heurístico
4. Factory retorna implementación correcta según flags
"""

import sys
import pytest
from unittest.mock import patch, MagicMock

# Create a mock ml_ranker module ONLY if lightgbm is not installed.
# When lightgbm is available the real app.ai.ml_ranker module is imported,
# and injecting a MagicMock here would leak into test_ml_ranker.py.
try:
    import lightgbm  # noqa: F401
    HAS_LIGHTGBM = True
except ImportError:
    HAS_LIGHTGBM = False

if not HAS_LIGHTGBM:
    _mock_ml_ranker = MagicMock()
    _mock_ml_ranker.MLRanker = MagicMock
    sys.modules.setdefault('app.ai.ml_ranker', _mock_ml_ranker)


class TestHybridRecommender:
    """Tests para HybridRecommender."""

    def test_init(self):
        """Init debe crear extractor, ranker y heuristic."""
        from app.ai.recommender import HybridRecommender
        
        with patch('app.ai.features.FeatureExtractor'):
            with patch('app.ai.ml_ranker.MLRanker'):
                with patch('app.ai.geo.find_nearby_providers'):
                    rec = HybridRecommender()
                    assert rec.extractor is not None
                    assert rec.ranker is not None
                    assert rec.heuristic is not None

    def test_rank_providers_fallback_no_candidates(self):
        """Debe hacer fallback a heurístico si no hay candidatos."""
        from app.ai.recommender import HybridRecommender
        
        with patch('app.ai.features.FeatureExtractor'):
            with patch('app.ai.ml_ranker.MLRanker'):
                with patch('app.ai.geo.find_nearby_providers', return_value=[]):
                    rec = HybridRecommender()
                    
                    # Mock heuristic
                    mock_heuristic = MagicMock()
                    mock_heuristic.rank_providers_for_service.return_value = [{'user_id': 1}]
                    rec.heuristic = mock_heuristic
                    
                    service = MagicMock()
                    service.latitud = 10.4
                    service.longitud = -73.2
                    
                    result = rec.rank_providers_for_service(service)
                    assert result == [{'user_id': 1}]
                    mock_heuristic.rank_providers_for_service.assert_called_once()

    def test_rank_providers_ml_success(self):
        """Debe usar ML si hay candidatos y modelo entrenado."""
        from app.ai.recommender import HybridRecommender
        import numpy as np
        
        with patch('app.ai.features.FeatureExtractor') as mock_ext:
            with patch('app.ai.ml_ranker.MLRanker') as mock_ranker:
                with patch('app.ai.geo.find_nearby_providers') as mock_find:
                    # Setup
                    mock_find.return_value = [MagicMock(id=1, email='p1@test.com')]
                    
                    extractor = mock_ext.return_value
                    extractor.extract_batch.return_value = np.array([[0.5] * 22])
                    extractor.extract_for_provider.return_value = {'distance_km': 1.0}
                    
                    ranker = mock_ranker.return_value
                    ranker.predict.return_value = np.array([0.8])
                    ranker.explain.return_value = "test"
                    ranker.version = "1.0.0"
                    
                    rec = HybridRecommender()
                    rec.ranker = ranker
                    rec.extractor = extractor
                    
                    service = MagicMock()
                    service.latitud = 10.4
                    service.longitud = -73.2
                    
                    result = rec.rank_providers_for_service(service)
                    
                    assert len(result) == 1
                    assert result[0]['score'] == 0.8
                    assert result[0]['model_version'] == "1.0.0"

    def test_rank_providers_ml_failure_fallback(self):
        """Debe hacer fallback a heurístico si ML falla."""
        from app.ai.recommender import HybridRecommender
        import numpy as np
        
        with patch('app.ai.features.FeatureExtractor') as mock_ext:
            with patch('app.ai.ml_ranker.MLRanker') as mock_ranker:
                with patch('app.ai.geo.find_nearby_providers') as mock_find:
                    mock_find.return_value = [MagicMock(id=1, email='p1@test.com')]
                    
                    extractor = mock_ext.return_value
                    extractor.extract_batch.return_value = np.array([[0.5] * 22])
                    
                    ranker = mock_ranker.return_value
                    ranker.predict.side_effect = Exception("ML error")
                    
                    rec = HybridRecommender()
                    rec.ranker = ranker
                    rec.extractor = extractor
                    
                    # Mock heuristic
                    mock_heuristic = MagicMock()
                    mock_heuristic.rank_providers_for_service.return_value = [{'user_id': 1}]
                    rec.heuristic = mock_heuristic
                    
                    service = MagicMock()
                    service.latitud = 10.4
                    service.longitud = -73.2
                    
                    result = rec.rank_providers_for_service(service)
                    assert result == [{'user_id': 1}]


class TestShadowRecommender:
    """Tests para ShadowRecommender."""

    def test_init(self):
        """Init debe crear heuristic y hybrid."""
        from app.ai.recommender import ShadowRecommender
        
        with patch('app.ai.recommender.HeuristicRecommender'):
            with patch('app.ai.recommender.HybridRecommender'):
                rec = ShadowRecommender()
                assert rec.heuristic is not None
                assert rec.hybrid is not None

    def test_rank_providers_logs_ml_uses_heuristic(self):
        """Debe loguear ML pero retornar heurístico."""
        from app.ai.recommender import ShadowRecommender
        
        with patch('app.ai.recommender.HeuristicRecommender'):
            with patch('app.ai.recommender.HybridRecommender'):
                rec = ShadowRecommender()
                
                # Mock hybrid
                mock_hybrid = MagicMock()
                mock_hybrid.rank_providers_for_service.return_value = [
                    {'email': 'ml@test.com', 'score': 0.9}
                ]
                rec.hybrid = mock_hybrid
                
                # Mock heuristic
                mock_heuristic = MagicMock()
                mock_heuristic.rank_providers_for_service.return_value = [
                    {'user_id': 1, 'email': 'heur@test.com', 'score': 0.7}
                ]
                rec.heuristic = mock_heuristic
                
                service = MagicMock()
                service.id = 42
                
                result = rec.rank_providers_for_service(service)
                
                # Debe retornar heurístico
                assert result[0]['email'] == 'heur@test.com'
                # Debe haber llamado hybrid para log
                mock_hybrid.rank_providers_for_service.assert_called_once()


class TestFactory:
    """Tests para get_recommender factory."""

    def test_returns_heuristic_by_default(self):
        """Debe retornar HeuristicRecommender por defecto."""
        from app.ai.recommender import get_recommender, HeuristicRecommender
        
        with patch('app.models.config.FeatureFlag') as mock_flag:
            # No flags enabled
            mock_flag.query.filter_by.return_value.first.return_value = None
            
            rec = get_recommender()
            assert isinstance(rec, HeuristicRecommender)

    def test_returns_hybrid_when_ml_enabled(self):
        """Debe retornar HybridRecommender si ml_ranking_enabled=True."""
        from app.ai.recommender import get_recommender
        
        with patch('app.models.config.FeatureFlag') as mock_flag:
            def side_effect(key, enabled):
                mock = MagicMock()
                if key == 'ml_ranking_enabled':
                    mock.first.return_value = MagicMock()
                else:
                    mock.first.return_value = None
                return mock
            
            mock_flag.query.filter_by.side_effect = side_effect
            
            rec = get_recommender()
            from app.ai.recommender import HybridRecommender
            assert isinstance(rec, HybridRecommender)

    def test_returns_shadow_when_shadow_mode(self):
        """Debe retornar ShadowRecommender si shadow_mode=True."""
        from app.ai.recommender import get_recommender
        
        with patch('app.models.config.FeatureFlag') as mock_flag:
            def side_effect(key, enabled):
                mock = MagicMock()
                if key == 'ml_shadow_mode':
                    mock.first.return_value = MagicMock()
                else:
                    mock.first.return_value = None
                return mock
            
            mock_flag.query.filter_by.side_effect = side_effect
            
            rec = get_recommender()
            from app.ai.recommender import ShadowRecommender
            assert isinstance(rec, ShadowRecommender)
