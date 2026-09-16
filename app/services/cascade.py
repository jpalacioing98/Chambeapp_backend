"""CascadeManager — Gestión de notificaciones en cascada.

Este servicio gestiona el envío de notificaciones en cascada para
solicitudes de servicio, expandiendo el radio geográfico por fases.

Uso:
    from app.services.cascade import CascadeManager

    # Iniciar cascada
    cascade = CascadeManager.start_cascade(solicitud_id=42)

    # Enviar fase (tarea Celery)
    CascadeManager.send_phase(cascade_id=cascade.id)
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from app.extensions import db, celery
from app.models.cascade import NotificationCascade
from app.models.solicitud import Solicitud
from app.models.notification import Notification
from app.ai.geo import find_nearby_providers

logger = logging.getLogger(__name__)


class CascadeManager:
    """Gestor de notificaciones en cascada."""
    
    # Configuración por defecto (3 fases)
    DEFAULT_CONFIG = [
        {"radius_km": 2.0, "delay_seconds": 300, "max_candidates": 5},
        {"radius_km": 5.0, "delay_seconds": 600, "max_candidates": 10},
        {"radius_km": 15.0, "delay_seconds": 900, "max_candidates": 15},
    ]
    
    @classmethod
    def start_cascade(cls, solicitud_id: int, config: list = None) -> NotificationCascade:
        """Inicia una cascada de notificaciones.
        
        Args:
            solicitud_id: ID de la solicitud
            config: Lista de fases [{radius_km, delay_seconds, max_candidates}]
            
        Returns:
            NotificationCascade creada
        """
        config = config or cls.DEFAULT_CONFIG
        
        # Verificar que no exista ya una cascada
        existing = NotificationCascade.query.filter_by(solicitud_id=solicitud_id).first()
        if existing:
            logger.warning(f"Cascada ya existe para solicitud {solicitud_id}")
            return existing
        
        cascade = NotificationCascade(
            solicitud_id=solicitud_id,
            config_json=config,
            estado='activa',
            fase_actual=1
        )
        db.session.add(cascade)
        db.session.commit()
        
        # Programar primera fase
        from app.services.cascade import send_phase_task
        send_phase_task.delay(cascade.id)
        
        logger.info(f"Cascada iniciada para solicitud {solicitud_id}")
        return cascade
    
    @classmethod
    def send_phase(cls, cascade_id: int):
        """Envía notificaciones de una fase.
        
        Args:
            cascade_id: ID de la cascada
        """
        cascade = NotificationCascade.query.get(cascade_id)
        if not cascade or cascade.estado != 'activa':
            logger.warning(f"Cascada {cascade_id} no activa")
            return
        
        phase = cascade.get_current_phase()
        if not phase:
            cascade.mark_completed()
            return
        
        solicitud = Solicitud.query.get(cascade.solicitud_id)
        if not solicitud:
            cascade.mark_expired()
            return
        
        # Buscar candidatos en el radio
        candidates = find_nearby_providers(
            lat=solicitud.latitud or 0,
            lng=solicitud.longitud or 0,
            radius_km=phase['radius_km'],
            top_k=phase['max_candidates']
        )
        
        # Enviar notificaciones
        enviados = 0
        creadas = []
        for provider in candidates:
            notif = Notification(
                user_id=provider.id,
                tipo='nueva_solicitud',
                titulo='Nueva solicitud cerca de ti',
                mensaje=f'Hay una solicitud de {solicitud.categoria} a {phase["radius_km"]}km',
                datos={'solicitud_id': solicitud.id}
            )
            db.session.add(notif)
            creadas.append(notif)
            enviados += 1
        
        db.session.commit()
        
        # Emitir en tiempo real vía Socket.IO (cola Redis / message_queue).
        # El servidor Flask (que mantiene las conexiones de clientes) recibe
        # el evento desde Redis y lo difunde a la sala user:<id>.
        from app.extensions import socketio
        for notif in creadas:
            socketio.emit(
                'notificacion:nueva',
                notif.to_dict(),
                room=f'user:{notif.user_id}',
            )
        
        # Log de fase
        cascade.log_phase(cascade.fase_actual, enviados, phase['radius_km'])
        cascade.enviados_total += enviados
        
        # Programar siguiente fase si existe
        if cascade.fase_actual < len(cascade.config_json):
            cascade.fase_actual += 1
            delay = cascade.config_json[cascade.fase_actual - 1]['delay_seconds']
            
            from app.services.cascade import send_phase_task
            send_phase_task.apply_async(args=[cascade.id], countdown=delay)
            
            db.session.commit()
        else:
            cascade.mark_completed()
        
        logger.info(f"Fase {cascade.fase_actual} enviada: {enviados} notificaciones")
    
    @classmethod
    def cancel_cascade(cls, solicitud_id: int):
        """Cancela una cascada."""
        cascade = NotificationCascade.query.filter_by(solicitud_id=solicitud_id).first()
        if cascade:
            cascade.cancel()
            logger.info(f"Cascada cancelada para solicitud {solicitud_id}")
    
    @classmethod
    def get_status(cls, cascade_id: int) -> dict:
        """Obtiene estado de una cascada."""
        cascade = NotificationCascade.query.get(cascade_id)
        if not cascade:
            return None
        return cascade.to_dict()


# Tarea Celery para enviar fase
@celery.task(name="app.services.cascade.send_phase_task")
def send_phase_task(cascade_id: int):
    """Tarea Celery para enviar fase de cascada."""
    from app import create_app
    
    app = create_app()
    with app.app_context():
        CascadeManager.send_phase(cascade_id)
