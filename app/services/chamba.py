"""Lógica de negocio del Módulo de Gestión de Chamba.

Máquina de estados, validación geoespacial (PostGIS en prod, Haversine en
tests) y operaciones sobre el expediente de la chamba (evidencias, adendas,
novedades, pago directo, calificación).
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import text

from app.ai.geo import haversine_km, is_postgis
from app.extensions import db, socketio
from app.models.chamba import Chamba, EstadoChamba

logger = logging.getLogger(__name__)

# Radio de validación de llegada al sitio (hito 2): 100 m.
RADIO_VALIDACION_KM = 0.1

TRANSICIONES_VALIDAS = {
    EstadoChamba.PROGRAMADA: {EstadoChamba.EN_PROCESO},
    EstadoChamba.EN_PROCESO: {EstadoChamba.EN_EJECUCION, EstadoChamba.PAUSADA},
    EstadoChamba.EN_EJECUCION: {
        EstadoChamba.PENDIENTE_VALIDACION,
        EstadoChamba.PAUSADA,
    },
    # Reanudación tras pánico: se restaura al estado previo si es válido.
    EstadoChamba.PAUSADA: {EstadoChamba.EN_PROCESO, EstadoChamba.EN_EJECUCION},
    EstadoChamba.PENDIENTE_VALIDACION: {EstadoChamba.LIQUIDACION_CONFIRMADA},
    EstadoChamba.LIQUIDACION_CONFIRMADA: set(),  # → FINALIZADA vía calificación
    EstadoChamba.FINALIZADA: set(),
}


def validar_transicion(actual: EstadoChamba, nuevo: EstadoChamba) -> bool:
    """Valida que la transición de estado sea legal según la máquina."""
    return nuevo in TRANSICIONES_VALIDAS.get(actual, set())


def verificar_geoposicion(lat: float, lng: float, lat_ref: float, lng_ref: float,
                          radio_km: float = RADIO_VALIDACION_KM) -> bool:
    """Verifica que un punto GPS esté dentro del radio del sitio de trabajo.

    Usa PostGIS (ST_DistanceSphere) en producción/dev y Haversine en tests
    (SQLite), igual que app/ai/geo.py.
    """
    if is_postgis():
        try:
            distancia_m = db.session.execute(
                text(
                    "SELECT ST_DistanceSphere("
                    "ST_SetSRID(ST_MakePoint(:lng, :lat), 4326), "
                    "ST_SetSRID(ST_MakePoint(:lng_ref, :lat_ref), 4326))"
                ),
                {"lng": lng, "lat": lat, "lng_ref": lng_ref, "lat_ref": lat_ref},
            ).scalar()
            return float(distancia_m) <= radio_km * 1000
        except Exception:
            logger.exception("Fallo el cálculo PostGIS; fallback a Haversine")
    return haversine_km(lat, lng, lat_ref, lng_ref) <= radio_km


def registrar_evidencia(chamba: Chamba, tipo: str, urls: list[str]) -> Chamba:
    """Registra URLs de evidencia de entrada o salida."""
    urls = [u for u in urls if u]
    if tipo == "entrada":
        chamba.evidencia_entrada = list(chamba.evidencia_entrada or []) + urls
    elif tipo == "salida":
        chamba.evidencia_salida = list(chamba.evidencia_salida or []) + urls
    return chamba


def agregar_adenda(chamba: Chamba, descripcion: str,
                   monto_extra=None, tiempo_extra=None,
                   tiempo_extra_unidad="minutos",
                   cubierta_por="pds_actual", categoria_requerida=None,
                   sugerida_por_pds=False) -> Chamba:
    """Registra una adenda al contrato negociada durante la ejecución.

    `cubierta_por`: quién hace el trabajo — "pds_actual" (la cubre el
    prestador de la chamba) u "otro_pds" (perfil distinto → candidata a
    maraña/rebusque con `categoria_requerida`).
    `sugerida_por_pds`: el prestador propuso trabajo de otro perfil; la
    decisión de lanzarla como maraña es del solicitante.
    `tiempo_extra_unidad`: minutos | horas | dias (default minutos).
    """
    adendas = list(chamba.adendas or [])
    adendas.append({
        "fecha": datetime.now(timezone.utc).isoformat(),
        "descripcion": descripcion,
        "monto_extra": monto_extra,
        "tiempo_extra": tiempo_extra,
        "tiempo_extra_unidad": tiempo_extra_unidad,
        "cubierta_por": cubierta_por,
        "categoria_requerida": categoria_requerida,
        "sugerida_por_pds": sugerida_por_pds,
    })
    chamba.adendas = adendas
    return chamba


def agregar_novedad(chamba: Chamba, tipo: str, descripcion: str) -> Chamba:
    """Registra una novedad / incidencia (botón de pánico incluido)."""
    novedades = list(chamba.novedades or [])
    novedades.append({
        "fecha": datetime.now(timezone.utc).isoformat(),
        "tipo": tipo,
        "descripcion": descripcion,
    })
    chamba.novedades = novedades
    return chamba


def confirmar_pago(chamba: Chamba, user_id: int, monto_final=None) -> Chamba:
    """Check-in de pago directo de una de las partes.

    Marca la confirmación del solicitante o del prestador según el user_id.
    Cuando ambas partes confirman, `pago_directo_confirmado` pasa a True.
    """
    contract = chamba.contract
    if user_id == contract.solicitante_id:
        chamba.pago_confirmado_solicitante = True
    elif user_id == contract.proveedor_id:
        chamba.pago_confirmado_prestador = True
    if monto_final is not None:
        chamba.pago_monto_final = monto_final
    if chamba.pago_confirmado_solicitante and chamba.pago_confirmado_prestador:
        chamba.pago_directo_confirmado = True
    return chamba


def finalizar_chamba(chamba: Chamba, estrellas: int, comentario=None,
                     habilidades=None) -> Chamba:
    """Cierra la chamba: guarda calificación y estado final.

    `habilidades` es opcional: si no llega, se CONSERVAN las habilidades
    ya validadas en la revisión (Hito 4). La liquidación solo notifica el
    pago.
    """
    chamba.rating_estrellas = estrellas
    chamba.rating_comentario = comentario
    if habilidades is not None:
        chamba.habilidades_validadas = list(habilidades)
    chamba.estado = EstadoChamba.FINALIZADA
    chamba.estado_previo = None
    chamba.fecha_finalizacion = datetime.now(timezone.utc)
    return chamba


def emitir_actualizacion(chamba: Chamba) -> None:
    """Notifica en tiempo real (socket) a ambos participantes de la chamba."""
    payload = {
        "chamba_id": chamba.id,
        "contract_id": chamba.contract_id,
        "estado": chamba.estado.value,
        "pago_directo_confirmado": chamba.pago_directo_confirmado,
        "actualizado_en": (
            chamba.actualizado_en.isoformat() if chamba.actualizado_en else None
        ),
    }
    contract = chamba.contract
    socketio.emit("chamba:actualizado", payload, room=f"user:{contract.solicitante_id}")
    socketio.emit("chamba:actualizado", payload, room=f"user:{contract.proveedor_id}")