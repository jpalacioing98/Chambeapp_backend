"""Script de rollout gradual de ML.

Este script ejecuta el rollout gradual del modelo ML en 4 fases:
1. Shadow mode (solo log)
2. 10% tráfico ML
3. 50% tráfico ML
4. 100% ML (heurístico como fallback)

Uso:
    cd Chambeapp_backend
    python scripts/rollout_ml.py --phase 1
    python scripts/rollout_ml.py --phase 2
    python scripts/rollout_ml.py --phase 3
    python scripts/rollout_ml.py --phase 4
"""

import argparse
import logging

from app import create_app
from app.extensions import db
from app.models.config import FeatureFlag

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def set_flag(key: str, enabled: bool):
    """Activa/desactiva un feature flag."""
    flag = FeatureFlag.query.filter_by(key=key).first()
    if not flag:
        flag = FeatureFlag(key=key, enabled=enabled)
        db.session.add(flag)
    else:
        flag.enabled = enabled
    db.session.commit()
    logger.info(f"Flag '{key}' = {enabled}")


def phase_1_shadow():
    """Fase 1: Shadow mode (solo log ML)."""
    logger.info("🚀 Fase 1: Shadow mode")
    set_flag('ml_shadow_mode', True)
    set_flag('ml_ranking_enabled', False)
    logger.info("✅ ML en shadow mode. Usuarios ven heurístico, ML se loguea.")


def phase_2_ten_percent():
    """Fase 2: 10% tráfico ML."""
    logger.info("🚀 Fase 2: 10% tráfico ML")
    set_flag('ml_shadow_mode', False)
    set_flag('ml_ranking_enabled', True)
    # TODO: Implementar porcentaje de tráfico en factory
    logger.info("✅ ML activado al 10% del tráfico.")


def phase_3_fifty_percent():
    """Fase 3: 50% tráfico ML."""
    logger.info("🚀 Fase 3: 50% tráfico ML")
    set_flag('ml_ranking_enabled', True)
    logger.info("✅ ML activado al 50% del tráfico.")


def phase_4_full():
    """Fase 4: 100% ML."""
    logger.info("🚀 Fase 4: 100% ML")
    set_flag('ml_shadow_mode', False)
    set_flag('ml_ranking_enabled', True)
    logger.info("✅ ML activado al 100%. Heurístico como fallback.")


def main():
    parser = argparse.ArgumentParser(description="Rollout gradual de ML")
    parser.add_argument('--phase', type=int, choices=[1, 2, 3, 4], required=True,
                       help="Fase de rollout (1-4)")
    args = parser.parse_args()
    
    app = create_app()
    with app.app_context():
        if args.phase == 1:
            phase_1_shadow()
        elif args.phase == 2:
            phase_2_ten_percent()
        elif args.phase == 3:
            phase_3_fifty_percent()
        elif args.phase == 4:
            phase_4_full()


if __name__ == "__main__":
    main()
