"""Cobros en monedas: tarifas, cálculo y movimientos.

Reglas (configurables por el superadmin):
- Contratos: un único porcentaje para ambas partes.
- monedas = trunc((monto * % / 100) / precio_moneda) + monedas_fijas
  con un mínimo por parte.
- Anuncios: costo fijo por publicar / reactivar.
"""

from math import trunc

from app.extensions import db
from app.models.cobro import TARIFAS_DEFAULT, TarifaCobro
from app.models.wallet import PaqueteMonedas
from app.services.wallet import reembolsar_monedas, usar_monedas

__all__ = [
    "get_tarifas",
    "get_tarifa",
    "get_config_publica",
    "actualizar_tarifas",
    "calcular_monedas_contrato",
    "costo_anuncio",
    "cobrar_monedas",
    "reembolsar_monedas",
]


def get_tarifas() -> dict[str, float]:
    """Todas las tarifas (con defaults para claves faltantes)."""
    valores = {clave: float(valor) for clave, valor in TARIFAS_DEFAULT.items()}
    for tarifa in TarifaCobro.query.all():
        valores[tarifa.clave] = float(tarifa.valor)
    return valores


def get_tarifa(clave: str, default: float = 0.0) -> float:
    tarifa = db.session.get(TarifaCobro, clave)
    if tarifa is not None:
        return float(tarifa.valor)
    return float(TARIFAS_DEFAULT.get(clave, default))


def get_config_publica() -> dict:
    """Config necesaria para mostrar precios en el frontend."""
    valores = get_tarifas()
    return {
        "pct_contrato": valores.get("pct_contrato", 3.0),
        "precio_moneda_cop": int(valores.get("precio_moneda_cop", 100)),
        "monedas_fijas": int(valores.get("monedas_fijas", 1)),
        "min_monedas_contrato": int(valores.get("min_monedas_contrato", 10)),
        "costo_publicar_anuncio": int(valores.get("costo_publicar_anuncio", 10)),
        "costo_reactivar_anuncio": int(
            valores.get("costo_reactivar_anuncio", 5)
        ),
    }


def actualizar_tarifas(data: dict, user_id: int | None = None) -> dict[str, float]:
    """Actualiza las tarifas. Si cambia el precio de la moneda, recalcula
    el precio en COP de todos los paquetes."""
    precio_anterior = get_tarifa("precio_moneda_cop", 100)

    for clave, valor in data.items():
        if clave not in TARIFAS_DEFAULT:
            continue
        numero = float(valor)
        if numero < 0:
            raise ValueError(f"La tarifa '{clave}' no puede ser negativa.")
        if clave == "precio_moneda_cop" and numero < 1:
            raise ValueError("El precio de la moneda debe ser mayor que 0.")
        if clave == "pct_contrato" and numero > 100:
            raise ValueError("El porcentaje no puede superar 100%.")

        tarifa = db.session.get(TarifaCobro, clave)
        if tarifa is None:
            tarifa = TarifaCobro(clave=clave, valor=numero)
            db.session.add(tarifa)
        else:
            tarifa.valor = numero
        tarifa.actualizado_por = user_id

    db.session.flush()

    nuevo_precio = get_tarifa("precio_moneda_cop", 100)
    if nuevo_precio != precio_anterior:
        recalcular_precios_paquetes(nuevo_precio)

    db.session.commit()
    return get_tarifas()


def recalcular_precios_paquetes(precio_moneda_cop: float) -> int:
    """Recalcula el precio COP de cada paquete: monedas base × precio.

    El `bonus` sigue siendo monedas de regalo. Las ofertas manuales
    (`precio_oferta_cop`) se conservan tal cual.
    """
    precio = max(1, int(round(precio_moneda_cop)))
    paquetes = PaqueteMonedas.query.all()
    for paquete in paquetes:
        paquete.precio_cop = max(1, int(paquete.cantidad) * precio)
    db.session.flush()
    return len(paquetes)


def calcular_monedas_contrato(monto) -> int:
    """Monedas que paga CADA parte al firmar un contrato."""
    monto_num = max(0.0, float(monto or 0))
    pct = get_tarifa("pct_contrato", 3.0)
    precio = max(1.0, get_tarifa("precio_moneda_cop", 100))
    fijas = max(0, int(get_tarifa("monedas_fijas", 1)))
    minimo = max(1, int(get_tarifa("min_monedas_contrato", 10)))

    monedas = trunc((monto_num * pct / 100.0) / precio) + fijas
    return max(minimo, monedas)


def costo_anuncio(accion: str) -> int:
    """Costo en monedas de publicar o reactivar un anuncio."""
    clave = (
        "costo_reactivar_anuncio"
        if accion == "reactivar"
        else "costo_publicar_anuncio"
    )
    return max(0, int(get_tarifa(clave, 0)))


def cobrar_monedas(
    user_id: int,
    cantidad: int,
    referencia: str,
    descripcion: str,
) -> bool:
    """Cobra monedas de forma idempotente. Lanza ValueError si no alcanza."""
    return usar_monedas(
        user_id,
        cantidad,
        motivo=descripcion,
        referencia=referencia,
    )
