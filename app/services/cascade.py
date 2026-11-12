"""CascadeManager — Gestión de notificaciones en cascada.

Este servicio gestiona el envío de notificaciones en cascada para
solicitudes de servicio, expandiendo el radio geográfico por fases.

Uso:
    from app.services.cascade import CascadeManager

    # Iniciar cascada
    cascade = CascadeManager.start_cascade(solicitud_id=42)

    # Enviar fase (tarea Celery)
    CascadeManager.send_phase(cascade_id=cascade.id)

La cascada es el SEGUNDO mecanismo de aviso (el primero es el aviso
inmediato a elegibles, `app.services.descubrimiento`): si nadie postula en
las primeras fases, el radio se amplía para captar PDS más lejanos.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from app.extensions import db, celery
from app.models.cascade import NotificationCascade
from app.models.solicitud import Solicitud
from app.models.notification import Notification
from app.schemas.solicitud import SolicitudSchema
from app.services.descubrimiento import (
    TIPO_NUEVA_SOLICITUD,
    pds_elegibles,
    usuarios_notificados,
)
from app.services.preferencias import preferencia_permite
from app.services.push import enviar_push_notificacion
from app.services.realtime import safe_emit

logger = logging.getLogger(__name__)


def _dump_solicitud(solicitud) -> dict | None:
    """Serializa la solicitud para emitarla por socket (o None si falla)."""
    try:
        return SolicitudSchema().dump(solicitud)
    except Exception:  # noqa: BLE001 — el dump nunca debe tumbar la fase
        logger.warning("No se pudo serializar la solicitud %s", getattr(solicitud, "id", "?"))
        return None


class CascadeManager:
    """Gestor de notificaciones en cascada."""

    # Configuración por defecto (3 fases).
    # `delay_seconds` = espera DESPUÉS de enviar esta fase antes de lanzar
    # la siguiente. La fase 1 se lanza de inmediato al crear la solicitud.
    DEFAULT_CONFIG = [
        {"radius_km": 20.0, "delay_seconds": 30, "max_candidates": 20},
        {"radius_km": 50.0, "delay_seconds": 120, "max_candidates": 40},
        {"radius_km": 100.0, "delay_seconds": 300, "max_candidates": 80},
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

        # Programar primera fase (inmediata). Si el broker no está disponible
        # se ejecuta la fase 1 EN ESTE PROCESO: tras el aviso inmediato a
        # elegibles (`app.services.descubrimiento`) normalmente no quedan
        # candidatos nuevos en 20 km, así que el coste es una consulta.
        if not cls._enqueue_phase(cascade.id):
            try:
                cls.send_phase(cascade.id)
            except Exception:  # noqa: BLE001 — el alta ya está persistida
                logger.exception(
                    "Fallo al ejecutar la fase 1 de la cascada %s en modo "
                    "degradado (sin broker)",
                    cascade.id,
                )

        logger.info(f"Cascada iniciada para solicitud {solicitud_id}")
        return cascade

    @classmethod
    def _enqueue_phase(cls, cascade_id: int, countdown: int = 0) -> bool:
        """Encola una fase en Celery. Devuelve False si el broker falla."""
        from app.services.cascade import send_phase_task

        try:
            send_phase_task.apply_async(args=[cascade_id], countdown=countdown)
            return True
        except Exception:  # noqa: BLE001 — broker caído no tumba la petición
            logger.warning(
                "No se pudo encolar la fase de la cascada %s "
                "(broker no disponible); queda para el barrido periódico",
                cascade_id,
                exc_info=True,
            )
            return False
    
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

        # Candidatos del radio de esta fase, filtrados por categoría
        # (mismo criterio que el listado `?elegibles=1`) y sin repetir a
        # quienes ya recibieron el aviso de esta solicitud.
        ya_notificados = usuarios_notificados(solicitud.id)
        candidates = pds_elegibles(
            solicitud,
            radius_km=phase['radius_km'],
            top_k=phase['max_candidates'],
            excluir_ids=ya_notificados,
        )

        # Enviar notificaciones
        enviados = 0
        creadas = []
        for provider in candidates:
            if not preferencia_permite(provider.id, TIPO_NUEVA_SOLICITUD):
                continue
            notif = Notification(
                user_id=provider.id,
                tipo=TIPO_NUEVA_SOLICITUD,
                titulo='Nueva solicitud cerca de ti',
                mensaje=f'Hay una solicitud de {solicitud.categoria} a {phase["radius_km"]}km',
                datos={
                    'solicitud_id': solicitud.id,
                    'categoria': solicitud.categoria,
                    'radio_km': phase['radius_km'],
                    'origen': 'cascada',
                    'fase': cascade.fase_actual,
                },
            )
            db.session.add(notif)
            creadas.append(notif)
            enviados += 1

        db.session.commit()

        # Emitir en tiempo real vía Socket.IO (cola Redis / message_queue).
        # El servidor Flask (que mantiene las conexiones de clientes) recibe
        # el evento desde Redis y lo difunde a la sala user:<id>.
        payload_solicitud = _dump_solicitud(solicitud)
        for notif in creadas:
            safe_emit(
                'notificacion:nueva',
                notif.to_dict(),
                room=f'user:{notif.user_id}',
            )
            if payload_solicitud is not None:
                safe_emit(
                    'solicitud:creada',
                    payload_solicitud,
                    room=f'user:{notif.user_id}',
                )
            enviar_push_notificacion(notif)

        # Log de fase
        fase_numero = cascade.fase_actual
        cascade.log_phase(fase_numero, enviados, phase['radius_km'])
        cascade.enviados_total += enviados

        # Programar siguiente fase si existe. El countdown usa el delay de
        # la fase ACTUAL (espera después de esta fase antes de ampliar).
        if cascade.fase_actual < len(cascade.config_json):
            cascade.fase_actual += 1
            delay = phase['delay_seconds']

            if cls._enqueue_phase(cascade.id, countdown=delay):
                cascade.timer_expira = None
            else:
                # Sin broker: deja la fase vencida para que el barrido
                # `app.tasks.resume_cascades` la reintente cuando vuelva.
                cascade.timer_expira = datetime.utcnow() + timedelta(seconds=delay)

            db.session.commit()
        else:
            cascade.mark_completed()

        logger.info(
            f"Fase {fase_numero} enviada: {enviados} notificaciones "
            f"(radio {phase['radius_km']}km)"
        )
    
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
