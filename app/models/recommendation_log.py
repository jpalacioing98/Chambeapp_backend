"""RecommendationLog — Log de recomendaciones para A/B testing.

Este modelo registra cada recomendación generada, permitiendo
análisis posterior de métricas por grupo (A/B) y modelo.

Uso:
    from app.models.recommendation_log import RecommendationLog

    log = RecommendationLog(
        solicitud_id=42,
        pds_id=7,
        puntuacion=0.85,
        ranking_pos=1,
        modelo_nombre='lightgbm_v1',
        experiment_group='A'
    )
    db.session.add(log)
    db.session.commit()
"""

from datetime import datetime
from app.extensions import db


class RecommendationLog(db.Model):
    """Log de recomendaciones para A/B testing.
    
    Attributes:
        solicitud_id: ID de la solicitud
        pds_id: ID del proveedor recomendado
        puntuacion: Score asignado
        ranking_pos: Posición en el ranking (1-N)
        features_snapshot: Snapshot de features usadas
        modelo_nombre: Nombre del modelo ('lightgbm_v1', 'heuristic')
        modelo_version: Versión del modelo
        notificado: Si se notificó al proveedor
        respondio: Si el proveedor respondió
        aceptado: Si la oferta fue aceptada
        experiment_group: Grupo A/B ('A', 'B')
        created_at: Fecha de creación
    """
    
    __tablename__ = 'recommendation_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    solicitud_id = db.Column(db.Integer, db.ForeignKey('solicitudes.id'))
    pds_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    puntuacion = db.Column(db.Float)
    ranking_pos = db.Column(db.Integer)
    features_snapshot = db.Column(db.JSON)
    
    modelo_nombre = db.Column(db.String(50))
    modelo_version = db.Column(db.String(50))
    
    notificado = db.Column(db.Boolean, default=False)
    respondio = db.Column(db.Boolean, default=False)
    aceptado = db.Column(db.Boolean, default=False)
    
    experiment_group = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        """Convierte a dict para serialización."""
        return {
            'id': self.id,
            'solicitud_id': self.solicitud_id,
            'pds_id': self.pds_id,
            'puntuacion': self.puntuacion,
            'ranking_pos': self.ranking_pos,
            'modelo_nombre': self.modelo_nombre,
            'modelo_version': self.modelo_version,
            'experiment_group': self.experiment_group,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
    
    @classmethod
    def log_recommendation(cls, solicitud_id, pds_id, score, model, group, 
                           ranking_pos=None, features=None, version=None):
        """Crea y guarda un log de recomendación."""
        log = cls(
            solicitud_id=solicitud_id,
            pds_id=pds_id,
            puntuacion=score,
            ranking_pos=ranking_pos,
            features_snapshot=features,
            modelo_nombre=model,
            modelo_version=version,
            experiment_group=group
        )
        db.session.add(log)
        db.session.commit()
        return log
    
    @classmethod
    def get_metrics_by_group(cls):
        """Calcula métricas por grupo A/B."""
        from sqlalchemy import func
        
        metrics = db.session.query(
            cls.experiment_group,
            func.count(cls.id).label('total'),
            func.avg(cls.puntuacion).label('avg_score'),
            func.sum(cls.aceptado.cast(db.Integer)).label('aceptados')
        ).group_by(cls.experiment_group).all()
        
        return {
            row.experiment_group: {
                'total': row.total,
                'avg_score': float(row.avg_score or 0),
                'aceptados': row.aceptados or 0,
                'tasa_aceptacion': (row.aceptados or 0) / row.total if row.total else 0
            }
            for row in metrics
        }
