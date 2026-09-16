"""NotificationCascade — Sistema de notificaciones en cascada.

Este modelo gestiona el envío de notificaciones en cascada para
solicitudes de servicio, expandiendo el radio geográfico por fases.

Uso:
    from app.models.cascade import NotificationCascade

    cascade = NotificationCascade(
        solicitud_id=42,
        config_json=[
            {"radius_km": 2.0, "delay_seconds": 300, "max_candidates": 5},
            {"radius_km": 5.0, "delay_seconds": 600, "max_candidates": 10},
            {"radius_km": 15.0, "delay_seconds": 900, "max_candidates": 15},
        ],
        estado='activa'
    )
    db.session.add(cascade)
    db.session.commit()
"""

from datetime import datetime
from app.extensions import db


class NotificationCascade(db.Model):
    """Cascada de notificaciones para una solicitud.
    
    Attributes:
        solicitud_id: ID de la solicitud
        fase_actual: Fase actual (1-N)
        config_json: Configuración de fases [{radius_km, delay_seconds, max_candidates}]
        estado: 'activa', 'completada', 'expirada', 'cancelada'
        enviados_total: Total de notificaciones enviadas
        respondidos_total: Total de respuestas recibidas
        timer_expira: Cuándo expira la fase actual
        started_at: Cuándo inició la cascada
        completed_at: Cuándo completó
        log_json: Log de actividad por fase
    """
    
    __tablename__ = 'notification_cascades'
    
    id = db.Column(db.Integer, primary_key=True)
    solicitud_id = db.Column(db.Integer, db.ForeignKey('solicitudes.id'), unique=True)
    
    fase_actual = db.Column(db.Integer, default=1)
    config_json = db.Column(db.JSON)  # [{radius_km, delay_seconds, max_candidates}]
    
    estado = db.Column(
        db.Enum('activa', 'completada', 'expirada', 'cancelada', name='cascade_estado'),
        default='activa'
    )
    
    enviados_total = db.Column(db.Integer, default=0)
    respondidos_total = db.Column(db.Integer, default=0)
    
    timer_expira = db.Column(db.DateTime)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    
    log_json = db.Column(db.JSON)  # [{fase, enviados, radio, timestamp}]
    
    def to_dict(self):
        """Convierte a dict para serialización."""
        return {
            'id': self.id,
            'solicitud_id': self.solicitud_id,
            'fase_actual': self.fase_actual,
            'config': self.config_json,
            'estado': self.estado,
            'enviados_total': self.enviados_total,
            'respondidos_total': self.respondidos_total,
            'timer_expira': self.timer_expira.isoformat() if self.timer_expira else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }
    
    def get_current_phase(self):
        """Retorna la configuración de la fase actual."""
        if not self.config_json:
            return None
        if self.fase_actual > len(self.config_json):
            return None
        return self.config_json[self.fase_actual - 1]
    
    def mark_completed(self):
        """Marca la cascada como completada."""
        self.estado = 'completada'
        self.completed_at = datetime.utcnow()
        db.session.commit()
    
    def mark_expired(self):
        """Marca la cascada como expirada."""
        self.estado = 'expirada'
        self.completed_at = datetime.utcnow()
        db.session.commit()
    
    def cancel(self):
        """Cancela la cascada."""
        self.estado = 'cancelada'
        self.completed_at = datetime.utcnow()
        db.session.commit()
    
    def log_phase(self, fase: int, enviados: int, radio_km: float):
        """Agrega entrada al log de fases."""
        if not self.log_json:
            self.log_json = []
        
        self.log_json.append({
            'fase': fase,
            'enviados': enviados,
            'radio_km': radio_km,
            'timestamp': datetime.utcnow().isoformat()
        })
        db.session.commit()
    
    @classmethod
    def get_active(cls):
        """Obtiene cascadas activas."""
        return cls.query.filter_by(estado='activa').all()
    
    def __repr__(self):
        return f'<NotificationCascade id={self.id} solicitud_id={self.solicitud_id} fase={self.fase_actual}>'
