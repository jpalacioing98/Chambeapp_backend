"""Servicio de analítica histórica: lee `metrics_daily` y
`metrics_segment_monthly` y entrega las estructuras que consume el dashboard.
"""

from datetime import date, timedelta

from sqlalchemy import func

from app.extensions import db
from app.models.metrics import MetricsDaily, MetricsSegmentMonthly

MONTHS_ES = [
    "Ene", "Feb", "Mar", "Abr", "May", "Jun",
    "Jul", "Ago", "Sep", "Oct", "Nov", "Dic",
]

HEAT_ROWS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
HEAT_COLS = ["6–9", "9–12", "12–15", "15–18", "18–21", "21–24"]
HEAT_WEIGHTS = [0.14, 0.2, 0.16, 0.2, 0.22, 0.08]

PALETTE_GENERO = {
    "Hombres": "#6366f1",
    "Mujeres": "#ec4899",
    "No especifica": "#94a3b8",
}


def _series(rows, field):
    return [int(getattr(r, field) or 0) for r in rows]


def get_history(days: int = 180) -> dict:
    """Histórico diario + agregados mensuales."""
    days = max(1, min(int(days), 366))
    rows = (
        MetricsDaily.query.order_by(MetricsDaily.fecha.desc())
        .limit(days)
        .all()
    )
    rows = list(reversed(rows))

    buckets = {}
    for r in rows:
        key = (r.fecha.year, r.fecha.month)
        b = buckets.setdefault(key, {
            "label": MONTHS_ES[r.fecha.month - 1],
            "key": f"{r.fecha.year}-{r.fecha.month:02d}",
            "contratos": 0, "solicitudes": 0, "ofertas": 0,
            "ingresos_cop": 0, "comisiones_cop": 0, "usuarios_nuevos": 0,
            "afiliaciones": 0, "certificados": 0, "alertas_enviadas": 0,
            "monedas_ganadas": 0, "monedas_gastadas": 0, "paquetes_vendidos": 0,
            "disputas": 0, "evasion": 0, "first_offer_sum": 0, "days": 0,
        })
        b["contratos"] += r.contratos
        b["solicitudes"] += r.solicitudes
        b["ofertas"] += r.ofertas
        b["ingresos_cop"] += r.ingresos_cop
        b["comisiones_cop"] += r.comisiones_cop
        b["usuarios_nuevos"] += r.usuarios_nuevos
        b["afiliaciones"] += r.afiliaciones
        b["certificados"] += r.certificados
        b["alertas_enviadas"] += r.alertas_enviadas
        b["monedas_ganadas"] += r.monedas_ganadas
        b["monedas_gastadas"] += r.monedas_gastadas
        b["paquetes_vendidos"] += r.paquetes_vendidos
        b["disputas"] += r.disputas
        b["evasion"] += r.evasion
        b["first_offer_sum"] += r.tiempo_primera_oferta_min
        b["days"] += 1

    monthly = []
    for _, b in sorted(buckets.items()):
        b["first_offer_avg"] = round(b.pop("first_offer_sum") / max(1, b["days"]))
        monthly.append(b)
    monthly = monthly[-6:]  # exactamente 6 meses para gráficas

    return {
        "days": len(rows),
        "daily": [
            {
                "date": r.fecha.isoformat(),
                "contratos": r.contratos,
                "solicitudes": r.solicitudes,
                "ofertas": r.ofertas,
                "ingresos_cop": r.ingresos_cop,
                "comisiones_cop": r.comisiones_cop,
                "usuarios_nuevos": r.usuarios_nuevos,
                "kyc_aprobados": r.kyc_aprobados,
                "monedas_ganadas": r.monedas_ganadas,
                "monedas_gastadas": r.monedas_gastadas,
                "paquetes_vendidos": r.paquetes_vendidos,
                "alertas_enviadas": r.alertas_enviadas,
                "afiliaciones": r.afiliaciones,
                "certificados": r.certificados,
                "disputas": r.disputas,
                "evasion": r.evasion,
                "tiempo_primera_oferta_min": r.tiempo_primera_oferta_min,
                "pds_activos": r.pds_activos,
                "solicitantes_activos": r.solicitantes_activos,
            }
            for r in rows
        ],
        "months": [m["label"] for m in monthly],
        "monthly": monthly,
        "timeSeries": {
            "contracts": _series(rows, "contratos"),
            "requests": _series(rows, "solicitudes"),
            "offers": _series(rows, "ofertas"),
            "revenue": _series(rows, "ingresos_cop"),
            "latency": _series(rows, "tiempo_primera_oferta_min"),
            "newUsers": _series(rows, "usuarios_nuevos"),
            "kycApproved": _series(rows, "kyc_aprobados"),
            "coinsEarned": _series(rows, "monedas_ganadas"),
            "coinsSpent": _series(rows, "monedas_gastadas"),
            "packagesSold": _series(rows, "paquetes_vendidos"),
            "affiliations": _series(rows, "afiliaciones"),
            "certificates": _series(rows, "certificados"),
            "disputes": _series(rows, "disputas"),
            "monthlyContracts": [m["contratos"] for m in monthly],
            "monthlyRevenue": [m["ingresos_cop"] for m in monthly],
            "monthlyRequests": [m["solicitudes"] for m in monthly],
            "monthlyAffiliations": [m["afiliaciones"] for m in monthly],
            "monthlyCertificates": [m["certificados"] for m in monthly],
            "monthlyCredits": [0 for _ in monthly],
        },
    }


def _latest_period():
    return db.session.query(func.max(MetricsSegmentMonthly.periodo)).scalar()


def _segment_rows(metrica: str, dimension: str):
    period = _latest_period()
    if period is None:
        return []
    return (
        MetricsSegmentMonthly.query.filter_by(
            periodo=period, metrica=metrica, dimension=dimension
        )
        .order_by(MetricsSegmentMonthly.valor.desc())
        .all()
    )


def _pct_rows(rows):
    total = sum(r.valor for r in rows) or 1
    return [
        {"label": r.dimension_valor, "value": round((r.valor / total) * 100, 1)}
        for r in rows
    ]


def get_distributions() -> dict:
    """Estructura de distribuciones para las gráficas del dashboard."""
    history = get_history(180)
    daily = MetricsDaily.query.order_by(MetricsDaily.fecha.asc()).limit(180).all()

    # Heatmap: reparte solicitudes por día de semana y franja
    values = [[0.0] * len(HEAT_COLS) for _ in HEAT_ROWS]
    for r in daily:
        ri = r.fecha.weekday()
        for ci, w in enumerate(HEAT_WEIGHTS):
            values[ri][ci] += r.solicitudes * w
    values = [[int(round(v)) for v in row] for row in values]

    region_pds = {r.dimension_valor: r.valor for r in _segment_rows("pds_activos", "region")}
    region_sol = {r.dimension_valor: r.valor for r in _segment_rows("solicitantes_activos", "region")}
    region_mer = {r.dimension_valor: r.valor for r in _segment_rows("merchants_activos", "region")}
    region_labels = list(dict.fromkeys(
        list(region_pds.keys()) + list(region_sol.keys()) + list(region_mer.keys())
    ))
    regions = [
        {
            "label": label,
            "value": int(round(region_pds.get(label, 0))),
            "sol": int(round(region_sol.get(label, 0))),
            "mer": int(round(region_mer.get(label, 0))),
        }
        for label in region_labels
    ] or [{"label": "Sin datos", "value": 0, "sol": 0, "mer": 0}]

    return {
        "regions": regions,
        "merchantFormality": _pct_rows(_segment_rows("merchants_activos", "formalidad")),
        "distances": _pct_rows(_segment_rows("solicitudes", "distancia")),
        "firstOffer": _pct_rows(_segment_rows("solicitudes", "primera_oferta")),
        "kycReview": _pct_rows(_segment_rows("solicitudes", "revision_kyc")),
        "contractSign": _pct_rows(_segment_rows("solicitudes", "firma")),
        "gender": [
            {**row, "color": PALETTE_GENERO.get(row["label"], "#94a3b8")}
            for row in _pct_rows(_segment_rows("solicitantes_activos", "genero"))
        ],
        "age": _pct_rows(_segment_rows("solicitantes_activos", "edad")),
        "activity": {"rows": HEAT_ROWS, "cols": HEAT_COLS, "values": values},
        "months": history["months"],
        "monthly": history["monthly"],
        "timeSeries": {
            **history["timeSeries"],
            "days": history["days"],
        },
    }


def get_segment(metrica: str, dimension: str) -> list:
    """Desagregación de una métrica por dimensión en el último mes."""
    rows = _segment_rows(metrica, dimension)
    return _pct_rows(rows)
