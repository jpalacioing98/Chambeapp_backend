"""TrustScore — Score consolidado de confianza del proveedor.

Este modelo calcula un score unificado de confianza (0-1) para cada
proveedor (PDS) basado en múltiples factores:

- KYC verificado
- Calidad del portafolio
- Rating promedio
- Contratos completados
- Referidos

El score se usa en el motor de recomendación ML como feature principal.

Uso:
    from app.models.trust import TrustScore

    # Obtener o crear trust score
    trust = TrustScore.get_or_create(pds_id=user_id)

    # Calcular score
    score = trust.calcular()

    # Consultar nivel
    print(trust.nivel)  # 'nuevo', 'confiable', 'verificado', 'experto'
"""

from datetime import datetime
from sqlalchemy import func
from app.extensions import db


class TrustScore(db.Model):
    """Score consolidado de confianza del proveedor.
    
    Attributes:
        pds_id: ID del usuario proveedor (unique)
        kyc_verificado: Si tiene KYC verificado
        portfolio_calidad: Calidad del portafolio (0-1)
        rating_score: Rating promedio normalizado (0-1)
        contratos_completados: Total de contratos completados
        referidos_count: Número de referidos activos
        puntuacion: Score final consolidado (0-1)
        nivel: Nivel de confianza ('nuevo', 'confiable', 'verificado', 'experto')
        componentes_json: Snapshot detallado de componentes
        calculado_en: Última fecha de cálculo
        version: Versión del cálculo (incrementa con cada recálculo)
    """
    
    __tablename__ = 'trust_scores'
    
    id = db.Column(db.Integer, primary_key=True)
    pds_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    
    # Componentes desglosados (0-1)
    kyc_verificado = db.Column(db.Boolean, default=False)
    portfolio_calidad = db.Column(db.Float, default=0.0)
    rating_score = db.Column(db.Float, default=0.0)
    contratos_completados = db.Column(db.Integer, default=0)
    referidos_count = db.Column(db.Integer, default=0)
    
    # Score final consolidado (0-1)
    puntuacion = db.Column(db.Float, default=0.0)
    nivel = db.Column(
        db.Enum('nuevo', 'confiable', 'verificado', 'experto', name='trust_level'),
        default='nuevo'
    )
    
    # Metadata
    componentes_json = db.Column(db.JSON)
    calculado_en = db.Column(db.DateTime, default=func.now())
    version = db.Column(db.Integer, default=1)
    
    # Relación
    pds = db.relationship('User', backref='trust_score', uselist=False)
    
    # Pesos para el cálculo (deben sumar 1.0)
    PESOS = {
        'kyc': 0.25,
        'rating': 0.25,
        'contratos': 0.20,
        'portfolio': 0.15,
        'referidos': 0.15,
    }
    
    # Umbrales para niveles
    UMBRALES = {
        'experto': 0.8,
        'verificado': 0.6,
        'confiable': 0.4,
        'nuevo': 0.0,
    }
    
    def calcular(self):
        """Calcula el score consolidado basado en múltiples factores.
        
        Returns:
            Score final (0-1)
            
        Example:
            >>> trust = TrustScore.get_or_create(pds_id=1)
            >>> score = trust.calcular()
            >>> print(f"Score: {score}, Nivel: {trust.nivel}")
            Score: 0.75, Nivel: verificado
        """
        from app.models.user import Profile
        
        profile = Profile.query.filter_by(user_id=self.pds_id).first()
        
        # Calcular componentes
        self.kyc_verificado = bool(profile.verificado) if profile else False
        self.rating_score = (profile.calificacion_promedio or 0) / 5.0 if profile else 0
        self.contratos_completados = self._contar_contratos()
        self.portfolio_calidad = self._calcular_calidad_portfolio()
        self.referidos_count = self._contar_referidos()
        
        # Calcular score ponderado
        self.puntuacion = round(
            self.PESOS['kyc'] * (1 if self.kyc_verificado else 0) +
            self.PESOS['rating'] * min(self.rating_score, 1.0) +
            self.PESOS['contratos'] * min(self.contratos_completados / 50, 1.0) +
            self.PESOS['portfolio'] * self.portfolio_calidad +
            self.PESOS['referidos'] * min(self.referidos_count / 10, 1.0),
            4
        )
        
        # Determinar nivel
        self.nivel = self._determinar_nivel()
        
        # Guardar snapshot de componentes
        self.componentes_json = {
            'kyc_verificado': self.kyc_verificado,
            'rating_score': round(self.rating_score, 4),
            'rating_raw': profile.calificacion_promedio if profile else 0,
            'contratos_completados': self.contratos_completados,
            'portfolio_calidad': round(self.portfolio_calidad, 4),
            'referidos_count': self.referidos_count,
            'pesos': self.PESOS,
        }
        
        self.calculado_en = datetime.utcnow()
        self.version += 1
        
        db.session.commit()
        return self.puntuacion
    
    def _determinar_nivel(self):
        """Determina el nivel según el score."""
        for nivel, umbral in sorted(self.UMBRALES.items(), key=lambda x: -x[1]):
            if self.puntuacion >= umbral:
                return nivel
        return 'nuevo'
    
    def _calcular_calidad_portfolio(self):
        """Evalúa calidad del portafolio (n items aprobados)."""
        try:
            from app.models.portfolio import PortfolioItem
            count = PortfolioItem.query.filter_by(
                pds_id=self.pds_id, estado='aprobado'
            ).count()
            return min(count / 10, 1.0)  # Max 10 items = 1.0
        except Exception:
            return 0.0
    
    def _contar_contratos(self):
        """Cuenta contratos completados."""
        try:
            from app.models.contract import Contract
            return Contract.query.filter(
                Contract.proveedor_id == self.pds_id,
                Contract.estado == 'completado'
            ).count()
        except Exception:
            return 0
    
    def _contar_referidos(self):
        """Cuenta referidos activos."""
        # Placeholder — implementar con tabla de referidos
        return 0
    
    @classmethod
    def get_or_create(cls, pds_id: int):
        """Obtiene o crea un TrustScore para un proveedor.
        
        Args:
            pds_id: ID del usuario proveedor
            
        Returns:
            Instancia de TrustScore
            
        Example:
            >>> trust = TrustScore.get_or_create(pds_id=42)
            >>> trust.calcular()
        """
        trust = cls.query.filter_by(pds_id=pds_id).first()
        if not trust:
            trust = cls(pds_id=pds_id)
            db.session.add(trust)
            db.session.commit()
        return trust
    
    @classmethod
    def recalculate_all(cls):
        """Recalcula todos los trust scores (tarea Celery)."""
        from app.models.user import User, RolUsuario
        
        pds_users = User.query.filter_by(rol=RolUsuario.PDS).all()
        count = 0
        
        for user in pds_users:
            trust = cls.get_or_create(pds_id=user.id)
            trust.calcular()
            count += 1
        
        return count
    
    def __repr__(self):
        return f'<TrustScore pds_id={self.pds_id} score={self.puntuacion} nivel={self.nivel}>'
