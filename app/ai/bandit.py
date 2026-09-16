"""Thompson Sampling — Rotación inteligente de categorías.

Este módulo implementa un Multi-Armed Bandit usando Thompson Sampling
para rotación de categorías de servicios, permitiendo exploración
automática de categorías nuevas o con poco volumen.

Uso:
    from app.ai.bandit import ThompsonBandit

    bandit = ThompsonBandit()
    categoria = bandit.select_category(['plomeria', 'electricidad', 'pintura'])
    bandit.update(categoria, accepted=True)
"""

import numpy as np
import logging
from typing import Optional

from app.extensions import db
from app.models.config import SystemConfig

logger = logging.getLogger(__name__)


class ThompsonBandit:
    """Multi-Armed Bandit con Thompson Sampling."""

    # Configuración
    PRIOR_ALPHA = 1  # Successes + 1 (prior uniforme)
    PRIOR_BETA = 1  # Failures + 1 (prior uniforme)

    def __init__(self):
        """Inicializa el bandit y carga estado."""
        self.alpha = {}
        self.beta = {}
        self._load_state()

    def _load_state(self):
        """Carga estado desde SystemConfig."""
        state = SystemConfig.get_value('bandit_state')
        if state:
            self.alpha = state.get('alpha', {})
            self.beta = state.get('beta', {})

    def _save_state(self):
        """Guarda estado en SystemConfig."""
        SystemConfig.set_value('bandit_state', {
            'alpha': self.alpha,
            'beta': self.beta
        })

    def select_category(self, categories: list[str]) -> str:
        """Selecciona categoría usando Thompson Sampling.
        
        Args:
            categories: Lista de categorías disponibles
            
        Returns:
            Categoría seleccionada (sample con mayor probabilidad posterior)
        """
        if not categories:
            return None

        samples = []
        for cat in categories:
            a = self.alpha.get(cat, self.PRIOR_ALPHA)
            b = self.beta.get(cat, self.PRIOR_BETA)
            samples.append(np.random.beta(a, b))

        return categories[np.argmax(samples)]

    def update(self, category: str, accepted: bool):
        """Actualiza distribución según resultado.
        
        Args:
            category: Categoría evaluada
            accepted: True si fue aceptada, False si rechazada
        """
        if category not in self.alpha:
            self.alpha[category] = self.PRIOR_ALPHA
            self.beta[category] = self.PRIOR_BETA

        if accepted:
            self.alpha[category] += 1
        else:
            self.beta[category] += 1

        self._save_state()
        logger.debug(f"Bandit updated: {category} accepted={accepted}")

    def get_probabilities(self, categories: list[str]) -> dict:
        """Retorna probabilidad de éxito por categoría.
        
        Args:
            categories: Lista de categorías
            
        Returns:
            Dict {categoria: probabilidad}
        """
        probs = {}
        for cat in categories:
            a = self.alpha.get(cat, self.PRIOR_ALPHA)
            b = self.beta.get(cat, self.PRIOR_BETA)
            probs[cat] = a / (a + b)
        return probs

    def get_arm_value(self, category: str) -> float:
        """Retorna valor UCB1 de un brazo (categoría).
        
        Útil como feature para el modelo ML.
        """
        a = self.alpha.get(category, self.PRIOR_ALPHA)
        b = self.beta.get(category, self.PRIOR_BETA)
        return a / (a + b)

    def reset(self):
        """Reinicia el estado del bandit."""
        self.alpha = {}
        self.beta = {}
        self._save_state()
        logger.info("Bandit reiniciado")
