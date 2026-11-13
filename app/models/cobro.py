"""Tarifas de cobro en monedas (configurables por el superadmin)."""

from datetime import datetime, timezone

from app.extensions import db

# Valores iniciales; el superadmin puede cambiarlos desde el panel.
TARIFAS_DEFAULT = {
    "pct_contrato": 3.0,
    "precio_moneda_cop": 100.0,
    "monedas_fijas": 1.0,
    "min_monedas_contrato": 10.0,
    "costo_publicar_anuncio": 10.0,
    "costo_reactivar_anuncio": 5.0,
}


class TarifaCobro(db.Model):
    """Precio unitario de una acción cobrada en monedas."""

    __tablename__ = "tarifas_cobro"

    clave = db.Column(db.String(50), primary_key=True)
    valor = db.Column(db.Float, nullable=False)
    descripcion = db.Column(db.String(255), nullable=True)
    actualizado_en = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    actualizado_por = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True
    )

    def __repr__(self):
        return f"<TarifaCobro {self.clave}={self.valor}>"
