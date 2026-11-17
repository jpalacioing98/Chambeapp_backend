"""Modelos de analítica histórica (6 meses) para el dashboard.

`MetricsDaily` guarda los agregados diarios globales.
`MetricsSegmentMonthly` guarda desagregaciones mensuales por dimensión
(región, oficio, género, edad, cohorte, etc.).
"""

from datetime import datetime, timezone

from app.extensions import db


class MetricsDaily(db.Model):
    __tablename__ = "metrics_daily"

    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, unique=True, nullable=False, index=True)

    contratos = db.Column(db.Integer, nullable=False, default=0)
    solicitudes = db.Column(db.Integer, nullable=False, default=0)
    ofertas = db.Column(db.Integer, nullable=False, default=0)
    ingresos_cop = db.Column(db.BigInteger, nullable=False, default=0)
    comisiones_cop = db.Column(db.BigInteger, nullable=False, default=0)
    usuarios_nuevos = db.Column(db.Integer, nullable=False, default=0)
    kyc_aprobados = db.Column(db.Integer, nullable=False, default=0)
    kyc_pendientes = db.Column(db.Integer, nullable=False, default=0)
    monedas_ganadas = db.Column(db.Integer, nullable=False, default=0)
    monedas_gastadas = db.Column(db.Integer, nullable=False, default=0)
    paquetes_vendidos = db.Column(db.Integer, nullable=False, default=0)
    alertas_enviadas = db.Column(db.Integer, nullable=False, default=0)
    afiliaciones = db.Column(db.Integer, nullable=False, default=0)
    certificados = db.Column(db.Integer, nullable=False, default=0)
    disputas = db.Column(db.Integer, nullable=False, default=0)
    evasion = db.Column(db.Integer, nullable=False, default=0)
    tiempo_primera_oferta_min = db.Column(db.Integer, nullable=False, default=0)
    pds_activos = db.Column(db.Integer, nullable=False, default=0)
    solicitantes_activos = db.Column(db.Integer, nullable=False, default=0)

    creado_en = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self):
        return f"<MetricsDaily {self.fecha} contratos={self.contratos}>"


class MetricsSegmentMonthly(db.Model):
    __tablename__ = "metrics_segment_monthly"
    __table_args__ = (
        db.Index(
            "ix_metrics_segment_lookup",
            "periodo",
            "metrica",
            "dimension",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    periodo = db.Column(db.Date, nullable=False, index=True)  # primer día del mes
    metrica = db.Column(db.String(60), nullable=False)  # p.ej. "contratos"
    dimension = db.Column(db.String(40), nullable=False)  # region | oficio | genero ...
    dimension_valor = db.Column(db.String(80), nullable=False)
    valor = db.Column(db.Float, nullable=False, default=0)

    creado_en = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self):
        return (
            f"<MetricsSegmentMonthly {self.periodo} {self.metrica} "
            f"{self.dimension}={self.dimension_valor} {self.valor}>"
        )
