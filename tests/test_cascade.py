"""Tests unitarios para NotificationCascade y CascadeManager.

Estos tests verifican:
1. Creación de cascada
2. Envío de fases
3. Expansión de radio por fase
4. Completación de cascada
5. Cancelación
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime


class TestNotificationCascade:
    """Tests para el modelo NotificationCascade."""

    def test_create_cascade(self):
        """Debe crear cascada con config por defecto."""
        from app.models.cascade import NotificationCascade
        
        cascade = NotificationCascade(
            solicitud_id=42,
            config_json=[
                {"radius_km": 2.0, "delay_seconds": 300, "max_candidates": 5},
                {"radius_km": 5.0, "delay_seconds": 600, "max_candidates": 10},
            ],
            estado='activa',
            fase_actual=1
        )
        
        assert cascade.solicitud_id == 42
        assert cascade.fase_actual == 1
        assert cascade.estado == 'activa'
        assert len(cascade.config_json) == 2

    def test_get_current_phase(self):
        """get_current_phase debe retornar fase actual."""
        from app.models.cascade import NotificationCascade
        
        cascade = NotificationCascade(
            solicitud_id=42,
            config_json=[
                {"radius_km": 2.0, "delay_seconds": 300, "max_candidates": 5},
                {"radius_km": 5.0, "delay_seconds": 600, "max_candidates": 10},
            ],
            fase_actual=1
        )
        
        phase = cascade.get_current_phase()
        assert phase['radius_km'] == 2.0
        
        cascade.fase_actual = 2
        phase = cascade.get_current_phase()
        assert phase['radius_km'] == 5.0

    def test_mark_completed(self):
        """mark_completed debe cambiar estado."""
        from app.models.cascade import NotificationCascade
        
        cascade = NotificationCascade(solicitud_id=42, estado='activa')
        
        with patch('app.models.cascade.db.session.commit'):
            cascade.mark_completed()
            assert cascade.estado == 'completada'
            assert cascade.completed_at is not None

    def test_log_phase(self):
        """log_phase debe agregar entrada al log."""
        from app.models.cascade import NotificationCascade
        
        cascade = NotificationCascade(solicitud_id=42, estado='activa')
        cascade.log_json = []
        
        with patch('app.models.cascade.db.session.commit'):
            cascade.log_phase(fase=1, enviados=5, radio_km=2.0)
            
            assert len(cascade.log_json) == 1
            assert cascade.log_json[0]['fase'] == 1
            assert cascade.log_json[0]['enviados'] == 5
            assert cascade.log_json[0]['radio_km'] == 2.0


class TestCascadeManager:
    """Tests para CascadeManager."""

    @pytest.fixture(autouse=True)
    def _setup_app(self):
        from app import create_app
        from app.extensions import db as _db
        app = create_app("app.config.TestingConfig")
        with app.app_context():
            _db.create_all()
            yield
            _db.session.remove()
            _db.drop_all()

    def test_start_cascade(self):
        """start_cascade debe crear y programar cascada."""
        from app.services.cascade import CascadeManager
        
        with patch('app.services.cascade.NotificationCascade') as mock_model:
            mock_cascade = MagicMock()
            mock_model.return_value = mock_cascade
            mock_model.query.filter_by.return_value.first.return_value = None
            
            with patch('app.services.cascade.db.session') as mock_db:
                with patch('app.services.cascade.send_phase_task') as mock_task:
                    cascade = CascadeManager.start_cascade(solicitud_id=42)
                    
                    assert cascade is mock_cascade
                    mock_task.delay.assert_called_once_with(mock_cascade.id)

    def test_send_phase_success(self):
        """send_phase debe enviar notificaciones y programar siguiente fase."""
        from app.services.cascade import CascadeManager
        
        # Mock cascade
        cascade = MagicMock()
        cascade.estado = 'activa'
        cascade.config_json = [
            {"radius_km": 2.0, "delay_seconds": 300, "max_candidates": 5},
            {"radius_km": 5.0, "delay_seconds": 600, "max_candidates": 10},
        ]
        cascade.fase_actual = 1
        cascade.get_current_phase.return_value = cascade.config_json[0]
        
        # Mock solicitud
        solicitud = MagicMock()
        solicitud.latitud = 10.4
        solicitud.longitud = -73.2
        solicitud.categoria = 'plomeria'
        
        # Mock the imported NotificationCascade and Solicitud in the cascade module
        with patch('app.services.cascade.NotificationCascade') as MockNC:
            MockNC.query.get.return_value = cascade
            with patch('app.services.cascade.Solicitud') as MockSol:
                MockSol.query.get.return_value = solicitud
                with patch('app.services.cascade.find_nearby_providers', return_value=[MagicMock(id=1), MagicMock(id=2)]):
                    with patch('app.services.cascade.Notification') as mock_notif:
                        with patch('app.services.cascade.db.session') as mock_db:
                            with patch('app.services.cascade.send_phase_task') as mock_task:
                                with patch('app.extensions.socketio') as mock_sio:
                                    CascadeManager.send_phase(cascade_id=1)
                                    
                                    # Debe haber enviado 2 notificaciones
                                    assert mock_notif.call_count == 2
                                    # Debe haber programado siguiente fase
                                    mock_task.apply_async.assert_called_once()

    def test_send_phase_completes_last(self):
        """send_phase debe completar si es la última fase."""
        from app.services.cascade import CascadeManager
        
        cascade = MagicMock()
        cascade.estado = 'activa'
        cascade.config_json = [
            {"radius_km": 2.0, "delay_seconds": 300, "max_candidates": 5},
        ]
        cascade.fase_actual = 1
        cascade.get_current_phase.return_value = cascade.config_json[0]
        
        solicitud = MagicMock()
        solicitud.latitud = 10.4
        solicitud.longitud = -73.2
        solicitud.categoria = 'plomeria'
        
        with patch('app.services.cascade.NotificationCascade') as MockNC:
            MockNC.query.get.return_value = cascade
            with patch('app.services.cascade.Solicitud') as MockSol:
                MockSol.query.get.return_value = solicitud
                with patch('app.services.cascade.find_nearby_providers', return_value=[]):
                    with patch('app.services.cascade.Notification'):
                        with patch('app.services.cascade.db.session'):
                            CascadeManager.send_phase(cascade_id=1)
                            
                            # Debe marcar como completada
                            cascade.mark_completed.assert_called_once()

    def test_cancel_cascade(self):
        """cancel_cascade debe cancelar la cascada."""
        from app.services.cascade import CascadeManager
        
        cascade = MagicMock()
        
        with patch('app.services.cascade.NotificationCascade') as MockNC:
            MockNC.query.filter_by.return_value.first.return_value = cascade
            
            CascadeManager.cancel_cascade(solicitud_id=42)
            cascade.cancel.assert_called_once()
