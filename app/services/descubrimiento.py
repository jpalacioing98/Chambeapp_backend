"""Descubrimiento — elegibilidad y avisos a PDS para una solicitud nueva.

Dos mecanismos complementarios, ambos alimentados por este módulo:

1. **Aviso inmediato** (`notificar_pds_elegibles`): en el mismo request que
   crea la solicitud, avisa a los PDS que realmente califican — perfil
   completo, categoría/habilidad coincidente y dentro del radio. El PDS se
   entera en menos de un segundo, que es lo que espera de "tiempo real".

2. **Cascada por fases** (`app.services.cascade`): si nadie postula, amplía el
   radio (20 → 50 → 100 km) con esperas cortas entre fases.

Ambos reutilizan `pds_elegibles()` para no duplicar la lógica de filtrado.
El criterio de categoría es el mismo que usa el endpoint `?elegibles=1` del
listado de solicitudes (ver `app/controllers/solicitudes.py`), así que un PDS
que ve la solicitud en su panel es exactamente el que recibe el aviso.
"""

import logging

from flask import current_app
from sqlalchemy import or_

from app.ai.geo import find_nearby_providers
from app.extensions import db
from app.models.config import FeatureFlag
from app.models.notification import Notification
from app.schemas.solicitud import SolicitudSchema
from app.services.categorias import normalizar_categoria
from app.services.preferencias import preferencia_permite
from app.services.push import enviar_push_notificacion
from app.services.realtime import safe_emit
from app.services.verificacion import ids_verificados_rol

logger = logging.getLogger(__name__)

# Radio (km) del aviso inmediato. Coincide con la fase 1 de la cascada: lo
# que se avisa de inmediato es el círculo cercano; el resto entra por fases.
RADIO_INMEDIATO_KM = 20.0

# Tope de PDS notificados en el aviso inmediato. Los que queden fuera entran
# por la cascada, que amplía el radio en la fase siguiente.
MAX_NOTIFICADOS_INMEDIATOS = 40

# Tipo de notificación que usa este flujo.
TIPO_NUEVA_SOLICITUD = "nueva_solicitud"


def flag_activo(key: str) -> bool:
    """True si el feature flag está habilitado.

    Bandera maestra: si el flag existe y está apagado, el flujo se desactiva.
    Si no existe (base sin seed), se asume habilitado para que la
    notificación funcione de todos modos.
    """
    flag = FeatureFlag.query.filter_by(key=key).first()
    if flag is None:
        return True
    return bool(flag.enabled)


def categorias_de_perfil(profile) -> set[str]:
    """Categorías + habilidades normalizadas del perfil de un PDS."""
    valores = list(getattr(profile, "categorias", None) or []) + list(
        getattr(profile, "habilidades", None) or []
    )
    return {normalizar_categoria(v) for v in valores if normalizar_categoria(v)}


def coincide_categoria(categoria_solicitud: str, profile) -> bool:
    """True si la categoría de la solicitud califica con el perfil del PDS."""
    categoria = normalizar_categoria(categoria_solicitud)
    if not categoria:
        return False
    permitidas = categorias_de_perfil(profile)
    if not permitidas:
        # Sin habilidades registradas no se filtra: el panel no queda vacío.
        return True
    return categoria in permitidas


def pds_elegibles(
    solicitud,
    radius_km: float | None = None,
    top_k: int | None = None,
    excluir_ids: set[int] | None = None,
) -> list:
    """PDS que califican para la solicitud.

    Filtra por perfil completo (ya viene del query geoespacial), categoría/
    habilidad coincidente y distancia. Devuelve usuarios `User` de rol PDS.
    """
    lat = solicitud.latitud
    lng = solicitud.longitud
    if lat is None or lng is None:
        return []

    radio = float(
        radius_km if radius_km is not None else (solicitud.radio_km or RADIO_INMEDIATO_KM)
    )
    radio = max(1.0, min(radio, 200.0))
    limite = int(top_k if top_k is not None else MAX_NOTIFICADOS_INMEDIATOS)

    # Se piden más candidatos de los necesarios porque el filtro de categoría
    # se aplica en Python (PostGIS no ordena por distancia en esta consulta).
    candidatos = find_nearby_providers(
        lat=lat,
        lng=lng,
        radius_km=radio,
        top_k=min(limite * 5, 500),
    )

    excluidos = excluir_ids or set()

    # Si el PDS necesita verificación para postular, tampoco se le avisa de
    # solicitudes que no podría atender. Se resuelve en bloque (una query).
    verificados: set[int] | None = None
    if current_app.config.get("REQUIRE_KYC_TO_OFFER", True):
        verificados = ids_verificados_rol("pds", [p.id for p in candidatos])

    elegibles = []
    for pds in candidatos:
        if pds.id in excluidos:
            continue
        if verificados is not None and pds.id not in verificados:
            continue
        profile = getattr(pds, "profile", None)
        if profile is None:
            continue
        if not coincide_categoria(solicitud.categoria, profile):
            continue
        elegibles.append(pds)
        if len(elegibles) >= limite:
            break
    return elegibles


def usuarios_notificados(solicitud_id: int) -> set[int]:
    """IDs de PDS ya notificados por esta solicitud (evita duplicados).

    Filtra en SQL por el camino JSON `datos.solicitud_id`. El valor se
    compara en las dos formas en que puede estar almacenado (número o
    texto) porque SQLite devuelve el tipo original de `JSON_EXTRACT`
    mientras Postgres normaliza a texto con `->>`. Si el motor no soporta
    la expresión, cae a un filtrado en Python.
    """
    try:
        filas = (
            Notification.query.with_entities(Notification.user_id)
            .filter(
                Notification.tipo == TIPO_NUEVA_SOLICITUD,
                or_(
                    Notification.datos["solicitud_id"].as_integer() == solicitud_id,
                    Notification.datos["solicitud_id"].as_string() == str(solicitud_id),
                ),
            )
            .all()
        )
        return {user_id for (user_id,) in filas}
    except Exception:  # noqa: BLE001 — el filtro por JSON no debe romper el flujo
        logger.debug(
            "Fallo el filtro JSON de notificaciones; se usa el filtrado en Python",
            exc_info=True,
        )

    try:
        filas = (
            Notification.query.with_entities(
                Notification.user_id, Notification.datos
            )
            .filter(
                Notification.tipo == TIPO_NUEVA_SOLICITUD,
                Notification.datos.isnot(None),
            )
            .all()
        )
    except Exception:  # noqa: BLE001
        logger.warning("No se pudo leer el historial de notificaciones", exc_info=True)
        return set()

    return {
        user_id
        for user_id, datos in filas
        if (datos or {}).get("solicitud_id") == solicitud_id
    }


def _crear_notificacion(solicitud, pds_id: int) -> Notification:
    """Persiste la notificación de "nueva solicitud" para un PDS."""
    categoria = solicitud.categoria or "servicio"
    notif = Notification(
        user_id=pds_id,
        tipo=TIPO_NUEVA_SOLICITUD,
        titulo="Nueva solicitud cerca de ti",
        mensaje=f"Hay una solicitud de {categoria} publicada cerca de ti.",
        datos={
            "solicitud_id": solicitud.id,
            "categoria": solicitud.categoria,
            "radio_km": solicitud.radio_km,
            "origen": "descubrimiento",
        },
    )
    return notif


def notificar_pds_elegibles(solicitud) -> int:
    """Notifica de inmediato a los PDS elegibles por la solicitud.

    Devuelve el número de PDS notificados. No hace commit: la transacción la
    cierra el controller que la invocó.
    """
    if not flag_activo("cascade_notifications"):
        logger.info(
            "Descubrimiento: flag 'cascade_notifications' apagado; se omite el aviso"
        )
        return 0

    if solicitud.latitud is None or solicitud.longitud is None:
        logger.info(
            "Descubrimiento: solicitud %s sin coordenadas; se omite el aviso",
            solicitud.id,
        )
        return 0

    ya_notificados = usuarios_notificados(solicitud.id)
    candidatos = pds_elegibles(
        solicitud,
        radius_km=RADIO_INMEDIATO_KM,
        top_k=MAX_NOTIFICADOS_INMEDIATOS,
        excluir_ids=ya_notificados,
    )
    if not candidatos:
        logger.info("Descubrimiento: sin PDS elegibles para la solicitud %s", solicitud.id)
        return 0

    creadas = []
    for pds in candidatos:
        if not preferencia_permite(pds.id, TIPO_NUEVA_SOLICITUD):
            continue
        notif = _crear_notificacion(solicitud, pds.id)
        db.session.add(notif)
        creadas.append((pds.id, notif))

    # Flush para obtener el id de cada notificación antes de emitirlas.
    db.session.flush()

    payload_solicitud = SolicitudSchema().dump(solicitud)
    for pds_id, notif in creadas:
        safe_emit("notificacion:nueva", notif.to_dict(), room=f"user:{pds_id}")
        # El PDS recibe además la solicitud completa para poder pintar la
        # tarjeta sin esperar un refetch.
        safe_emit("solicitud:creada", payload_solicitud, room=f"user:{pds_id}")
        enviar_push_notificacion(notif)

    logger.info(
        "Descubrimiento: %s PDS notificados de la solicitud %s",
        len(creadas),
        solicitud.id,
    )
    return len(creadas)
