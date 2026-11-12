"""Servicio de autenticación en dos pasos (2FA).

Métodos soportados:
  · `sms`  — código de 6 dígitos por SMS (Onurix; en dev se loguea).
  · `totp` — app autenticadora (Google Authenticator, Authy, 1Password…).
  · códigos de recuperación — 10 códigos de un solo uso, siempre disponibles.

El desafío SMS vive en memoria (igual que el OTP); en producción debe moverse
a Redis. Los códigos de recuperación y el secreto TOTP sí se persisten.
"""

import base64
import hashlib
import hmac
import io
import secrets
from datetime import datetime, timedelta, timezone

from flask import current_app

from app.extensions import db
from app.models.two_factor import TwoFactorRecoveryCode
from app.services.sms import send_sms_2fa

_challenges: dict[int, dict] = {}

CODE_LENGTH = 6
TTL_MINUTES = 5
MAX_ATTEMPTS = 5
RESEND_COOLDOWN_SECONDS = 60
RECOVERY_CODE_COUNT = 10

# Alfabeto sin caracteres ambiguos (0/O, 1/I/L).
_RECOVERY_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


# ---------------------------------------------------------------------------
# Helpers de teléfono / claves
# ---------------------------------------------------------------------------

def _phone_onurix(telefono: str) -> str:
    digits = "".join(ch for ch in telefono if ch.isdigit())
    if len(digits) == 10:
        return f"57{digits}"
    if len(digits) >= 12 and digits.startswith("57"):
        return digits
    return f"57{digits}"


def mask_phone(telefono: str | None) -> str | None:
    """Muestra solo los últimos 3 dígitos: +57 *** *** 123."""
    if not telefono:
        return None
    digits = "".join(ch for ch in telefono if ch.isdigit())
    if not digits:
        return None
    return f"*** *** {digits[-3:]}"


def _fernet():
    from cryptography.fernet import Fernet

    secret = current_app.config["SECRET_KEY"]
    key = base64.urlsafe_b64encode(
        hashlib.sha256(f"{secret}:2fa-totp".encode()).digest()
    )
    return Fernet(key)


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode()).decode()
    except Exception:
        # Compatibilidad con secretos en texto plano (no deberían existir).
        return value


def _hash_recovery_code(code: str) -> str:
    key = current_app.config["SECRET_KEY"].encode()
    normalized = "".join(ch for ch in code.upper() if ch.isalnum())
    return hmac.new(key, normalized.encode(), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# TOTP
# ---------------------------------------------------------------------------

def generate_totp_secret() -> str:
    import pyotp

    return pyotp.random_base32()


def totp_uri(user, secret: str) -> str:
    import pyotp

    return pyotp.TOTP(secret).provisioning_uri(
        name=user.email, issuer_name="ChambeApp"
    )


def qr_svg(uri: str) -> str | None:
    """QR en SVG (sin dependencia de Pillow)."""
    try:
        import qrcode
        import qrcode.image.svg

        image = qrcode.make(
            uri,
            image_factory=qrcode.image.svg.SvgPathImage,
            box_size=10,
            border=2,
        )
        buffer = io.BytesIO()
        image.save(buffer)
        return buffer.getvalue().decode("utf-8")
    except Exception:  # noqa: BLE001 — el frontend puede mostrar el secreto
        return None


def verify_totp(secret: str | None, code: str) -> bool:
    if not secret:
        return False
    import pyotp

    return pyotp.TOTP(secret).verify((code or "").strip(), valid_window=1)


# ---------------------------------------------------------------------------
# Códigos de recuperación
# ---------------------------------------------------------------------------

def _new_recovery_code() -> str:
    raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def generate_recovery_codes(user, count: int = RECOVERY_CODE_COUNT) -> list[str]:
    """Reemplaza los códigos anteriores y devuelve los nuevos en texto plano."""
    TwoFactorRecoveryCode.query.filter_by(user_id=user.id).delete()
    codigos = []
    for _ in range(count):
        code = _new_recovery_code()
        codigos.append(code)
        db.session.add(
            TwoFactorRecoveryCode(
                user_id=user.id, code_hash=_hash_recovery_code(code)
            )
        )
    db.session.flush()
    return codigos


def consume_recovery_code(user, code: str) -> bool:
    """Consume un código de recuperación si coincide (marca usado)."""
    normalized = "".join(ch for ch in (code or "").upper() if ch.isalnum())
    if len(normalized) != 8:
        return False
    hashed = _hash_recovery_code(normalized)
    row = (
        TwoFactorRecoveryCode.query.filter_by(
            user_id=user.id, code_hash=hashed, usado=False
        )
        .first()
    )
    if row is None:
        return False
    row.usado = True
    row.usado_en = datetime.now(timezone.utc)
    return True


def count_recovery_codes(user) -> int:
    return TwoFactorRecoveryCode.query.filter_by(
        user_id=user.id, usado=False
    ).count()


# ---------------------------------------------------------------------------
# Desafíos de login
# ---------------------------------------------------------------------------

def _dev_codes_visibles() -> bool:
    return bool(
        current_app.config.get("TESTING") or current_app.config.get("DEBUG")
    )


def _metodo_efectivo(user) -> str:
    """Método utilizable; si el TOTP no tiene secreto, cae a SMS."""
    if user.two_factor_method == "totp" and user.two_factor_secret:
        return "totp"
    return "sms"


def create_challenge(user) -> dict:
    """Genera el desafío del login según el método del usuario.

    Para SMS guarda el código (y lo envía si hay teléfono); para TOTP no se
    genera nada: el código lo produce la app autenticadora.
    """
    method = _metodo_efectivo(user)
    base = {
        "requires_2fa": True,
        "method": method,
        "expires_in": TTL_MINUTES * 60,
    }

    if method == "totp":
        return base

    code = "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))
    ahora = datetime.now(timezone.utc)
    _challenges[user.id] = {
        "code": code,
        "expires_at": ahora + timedelta(minutes=TTL_MINUTES),
        "attempts": 0,
        "sent_at": ahora,
    }

    if user.telefono:
        try:
            send_sms_2fa(_phone_onurix(user.telefono), code)
        except Exception:
            current_app.logger.warning(
                "[2FA] No se pudo enviar SMS a user %s", user.id
            )

    base["masked_phone"] = mask_phone(user.telefono)
    if _dev_codes_visibles():
        base["dev_code"] = code
    return base


def resend_sms_challenge(user) -> dict:
    """Reenvía el código SMS con un cooldown de 60 s."""
    entry = _challenges.get(user.id)
    ahora = datetime.now(timezone.utc)
    if entry and entry.get("sent_at"):
        transcurrido = (ahora - entry["sent_at"]).total_seconds()
        if transcurrido < RESEND_COOLDOWN_SECONDS:
            return {
                "sent": False,
                "retry_after": int(RESEND_COOLDOWN_SECONDS - transcurrido),
            }

    payload = create_challenge(user)
    if payload.get("method") != "sms":
        return {"sent": False, "retry_after": 0}

    result = {
        "sent": True,
        "expires_in": payload["expires_in"],
        "masked_phone": payload.get("masked_phone"),
    }
    if "dev_code" in payload:
        result["dev_code"] = payload["dev_code"]
    return result


def _verify_sms(user_id: int, code: str) -> bool | str:
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


def verify_second_factor(user, code: str) -> bool | str:
    """Valida SMS, TOTP o un código de recuperación.

    Devuelve True o un string de error:
    'no_challenge' | 'expired' | 'too_many' | 'invalid'.
    """
    normalized = (code or "").strip()
    if not normalized:
        return "invalid"

    # 1) Código de recuperación (formato XXXX-XXXX, se acepta sin guion).
    if consume_recovery_code(user, normalized):
        return True

    method = _metodo_efectivo(user)
    if method == "totp":
        secret = decrypt_secret(user.two_factor_secret)
        return True if verify_totp(secret, normalized) else "invalid"

    return _verify_sms(user.id, normalized)


def verify_code_for_method(user, method: str, code: str) -> bool:
    """Verifica el código del método que se está ACTIVANDO.

    · sms  → contra el desafío SMS vigente (enviado antes con /2fa/sms/send).
    · totp → contra el secreto pendiente (setup) o el confirmado.
    """
    if method == "totp":
        pending = decrypt_secret(user.two_factor_pending_secret)
        actual = decrypt_secret(user.two_factor_secret)
        return verify_totp(pending, code) or verify_totp(actual, code)
    result = _verify_sms(user.id, code)
    return result is True


def clear_challenge(user_id: int) -> None:
    _challenges.pop(user_id, None)
