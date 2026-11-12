"""Web Push notifications (VAPID) — RF-10 / HU-33.

`pywebpush` se importa de forma perezosa: los tests y los entornos sin la
dependencia instalada siguen funcionando (el envío se omite y se registra).
"""

import json
import logging
from functools import lru_cache
from uuid import uuid4

from app.extensions import db
from app.models.config import SystemConfig

log = logging.getLogger(__name__)

VAPID_PUBLIC_KEY = "vapid_public_key"
VAPID_PRIVATE_KEY = "vapid_private_key"
VAPID_SUBJECT = "mailto:soporte@chambeapp.com"

# Todos los tipos apuntan al centro de notificaciones: la página resuelve el
# deep-link exacto según el rol (solicitante / pds / merchant).
DEFAULT_PUSH_URL = "/notificaciones"


def _config_or_env(key: str) -> str | None:
    import os

    env_value = os.environ.get(key.upper())
    if env_value:
        return env_value
    try:
        value = SystemConfig.get_value(key)
    except Exception:  # tabla inexistente en algún test aislado
        return None
    return value or None


def vapid_public_key() -> str | None:
    """Clave pública VAPID en base64url (la que recibe el navegador)."""
    return _config_or_env(VAPID_PUBLIC_KEY)


def vapid_private_key() -> str | None:
    return _config_or_env(VAPID_PRIVATE_KEY)


def push_disponible() -> bool:
    """True si hay claves y `pywebpush` instalado."""
    if not vapid_public_key() or not vapid_private_key():
        return False
    try:
        import pywebpush  # noqa: F401
    except Exception:  # noqa: BLE001 — dependencia opcional
        return False
    return True


@lru_cache(maxsize=2)
def _vapid_privada(pem: str):
    """pywebpush acepta un `Vapid01` o un str base64; NO bytes.

    Nuestra clave se guarda como PEM, así que la convertimos a `Vapid01`
    una sola vez (cacheada).
    """
    from py_vapid import Vapid01

    return Vapid01.from_pem(pem.encode())


def _clave_vapid():
    """Devuelve la clave en el formato que espera `pywebpush.webpush`."""
    private_key = vapid_private_key()
    if not private_key:
        return None
    if "BEGIN" in private_key:
        return _vapid_privada(private_key)
    # Base64url DER/raw ya codificada: se pasa tal cual (str).
    return private_key


def enviar_push(suscripcion, payload: dict) -> bool:
    """Envía un push a UNA suscripción. Devuelve True si se entregó.

    Si el navegador invalidó la suscripción (404/410) la elimina de la sesión
    actual; el commit lo hace el caller para no persistir estados a medias.
    """
    if not push_disponible():
        return False

    from pywebpush import WebPushException, webpush

    try:
        webpush(
            subscription_info=suscripcion.to_subscription_info(),
            data=json.dumps(payload, default=str),
            vapid_private_key=_clave_vapid(),
            vapid_claims={"sub": VAPID_SUBJECT},
            timeout=5,
        )
        return True
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (404, 410):
            db.session.delete(suscripcion)
        log.warning("push_failed status=%s error=%s", status, exc)
        return False
    except Exception as exc:  # noqa: BLE001 — nunca tumbar el flujo de negocio
        log.warning("push_failed error=%s", exc)
        return False


def enviar_push_prueba(user_id: int) -> dict:
    """Envía una push de prueba a los dispositivos del usuario (sin persistir)."""
    from app.models.push import PushSubscription

    subs = (
        PushSubscription.query.filter_by(user_id=user_id)
        .order_by(PushSubscription.id.desc())
        .limit(10)
        .all()
    )
    payload = {
        "title": "ChambeApp",
        "body": "Notificación de prueba: el push está funcionando.",
        "icon": "/icons/icon-192.png",
        "badge": "/icons/badge-72.png",
        "tag": f"prueba-{uuid4().hex[:8]}",
        "data": {"url": "/notificaciones", "tipo": "prueba"},
    }
    enviados = sum(1 for sub in subs if enviar_push(sub, payload))
    return {"sent": enviados, "subscriptions": len(subs)}


def enviar_push_notificacion(notif) -> int:
    """Envía la notificación persistida a todas las suscripciones del usuario.

    Respeta `MerchantPreference.push_enabled`. No hace commit: la transacción
    la cierra el caller. Devuelve cuántos envíos salieron.
    """
    try:
        from app.models.merchant import MerchantPreference
        from app.models.push import PushSubscription

        prefs = MerchantPreference.query.filter_by(user_id=notif.user_id).first()
        if prefs is not None and not prefs.push_enabled:
            return 0

        subs = (
            PushSubscription.query.filter_by(user_id=notif.user_id)
            .order_by(PushSubscription.id.desc())
            .limit(10)
            .all()
        )
        if not subs:
            return 0

        payload = {
            "title": notif.titulo or "ChambeApp",
            "body": notif.mensaje,
            "icon": "/icons/icon-192.png",
            "badge": "/icons/badge-72.png",
            "tag": (
                f"notif-{notif.id}"
                if notif.id
                else f"notif-{notif.tipo}-{uuid4().hex[:8]}"
            ),
            "requireInteraction": False,
            "data": {
                "url": DEFAULT_PUSH_URL,
                "tipo": notif.tipo,
                "datos": notif.datos or {},
            },
        }

        enviados = 0
        for sub in subs:
            if enviar_push(sub, payload):
                enviados += 1
        return enviados
    except Exception as exc:  # noqa: BLE001
        log.warning("push_dispatch_failed error=%s", exc)
        return 0
