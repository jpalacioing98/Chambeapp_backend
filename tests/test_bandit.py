"""Tests unitarios para ThompsonBandit.

Estos tests verifican:
1. Selección de categoría (Thompson Sampling)
2. Actualización de distribución
3. Probabilidades de éxito
4. Valor de brazo (arm value)
5. Reset del estado
"""

import numpy as np
import pytest
from unittest.mock import patch, MagicMock


class TestThompsonBandit:
    """Tests para ThompsonBandit."""

    def test_init_loads_state(self):
        """Init debe cargar estado desde SystemConfig."""
        from app.ai.bandit import ThompsonBandit
        
        mock_state = {
            'alpha': {'plomeria': 5, 'electricidad': 3},
            'beta': {'plomeria': 2, 'electricidad': 1}
        }
        
        with patch('app.ai.bandit.SystemConfig') as mock_config:
            mock_config.get_value.return_value = mock_state
            
            bandit = ThompsonBandit()
            assert bandit.alpha == {'plomeria': 5, 'electricidad': 3}
            assert bandit.beta == {'plomeria': 2, 'electricidad': 1}

    def test_select_category(self):
        """select_category debe retornar una categoría válida."""
        from app.ai.bandit import ThompsonBandit
        
        with patch('app.ai.bandit.SystemConfig') as mock_config:
            mock_config.get_value.return_value = None
            
            bandit = ThompsonBandit()
            categories = ['plomeria', 'electricidad', 'pintura']
            
            selected = bandit.select_category(categories)
            assert selected in categories

    def test_select_category_empty(self):
        """select_category debe retornar None si no hay categorías."""
        from app.ai.bandit import ThompsonBandit
        
        with patch('app.ai.bandit.SystemConfig') as mock_config:
            mock_config.get_value.return_value = None
            
            bandit = ThompsonBandit()
            assert bandit.select_category([]) is None

    def test_update_success(self):
        """update debe incrementar alpha en éxito."""
        from app.ai.bandit import ThompsonBandit
        
        with patch('app.ai.bandit.SystemConfig') as mock_config:
            mock_config.get_value.return_value = None
            
            bandit = ThompsonBandit()
            bandit.update('plomeria', accepted=True)
            
            assert bandit.alpha['plomeria'] == 2  # 1 + 1
            assert bandit.beta['plomeria'] == 1   # 1 + 0

    def test_update_failure(self):
        """update debe incrementar beta en fallo."""
        from app.ai.bandit import ThompsonBandit
        
        with patch('app.ai.bandit.SystemConfig') as mock_config:
            mock_config.get_value.return_value = None
            
            bandit = ThompsonBandit()
            bandit.update('plomeria', accepted=False)
            
            assert bandit.alpha['plomeria'] == 1  # 1 + 0
            assert bandit.beta['plomeria'] == 2   # 1 + 1

    def test_get_probabilities(self):
        """get_probabilities debe retornar probabilidad correcta."""
        from app.ai.bandit import ThompsonBandit
        
        with patch('app.ai.bandit.SystemConfig') as mock_config:
            mock_config.get_value.return_value = None
            
            bandit = ThompsonBandit()
            bandit.alpha['plomeria'] = 5
            bandit.beta['plomeria'] = 5
            
            probs = bandit.get_probabilities(['plomeria'])
            assert probs['plomeria'] == 0.5  # 5 / (5+5)

    def test_get_arm_value(self):
        """get_arm_value debe retornar valor de brazo."""
        from app.ai.bandit import ThompsonBandit
        
        with patch('app.ai.bandit.SystemConfig') as mock_config:
            mock_config.get_value.return_value = None
            
            bandit = ThompsonBandit()
            bandit.alpha['plomeria'] = 8
            bandit.beta['plomeria'] = 2
            
            value = bandit.get_arm_value('plomeria')
            assert value == 0.8  # 8 / (8+2)

    def test_reset(self):
        """reset debe limpiar estado."""
        from app.ai.bandit import ThompsonBandit
        
        with patch('app.ai.bandit.SystemConfig') as mock_config:
            mock_config.get_value.return_value = None
            
            bandit = ThompsonBandit()
            bandit.alpha['plomeria'] = 5
            bandit.beta['plomeria'] = 2
            
            bandit.reset()
            assert bandit.alpha == {}
            assert bandit.beta == {}

    def test_exploration_emerges(self):
        """Thompson Sampling debe explorar categorías nuevas."""
        from app.ai.bandit import ThompsonBandit
        
        with patch('app.ai.bandit.SystemConfig') as mock_config:
            mock_config.get_value.return_value = None
            
            bandit = ThompsonBandit()
            
            # Categoría con mucho éxito
            bandit.alpha['plomeria'] = 100
            bandit.beta['plomeria'] = 10
            
            # Categoría nueva (prior uniforme)
            # Debe ser seleccionada ocasionalmente por exploración
            selections = []
            for _ in range(100):
                selections.append(bandit.select_category(['plomeria', 'nueva']))
            
            # La categoría nueva debe aparecer al menos una vez
            assert 'nueva' in selections
