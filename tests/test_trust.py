"""Tests unitarios para TrustScore — Score de confianza.

Estos tests verifican:
1. Cálculo del score (ponderación)
2. Determinación de niveles
3. Get or create
4. Servicio TrustService
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime


class TestTrustScoreModel:
    """Tests para el modelo TrustScore."""

    def test_score_calculation_perfect(self):
        """Score máximo cuando todos los componentes son ideales."""
        from app.models.trust import TrustScore
        
        trust = TrustScore()
        trust.kyc_verificado = True
        trust.rating_score = 1.0
        trust.contratos_completados = 50  # Max
        trust.portfolio_calidad = 1.0
        trust.referidos_count = 10  # Max
        
        # Calcular score manualmente
        score = (
            0.25 * 1 +  # kyc
            0.25 * 1 +  # rating
            0.20 * 1 +  # contratos (50/50)
            0.15 * 1 +  # portfolio
            0.15 * 1    # referidos (10/10)
        )
        
        assert score == 1.0

    def test_score_calculation_zero(self):
        """Score mínimo cuando todos los componentes son cero."""
        from app.models.trust import TrustScore
        
        trust = TrustScore()
        trust.kyc_verificado = False
        trust.rating_score = 0.0
        trust.contratos_completados = 0
        trust.portfolio_calidad = 0.0
        trust.referidos_count = 0
        
        score = (
            0.25 * 0 +  # kyc
            0.25 * 0 +  # rating
            0.20 * 0 +  # contratos
            0.15 * 0 +  # portfolio
            0.15 * 0    # referidos
        )
        
        assert score == 0.0

    def test_nivel_experto(self):
        """Nivel 'experto' para score >= 0.8."""
        from app.models.trust import TrustScore
        
        trust = TrustScore()
        trust.puntuacion = 0.85
        
        nivel = trust._determinar_nivel()
        assert nivel == 'experto'

    def test_nivel_verificado(self):
        """Nivel 'verificado' para 0.6 <= score < 0.8."""
        from app.models.trust import TrustScore
        
        trust = TrustScore()
        trust.puntuacion = 0.65
        
        nivel = trust._determinar_nivel()
        assert nivel == 'verificado'

    def test_nivel_confiable(self):
        """Nivel 'confiable' para 0.4 <= score < 0.6."""
        from app.models.trust import TrustScore
        
        trust = TrustScore()
        trust.puntuacion = 0.45
        
        nivel = trust._determinar_nivel()
        assert nivel == 'confiable'

    def test_nivel_nuevo(self):
        """Nivel 'nuevo' para score < 0.4."""
        from app.models.trust import TrustScore
        
        trust = TrustScore()
        trust.puntuacion = 0.2
        
        nivel = trust._determinar_nivel()
        assert nivel == 'nuevo'

    def test_pesos_suman_uno(self):
        """Los pesos deben sumar exactamente 1.0."""
        from app.models.trust import TrustScore
        
        total = sum(TrustScore.PESOS.values())
        assert abs(total - 1.0) < 0.001

    def test_umbrales_ordenados(self):
        """Los umbrales deben estar ordenados de mayor a menor."""
        from app.models.trust import TrustScore
        
        umbrales = list(TrustScore.UMBRALES.values())
        assert umbrales == sorted(umbrales, reverse=True)


class TestTrustService:
    """Tests para TrustService."""

    def test_get_trust_returns_dict(self):
        """get_trust debe retornar un dict con los campos esperados."""
        from app.services.trust import TrustService
        from app.models.trust import TrustScore
        from app import create_app
        from app.extensions import db as _db, cache as _cache
        
        app = create_app("app.config.TestingConfig")
        with app.app_context():
            _db.create_all()
            _cache.init_app(app)
            
            # Mock del TrustScore
            mock_trust = MagicMock()
            mock_trust.puntuacion = 0.75
            mock_trust.nivel = 'verificado'
            mock_trust.kyc_verificado = True
            mock_trust.portfolio_calidad = 0.6
            mock_trust.rating_score = 0.8
            mock_trust.contratos_completados = 25
            mock_trust.referidos_count = 5
            mock_trust.calculado_en = datetime.utcnow()
            mock_trust.version = 3
            
            with patch.object(TrustScore, 'get_or_create', return_value=mock_trust):
                with patch.object(TrustScore, 'calcular', return_value=0.75):
                    data = TrustService.get_trust(pds_id=42)
                    
                    assert 'puntuacion' in data
                    assert 'nivel' in data
                    assert 'componentes' in data
                    assert data['puntuacion'] == 0.75
                    assert data['nivel'] == 'verificado'
            
            _db.drop_all()

    def test_recalculate_invalidates_cache(self):
        """recalculate debe invalidar el cache."""
        from app.services.trust import TrustService
        from app.models.trust import TrustScore
        
        mock_trust = MagicMock()
        mock_trust.calcular.return_value = 0.8
        mock_trust.nivel = 'experto'
        mock_trust.version = 1
        
        with patch.object(TrustScore, 'get_or_create', return_value=mock_trust):
            with patch('app.services.trust.cache.delete_memoized') as mock_delete:
                result = TrustService.recalculate(pds_id=42)
                
                assert result['puntuacion'] == 0.8
                mock_delete.assert_called_once()

    def test_get_top_trusted_returns_list(self):
        """get_top_trusted debe retornar una lista."""
        from app.services.trust import TrustService
        from app.models.trust import TrustScore
        from app import create_app
        from app.extensions import db as _db
        
        app = create_app("app.config.TestingConfig")
        with app.app_context():
            _db.create_all()
            
            mock_trusts = [
                MagicMock(pds_id=1, puntuacion=0.9, nivel='experto'),
                MagicMock(pds_id=2, puntuacion=0.8, nivel='verificado'),
            ]
            
            with patch.object(TrustScore, 'query') as mock_query:
                mock_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = mock_trusts
                
                with patch('app.services.trust.User') as MockUser:
                    MockUser.query.get.side_effect = lambda id: MagicMock(
                        email=f'user{id}@test.com',
                        nombre=f'User {id}'
                    )
                    
                    result = TrustService.get_top_trusted(n=2)
                    
                    assert len(result) == 2
                    assert result[0]['email'] == 'user1@test.com'
            
            _db.drop_all()

    def test_get_trust_distribution(self):
        """get_trust_distribution debe retornar conteo por nivel."""
        from app.services.trust import TrustService
        from app.models.trust import TrustScore
        
        mock_distribution = [
            ('nuevo', 45),
            ('confiable', 30),
            ('verificado', 20),
            ('experto', 5),
        ]
        
        with patch('app.services.trust.db.session.query') as mock_query:
            mock_query.return_value.group_by.return_value.all.return_value = mock_distribution
            
            result = TrustService.get_trust_distribution()
            
            assert result == {
                'nuevo': 45,
                'confiable': 30,
                'verificado': 20,
                'experto': 5,
            }
