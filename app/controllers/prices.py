"""Routes: precios sugeridos por categoría (RF-28).

Endpoints (prefijo /api/v1):
  GET /precios/<categoria>    -> precios sugeridos para una categoría
  GET /precios                -> todas las categorías con precios promedio
"""

from flask.views import MethodView
from flask_smorest import Blueprint, abort

from app.extensions import db, cache
from app.models.solicitud import Solicitud, EstadoSolicitud
from app.schemas.prices import PriceSuggestionSchema, AllPricesSchema

blp = Blueprint("prices", __name__, description="Precios sugeridos (RF-28)")

# Categorías válidas con sus precios base (COP)
PRECIOS_BASE = {
    "plomeria": {"min": 50000, "max": 300000, "promedio": 150000},
    "electricidad": {"min": 60000, "max": 350000, "promedio": 180000},
    "pintura": {"min": 40000, "max": 250000, "promedio": 120000},
    "carpinteria": {"min": 80000, "max": 500000, "promedio": 250000},
    "cerrajeria": {"min": 70000, "max": 400000, "promedio": 200000},
    "limpieza": {"min": 30000, "max": 200000, "promedio": 100000},
    "jardineria": {"min": 40000, "max": 250000, "promedio": 120000},
    "mecanica": {"min": 60000, "max": 400000, "promedio": 200000},
    "tecnologia": {"min": 80000, "max": 500000, "promedio": 250000},
    "otros": {"min": 50000, "max": 300000, "promedio": 150000},
}


def _calcular_precios_reales(categoria: str) -> dict:
    """Calcula precios reales basados en solicitudes completadas de la categoría."""
    solicitudes = Solicitud.query.filter(
        Solicitud.categoria == categoria,
        Solicitud.estado == EstadoSolicitud.COMPLETADO,
        Solicitud.presupuesto.isnot(None),
        Solicitud.presupuesto > 0,
    ).all()

    if not solicitudes:
        return PRECIOS_BASE.get(categoria, PRECIOS_BASE["otros"])

    presupuestos = [s.presupuesto for s in solicitudes]
    return {
        "min": min(presupuestos),
        "max": max(presupuestos),
        "promedio": int(sum(presupuestos) / len(presupuestos)),
        "muestra": len(presupuestos),
    }


@blp.route("/precios/<string:categoria>")
class PriceSuggestion(MethodView):
    @blp.response(200, PriceSuggestionSchema)
    @cache.cached(timeout=3600, query_string=True)
    def get(self, categoria):
        """RF-28: Obtiene precios sugeridos para una categoría específica."""
        if categoria not in PRECIOS_BASE:
            abort(404, message=f"Categoría no válida: {categoria}")

        precios = _calcular_precios_reales(categoria)

        return {
            "categoria": categoria,
            "min": precios["min"],
            "max": precios["max"],
            "promedio": precios["promedio"],
            "muestra": precios.get("muestra", 0),
            "moneda": "COP",
            "fuente": "solicitudes_completadas" if precios.get("muestra", 0) > 0 else "estimacion_base",
        }


@blp.route("/precios")
class AllPrices(MethodView):
    @blp.response(200, AllPricesSchema)
    @cache.cached(timeout=3600)
    def get(self):
        """RF-28: Obtiene precios sugeridos para todas las categorías."""
        resultados = {}
        for cat in PRECIOS_BASE:
            precios = _calcular_precios_reales(cat)
            resultados[cat] = {
                "min": precios["min"],
                "max": precios["max"],
                "promedio": precios["promedio"],
                "muestra": precios.get("muestra", 0),
            }

        return {
            "categorias": resultados,
            "moneda": "COP",
            "total_categorias": len(resultados),
        }
