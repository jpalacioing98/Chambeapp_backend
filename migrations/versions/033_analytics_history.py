"""analítica histórica: metrics_daily + metrics_segment_monthly (6 meses)

Revision ID: 033_analytics_history
Revises: 032_formulario_solicitud
Create Date: 2026-11-15

Crea las tablas de analítica y siembra ~180 días de históricos globales y
6 meses de desagregaciones mensuales por dimensión (región, oficio, género,
edad, cohorte). Datos deterministas para que el dashboard tenga volumen.
"""

from datetime import date, datetime, timedelta, timezone
import math
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "033_analytics_history"
down_revision: Union[str, None] = "032_formulario_solicitud"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _rng(seed: int):
    state = seed % 2147483647
    if state <= 0:
        state += 2147483646

    def nxt() -> float:
        nonlocal state
        state = (state * 16807) % 2147483647
        return (state - 1) / 2147483646

    return nxt


def _seed_daily(conn, table) -> int:
    existing = conn.execute(sa.select(sa.func.count()).select_from(table)).scalar() or 0
    if existing:
        return 0

    rnd = _rng(20260115)
    end = date.today()
    days = 180
    now = datetime.now(timezone.utc)
    rows = []
    for i in range(days - 1, -1, -1):
        d = end - timedelta(days=i)
        t = (days - 1 - i) / (days - 1)
        growth = 0.72 + t * 0.56
        dow = d.weekday()  # 0=lunes
        weekend = 0.74 if dow == 6 else 0.86 if dow == 5 else 1.0
        seasonal = 1 + 0.09 * math.sin((i / 30) * 6.28318)
        scale = growth * weekend * seasonal * (0.84 + rnd() * 0.32)

        contratos = round(30 * scale)
        solicitudes = round(56 * scale)
        ofertas = round(104 * scale)
        ingresos = round(1450000 * scale)
        comisiones = round(ingresos * 0.115)
        usuarios = round(26 * scale)
        kyc_ok = round(16 * scale)
        kyc_pend = round(18 * (0.7 + rnd() * 0.7))
        ganadas = round(contratos * 10 * (0.9 + rnd() * 0.2))
        gastadas = round(900 * scale)
        paquetes = round(14 * scale)
        alertas = round(10 * scale)
        afiliaciones = round(4 * scale)
        certificados = round(2 * scale)
        disputas = 1 if rnd() > 0.8 else 0
        evasion = 1 if rnd() > 0.86 else 0
        primera = round(22 + (1 - t) * 55 + rnd() * 35)
        pds = round(22 * growth * (0.95 + rnd() * 0.1))
        sol = round(26 * growth * (0.95 + rnd() * 0.1))

        rows.append({
            "fecha": d,
            "contratos": contratos,
            "solicitudes": solicitudes,
            "ofertas": ofertas,
            "ingresos_cop": ingresos,
            "comisiones_cop": comisiones,
            "usuarios_nuevos": usuarios,
            "kyc_aprobados": kyc_ok,
            "kyc_pendientes": kyc_pend,
            "monedas_ganadas": ganadas,
            "monedas_gastadas": gastadas,
            "paquetes_vendidos": paquetes,
            "alertas_enviadas": alertas,
            "afiliaciones": afiliaciones,
            "certificados": certificados,
            "disputas": disputas,
            "evasion": evasion,
            "tiempo_primera_oferta_min": primera,
            "pds_activos": pds,
            "solicitantes_activos": sol,
            "creado_en": now,
        })

    op.bulk_insert(table, rows)
    return len(rows)


DIMENSIONS = {
    "region": [
        "Valledupar Centro", "Valledupar Periferia", "La Mesa",
        "Patillal", "Badillo",
    ],
    "oficio": [
        "Plomería", "Electricidad", "Pintura", "Jardinería",
        "Aseo", "Carpintería", "Soldadura", "Climatización",
    ],
    "genero": ["Hombres", "Mujeres", "No especifica"],
    "edad": [
        "18–24 años", "25–28 años", "29–35 años",
        "36–45 años", "46–55 años", "56 años o más",
    ],
    "urgencia": ["Para hoy", "Esta semana", "Fecha flexible"],
    "canal": ["Orgánico", "Referido", "Campaña pagada"],
    "distancia": ["0–2 km", "2–5 km", "5–10 km", "10–15 km", "15+ km"],
    "primera_oferta": [
        "Menos de 15 min", "15–30 min", "30 min–2 h",
        "2–4 h", "4–24 h", "Más de 24 h",
    ],
    "revision_kyc": [
        "Menos de 6 h", "6–12 h", "12–24 h", "24–48 h", "Más de 48 h",
    ],
    "firma": [
        "Menos de 1 h", "1–4 h", "4–12 h", "12–24 h", "Más de 24 h",
    ],
    "cohorte": ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio"],
    "formalidad": ["Formal", "Informal"],
}

METRICS = [
    "contratos", "solicitudes", "ingresos_cop",
    "pds_activos", "solicitantes_activos", "merchants_activos",
    "anuncios", "kyc_aprobados",
]

# Pesos realistas para dimensiones demográficas y de comportamiento.
FIXED_WEIGHTS = {
    "genero": [62, 34, 4],
    "edad": [16, 17, 25, 22, 14, 6],
    "urgencia": [38, 40, 22],
    "canal": [52, 27, 21],
    "region": [34, 22, 14, 8, 6, 10, 6],
    "oficio": [26, 20, 14, 12, 10, 8, 6, 4],
    "formalidad": [38, 62],
}


def _first_of_month(d: date) -> date:
    return date(d.year, d.month, 1)


def _add_months(d: date, delta: int) -> date:
    year = d.year + (d.month - 1 + delta) // 12
    month = (d.month - 1 + delta) % 12 + 1
    return date(year, month, 1)


def _seed_segments(conn, table) -> int:
    existing = conn.execute(sa.select(sa.func.count()).select_from(table)).scalar() or 0
    if existing:
        return 0

    rnd = _rng(20260201)
    current = _first_of_month(date.today())
    periods = [_add_months(current, -i) for i in range(5, -1, -1)]
    now = datetime.now(timezone.utc)

    rows = []
    for idx, periodo in enumerate(periods):
        growth = 0.72 + (idx / 5) * 0.56
        for metrica in METRICS:
            base = {
                "contratos": 900,
                "solicitudes": 1700,
                "ingresos_cop": 43000000,
                "pds_activos": 640,
                "solicitantes_activos": 700,
                "merchants_activos": 180,
                "anuncios": 90,
                "kyc_aprobados": 480,
            }[metrica] * growth
            for dimension, values in DIMENSIONS.items():
                fixed = FIXED_WEIGHTS.get(dimension)
                if fixed and len(fixed) == len(values):
                    weights = list(fixed)
                else:
                    weights = [0.15 + rnd() for _ in values]
                total = sum(weights)
                for value, w in zip(values, weights):
                    rows.append({
                        "periodo": periodo,
                        "metrica": metrica,
                        "dimension": dimension,
                        "dimension_valor": value,
                        "valor": round(base * (w / total), 2),
                        "creado_en": now,
                    })

    op.bulk_insert(table, rows)
    return len(rows)


def upgrade() -> None:
    op.create_table(
        "metrics_daily",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fecha", sa.Date(), nullable=False, unique=True),
        sa.Column("contratos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("solicitudes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ofertas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ingresos_cop", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("comisiones_cop", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("usuarios_nuevos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kyc_aprobados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kyc_pendientes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("monedas_ganadas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("monedas_gastadas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("paquetes_vendidos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("alertas_enviadas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("afiliaciones", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("certificados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("disputas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evasion", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tiempo_primera_oferta_min", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pds_activos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("solicitantes_activos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_metrics_daily_fecha", "metrics_daily", ["fecha"])

    op.create_table(
        "metrics_segment_monthly",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("periodo", sa.Date(), nullable=False),
        sa.Column("metrica", sa.String(length=60), nullable=False),
        sa.Column("dimension", sa.String(length=40), nullable=False),
        sa.Column("dimension_valor", sa.String(length=80), nullable=False),
        sa.Column("valor", sa.Float(), nullable=False, server_default="0"),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_metrics_segment_lookup",
        "metrics_segment_monthly",
        ["periodo", "metrica", "dimension"],
    )
    op.create_index(
        "ix_metrics_segment_periodo",
        "metrics_segment_monthly",
        ["periodo"],
    )

    # Sembrado
    metrics_daily = sa.table(
        "metrics_daily",
        *(sa.column(c) for c in [
            "fecha", "contratos", "solicitudes", "ofertas", "ingresos_cop",
            "comisiones_cop", "usuarios_nuevos", "kyc_aprobados", "kyc_pendientes",
            "monedas_ganadas", "monedas_gastadas", "paquetes_vendidos",
            "alertas_enviadas", "afiliaciones", "certificados", "disputas",
            "evasion", "tiempo_primera_oferta_min", "pds_activos",
            "solicitantes_activos", "creado_en",
        ])
    )
    segments = sa.table(
        "metrics_segment_monthly",
        *(sa.column(c) for c in [
            "periodo", "metrica", "dimension", "dimension_valor", "valor", "creado_en",
        ])
    )

    conn = op.get_bind()
    inserted_daily = _seed_daily(conn, metrics_daily)
    inserted_seg = _seed_segments(conn, segments)

    print(f"[033_analytics_history] metrics_daily={inserted_daily} filas; segments={inserted_seg} filas")


def downgrade() -> None:
    op.drop_index("ix_metrics_segment_periodo", table_name="metrics_segment_monthly")
    op.drop_index("ix_metrics_segment_lookup", table_name="metrics_segment_monthly")
    op.drop_table("metrics_segment_monthly")
    op.drop_index("ix_metrics_daily_fecha", table_name="metrics_daily")
    op.drop_table("metrics_daily")
