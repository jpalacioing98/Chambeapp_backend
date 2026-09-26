"""Servicio de autenticación en dos pasos (2FA) — desafíos de login.

Cuando un usuario tiene `two_factor_enabled=True`, el login NO entrega tokens:
genera un desafío (código de 6 dígitos) con expiración y reintentos, lo "envía"
(SMS vía Onurix en prod; `dev_code` en dev/test) y espera que el cliente lo
valide en `POST /auth/2fa/verify` para emitir los tokens.

El store es en memoria (igual que el OTP); en producción migrar a Redis.
"""

import secrets
from datetime import datetime, timedelta, timezone

from flask import current_app

from app.services.sms import send_sms_2fa

_challenges: dict[int, dict] = {}

CODE_LENGTH = 6
TTL_MINUTES = 5
MAX_ATTEMPTS = 5


def _phone_onurix(telefono: str) -> str:
    digits = "".join(ch for ch in telefono if ch.isdigit())
    if len(digits) == 10:
        return f"57{digits}"
    if len(digits) >= 12 and digits.startswith("57"):
        return digits
    return f"57{digits}"


def create_challenge(user) -> dict:
    """Genera un desafío 2FA para el usuario y lo envía.

    Devuelve el payload del login (`expires_in` y, en dev/test, `dev_code`).
    """
    code = "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))
    _challenges[user.id] = {
        "code": code,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=TTL_MINUTES),
        "attempts": 0,
    }

    if user.telefono:
        try:
            send_sms_2fa(_phone_onurix(user.telefono), code)
        except Exception:
            current_app.logger.warning("[2FA] No se pudo enviar SMS a user %s", user.id)

    response = {"expires_in": TTL_MINUTES * 60}
    if current_app.config.get("TESTING") or current_app.config.get("DEBUG"):
        response["dev_code"] = code
    return response


def verify_challenge(user_id: int, code: str) -> bool | str:
    """Valida el código del desafío.

    Devuelve True (válido y consumido), o un string de error:
    'no_challenge' | 'expired' | 'too_many'.
    """
    entry = _challenges.get(user_id)
    if entry is None:
        return "no_challenge"
    if datetime.now(timezone.utc) > entry["expires_at"]:
        _challenges.pop(user_id, None)
        return "expired"
    if entry["attempts"] >= MAX_ATTEMPTS:
        _challenges.pop(user_id, None)
        return "too_many"
    entry["attempts"] += 1
    if secrets.compare_digest(entry["code"], (code or "").strip()):
        _challenges.pop(user_id, None)
        return True
    return False