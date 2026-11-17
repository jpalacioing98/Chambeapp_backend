"""Siembra idempotente de analítica histórica (180 días + 6 meses).

Crea las tablas si no existen (compatibilidad con el flujo de Docker que usa
`flask db stamp head` en lugar de `upgrade`) e inserta los históricos solo si
están vacíos. Pensado para ejecutarse al arrancar el contenedor.

Uso:
    python seed_metrics_history.py
"""

from datetime import date, datetime, timedelta, timezone
import math
import random

from app import create_app
from app.extensions import db
from app.models.metrics import MetricsDaily, MetricsSegmentMonthly

DIMENSIONS = {
    "region": [
        "Valledupar Centro", "Valledupar Periferia", "La Mesa",
        "Patillal", "Badillo", "Sincelejo", "Riohacha",
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


def seed_daily() -> int:
    if db.session.query(MetricsDaily.id).first() is not None:
        return 0

    rnd = random.Random(20260115)
    end = date.today()
    days = 180
    now = datetime.now(timezone.utc)
    rows = []

    for i in range(days - 1, -1, -1):
        d = end - timedelta(days=i)
        t = (days - 1 - i) / (days - 1)
        growth = 0.72 + t * 0.56
        dow = d.weekday()
        weekend = 0.74 if dow == 6 else 0.86 if dow == 5 else 1.0
        seasonal = 1 + 0.09 * math.sin((i / 30) * 6.28318)
        scale = growth * weekend * seasonal * (0.84 + rnd.random() * 0.32)

        contratos = round(30 * scale)
        solicitudes = round(56 * scale)
        ofertas = round(104 * scale)
        ingresos = round(1450000 * scale)
        comisiones = round(ingresos * 0.115)
        usuarios = round(26 * scale)
        kyc_ok = round(16 * scale)
        kyc_pend = round(18 * (0.7 + rnd.random() * 0.7))
        ganadas = round(contratos * 10 * (0.9 + rnd.random() * 0.2))
        gastadas = round(900 * scale)
        paquetes = round(14 * scale)
        alertas = round(10 * scale)
        afiliaciones = round(4 * scale)
        certificados = round(2 * scale)
        disputas = 1 if rnd.random() > 0.8 else 0
        evasion = 1 if rnd.random() > 0.86 else 0
        primera = round(22 + (1 - t) * 55 + rnd.random() * 35)
        pds = round(22 * growth * (0.95 + rnd.random() * 0.1))
        sol = round(26 * growth * (0.95 + rnd.random() * 0.1))

        rows.append(MetricsDaily(
            fecha=d,
            contratos=contratos,
            solicitudes=solicitudes,
            ofertas=ofertas,
            ingresos_cop=ingresos,
            comisiones_cop=comisiones,
            usuarios_nuevos=usuarios,
            kyc_aprobados=kyc_ok,
            kyc_pendientes=kyc_pend,
            monedas_ganadas=ganadas,
            monedas_gastadas=gastadas,
            paquetes_vendidos=paquetes,
            alertas_enviadas=alertas,
            afiliaciones=afiliaciones,
            certificados=certificados,
            disputas=disputas,
            evasion=evasion,
            tiempo_primera_oferta_min=primera,
            pds_activos=pds,
            solicitantes_activos=sol,
            creado_en=now,
        ))

    db.session.add_all(rows)
    db.session.commit()
    return len(rows)


def seed_segments() -> int:
    if db.session.query(MetricsSegmentMonthly.id).first() is not None:
        return 0

    rnd = random.Random(20260201)
    current = _first_of_month(date.today())
    periods = [_add_months(current, -i) for i in range(5, -1, -1)]
    now = datetime.now(timezone.utc)

    base_by_metric = {
        "contratos": 900,
        "solicitudes": 1700,
        "ingresos_cop": 43000000,
        "pds_activos": 640,
        "solicitantes_activos": 700,
        "merchants_activos": 180,
        "anuncios": 90,
        "kyc_aprobados": 480,
    }

    rows = []
    for idx, periodo in enumerate(periods):
        growth = 0.72 + (idx / max(1, len(periods) - 1)) * 0.56
        for metrica, base in base_by_metric.items():
            base_val = base * growth
            for dimension, values in DIMENSIONS.items():
                fixed = FIXED_WEIGHTS.get(dimension)
                if fixed and len(fixed) == len(values):
                    weights = list(fixed)
                else:
                    weights = [0.15 + rnd.random() for _ in values]
                total = sum(weights)
                for value, w in zip(values, weights):
                    rows.append(MetricsSegmentMonthly(
                        periodo=periodo,
                        metrica=metrica,
                        dimension=dimension,
                        dimension_valor=value,
                        valor=round(base_val * (w / total), 2),
                        creado_en=now,
                    ))

    db.session.add_all(rows)
    db.session.commit()
    return len(rows)


def main() -> None:
    app = create_app()
    with app.app_context():
        try:
            db.create_all()
        except Exception as exc:  # esquema ya existente / extensiones
            print(f"[seed-metrics] aviso create_all: {exc}")

        daily = seed_daily()
        segments = seed_segments()
        total_daily = db.session.query(MetricsDaily).count()
        total_seg = db.session.query(MetricsSegmentMonthly).count()
        print(
            "[seed-metrics] insertados: "
            f"daily={daily} segments={segments} | "
            f"totales: daily={total_daily} segments={total_seg}"
        )


if __name__ == "__main__":
    main()
