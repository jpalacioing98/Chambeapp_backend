"""Load testing para NotificationCascade.

Este test verifica que el sistema de cascada puede manejar múltiples
solicitudes simultáneas sin degradación significativa.

Uso:
    cd Chambeapp_backend
    python -m pytest tests/load/test_cascade_load.py -v
"""

import time
import pytest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch, MagicMock


class TestCascadeLoad:
    """Tests de carga para cascadas."""

    def test_multiple_cascades_concurrent(self):
        """Debe manejar múltiples cascadas concurrentes."""
        from app.services.cascade import CascadeManager
        
        n_cascades = 10
        
        with patch('app.services.cascade.NotificationCascade') as mock_model:
            mock_cascade = MagicMock()
            mock_model.return_value = mock_cascade
            mock_model.query.filter_by.return_value.first.return_value = None
            
            with patch('app.services.cascade.db.session'):
                with patch('app.services.cascade.send_phase_task'):
                    start = time.time()
                    
                    # Crear cascadas en paralelo
                    with ThreadPoolExecutor(max_workers=5) as executor:
                        futures = [
                            executor.submit(
                                CascadeManager.start_cascade,
                                solicitud_id=i
                            )
                            for i in range(n_cascades)
                        ]
                        results = [f.result() for f in futures]
                    
                    elapsed = time.time() - start
                    
                    assert len(results) == n_cascades
                    assert elapsed < 5.0  # Debe completar en <5s

    def test_cascade_send_phase_performance(self):
        """send_phase debe ser rápido incluso con muchos candidatos."""
        from app.services.cascade import CascadeManager
        from app.models.cascade import NotificationCascade
        
        # Mock cascade con 100 candidatos
        cascade = MagicMock()
        cascade.estado = 'activa'
        cascade.config_json = [
            {"radius_km": 15.0, "delay_seconds": 900, "max_candidates": 100},
        ]
        cascade.fase_actual = 1
        cascade.get_current_phase.return_value = cascade.config_json[0]
        
        solicitud = MagicMock()
        solicitud.latitud = 10.4
        solicitud.longitud = -73.2
        solicitud.categoria = 'plomeria'
        
        # 100 candidatos mock
        candidates = [MagicMock(id=i) for i in range(100)]
        
        with patch('app.services.cascade.NotificationCascade.query.get', return_value=cascade):
            with patch('app.services.cascade.Solicitud.query.get', return_value=solicitud):
                with patch('app.services.cascade.find_nearby_providers', return_value=candidates):
                    with patch('app.services.cascade.Notification') as mock_notif:
                        with patch('app.services.cascade.db.session'):
                            with patch('app.services.cascade.send_phase_task'):
                                start = time.time()
                                CascadeManager.send_phase(cascade_id=1)
                                elapsed = time.time() - start
                                
                                # Debe enviar 100 notificaciones rápido
                                assert mock_notif.call_count == 100
                                assert elapsed < 2.0  # <2s para 100 notificaciones
