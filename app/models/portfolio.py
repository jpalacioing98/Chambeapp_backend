"""PortfolioItem — Items del portafolio del proveedor.

Este modelo representa los items (fotos, videos, documentos) que un
proveedor sube para validar su experiencia y construir confianza.

Uso:
    from app.models.portfolio import PortfolioItem

    item = PortfolioItem(
        pds_id=42,
        titulo='Reparación de tubería',
        tipo='foto',
        categoria='plomeria',
        s3_key='portfolio/42/trabajo1.webp',
        url='http://minio:9000/chambeapp-portfolio/portfolio/42/trabajo1.webp'
    )
    db.session.add(item)
    db.session.commit()
"""

from datetime import datetime
from app.extensions import db


class PortfolioItem(db.Model):
    """Item del portafolio del proveedor.
    
    Attributes:
        pds_id: ID del usuario proveedor
        titulo: Título del item
        descripcion: Descripción opcional
        tipo: 'foto', 'video', 'documento'
        categoria: Categoría del trabajo (ej. 'plomeria')
        s3_key: Clave en el bucket S3/MinIO
        url: URL pública del archivo
        file_size_bytes: Tamaño del archivo
        mime_type: Tipo MIME
        estado: 'pendiente_revision', 'aprobado', 'rechazado'
        verificado_por: ID del admin que verificó
        verificado_en: Fecha de verificación
        vistas: Contador de vistas
        created_at: Fecha de creación
    """
    
    __tablename__ = 'portfolio_items'
    
    id = db.Column(db.Integer, primary_key=True)
    pds_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    titulo = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.String(500))
    tipo = db.Column(
        db.Enum('foto', 'video', 'documento', name='portfolio_tipo'),
        nullable=False
    )
    categoria = db.Column(db.String(50), nullable=False)
    
    # Storage
    s3_key = db.Column(db.String(500), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    file_size_bytes = db.Column(db.BigInteger)
    mime_type = db.Column(db.String(50))
    
    # Moderación
    estado = db.Column(
        db.Enum('pendiente_revision', 'aprobado', 'rechazado', name='portfolio_estado'),
        default='pendiente_revision'
    )
    verificado_por = db.Column(db.Integer, db.ForeignKey('users.id'))
    verificado_en = db.Column(db.DateTime)
    
    # Métricas
    vistas = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relaciones
    pds = db.relationship('User', foreign_keys=[pds_id], backref='portfolio_items')
    verificado_por_user = db.relationship('User', foreign_keys=[verificado_por])
    
    # Índices
    __table_args__ = (
        db.Index('ix_portfolio_pds_estado', 'pds_id', 'estado'),
        db.Index('ix_portfolio_categoria', 'categoria'),
    )
    
    def to_dict(self):
        """Convierte el item a dict para serialización."""
        return {
            'id': self.id,
            'pds_id': self.pds_id,
            'titulo': self.titulo,
            'descripcion': self.descripcion,
            'tipo': self.tipo,
            'categoria': self.categoria,
            'url': self.url,
            'file_size_bytes': self.file_size_bytes,
            'mime_type': self.mime_type,
            'estado': self.estado,
            'vistas': self.vistas,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
    
    def increment_views(self):
        """Incrementa el contador de vistas."""
        self.vistas += 1
        db.session.commit()
    
    def approve(self, admin_id: int):
        """Aprueba el item (verificación)."""
        self.estado = 'aprobado'
        self.verificado_por = admin_id
        self.verificado_en = datetime.utcnow()
        db.session.commit()
    
    def reject(self, admin_id: int):
        """Rechaza el item."""
        self.estado = 'rechazado'
        self.verificado_por = admin_id
        self.verificado_en = datetime.utcnow()
        db.session.commit()
    
    @classmethod
    def get_approved_by_pds(cls, pds_id: int):
        """Obtiene items aprobados de un proveedor."""
        return cls.query.filter_by(
            pds_id=pds_id,
            estado='aprobado'
        ).all()
    
    @classmethod
    def get_pending(cls):
        """Obtiene items pendientes de revisión."""
        return cls.query.filter_by(estado='pendiente_revision').all()
    
    def __repr__(self):
        return f'<PortfolioItem id={self.id} pds_id={self.pds_id} tipo={self.tipo}>'
