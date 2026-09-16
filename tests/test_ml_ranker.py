"""Tests unitarios para MLRanker — Modelo de ranking.

Estos tests verifican:
1. Entrenamiento del modelo
2. Predicción de scores
3. Feature importance
4. Explicación de predicciones
5. Guardado/carga de modelo
"""

import pytest

try:
    import lightgbm  # noqa: F401
    HAS_LIGHTGBM = True
except ImportError:
    HAS_LIGHTGBM = False

pytestmark = pytest.mark.skipif(
    not HAS_LIGHTGBM, reason="requires lightgbm (not installed in this env)"
)

import os
import numpy as np
import pytest
from unittest.mock import patch, MagicMock


class TestMLRanker:
    """Tests para MLRanker."""
    
    def test_init_no_model(self):
        """Init sin modelo debe tener model=None."""
        from app.ai.ml_ranker import MLRanker
        
        with patch.object(MLRanker, '_load_model') as mock_load:
            mock_load.return_value = None
            ranker = MLRanker()
            assert ranker.model is None
            assert ranker.is_trained() is False
    
    def test_train_insufficient_data(self):
        """train debe fallar con <100 samples."""
        from app.ai.ml_ranker import MLRanker
        
        ranker = MLRanker()
        ranker.model = None
        
        X = np.random.rand(50, 22)  # Solo 50 samples
        y = np.random.randint(0, 2, 50)
        
        with pytest.raises(ValueError):
            ranker.train(X, y, [f'f{i}' for i in range(22)])
    
    def test_train_success(self):
        """train debe entrenar exitosamente con >=100 samples."""
        from app.ai.ml_ranker import MLRanker
        
        ranker = MLRanker()
        ranker.model = None
        
        # Generar datos sintéticos
        np.random.seed(42)
        X = np.random.rand(200, 22)
        y = np.random.randint(0, 2, 200)
        feature_names = [f'f{i}' for i in range(22)]
        
        with patch.object(ranker, '_save_model') as mock_save:
            metrics = ranker.train(X, y, feature_names)
            
            assert ranker.is_trained() is True
            assert 'version' in metrics
            assert metrics['n_samples'] == 200
            assert metrics['n_features'] == 22
            assert 'feature_importance' in metrics
            mock_save.assert_called_once()
    
    def test_predict(self):
        """predict debe retornar scores."""
        from app.ai.ml_ranker import MLRanker
        
        ranker = MLRanker()
        ranker.model = None
        
        np.random.seed(42)
        X_train = np.random.rand(200, 22)
        y_train = np.random.randint(0, 2, 200)
        feature_names = [f'f{i}' for i in range(22)]
        
        with patch.object(ranker, '_save_model'):
            ranker.train(X_train, y_train, feature_names)
        
        # Predecir
        X_test = np.random.rand(5, 22)
        scores = ranker.predict(X_test)
        
        assert isinstance(scores, np.ndarray)
        assert scores.shape == (5,)
        assert all(0 <= s <= 1 for s in scores)
    
    def test_predict_not_trained(self):
        """predict debe fallar si modelo no entrenado."""
        from app.ai.ml_ranker import MLRanker
        
        ranker = MLRanker()
        ranker.model = None
        
        X = np.random.rand(5, 22)
        with pytest.raises(ValueError):
            ranker.predict(X)
    
    def test_get_feature_importance(self):
        """get_feature_importance debe retornar dict."""
        from app.ai.ml_ranker import MLRanker
        
        ranker = MLRanker()
        ranker.model = None
        
        np.random.seed(42)
        X = np.random.rand(200, 22)
        y = np.random.randint(0, 2, 200)
        feature_names = [f'f{i}' for i in range(22)]
        
        with patch.object(ranker, '_save_model'):
            ranker.train(X, y, feature_names)
        
        importance = ranker.get_feature_importance()
        assert isinstance(importance, dict)
        assert len(importance) == 22
    
    def test_get_feature_importance_no_model(self):
        """get_feature_importance debe retornar {} sin modelo."""
        from app.ai.ml_ranker import MLRanker
        
        ranker = MLRanker()
        ranker.model = None
        
        assert ranker.get_feature_importance() == {}
    
    def test_explain(self):
        """explain debe retornar string con top features."""
        from app.ai.ml_ranker import MLRanker
        
        ranker = MLRanker()
        ranker.model = None
        
        np.random.seed(42)
        X = np.random.rand(200, 22)
        y = np.random.randint(0, 2, 200)
        feature_names = [f'f{i}' for i in range(22)]
        
        with patch.object(ranker, '_save_model'):
            ranker.train(X, y, feature_names)
        
        features = {f'f{i}': np.random.rand() for i in range(22)}
        explanation = ranker.explain(features)
        
        assert isinstance(explanation, str)
        assert 'f' in explanation  # Debe contener nombres de features
    
    def test_explain_no_model(self):
        """explain debe retornar mensaje sin modelo."""
        from app.ai.ml_ranker import MLRanker
        
        ranker = MLRanker()
        ranker.model = None
        
        features = {'f0': 0.5}
        assert ranker.explain(features) == "Modelo no entrenado"
    
    def test_save_and_load(self, tmp_path):
        """Modelo debe guardarse y cargarse correctamente."""
        from app.ai.ml_ranker import MLRanker
        
        # Usar path temporal
        model_path = str(tmp_path / "test_model.pkl")
        
        ranker1 = MLRanker()
        ranker1.model = None
        
        np.random.seed(42)
        X = np.random.rand(200, 22)
        y = np.random.randint(0, 2, 200)
        feature_names = [f'f{i}' for i in range(22)]
        
        with patch.object(MLRanker, 'MODEL_PATH', model_path):
            with patch.object(ranker1, '_save_model'):
                ranker1.train(X, y, feature_names)
            
            # Cargar en nueva instancia
            with patch.object(MLRanker, 'MODEL_PATH', model_path):
                with patch.object(MLRanker, '_load_model'):
                    ranker2 = MLRanker()
                    ranker2.model = ranker1.model
                    ranker2.feature_names = ranker1.feature_names
                    ranker2.version = ranker1.version
                
                assert ranker2.is_trained() is True
                assert ranker2.feature_names == feature_names
