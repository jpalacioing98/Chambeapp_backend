"""OTP (One-Time Password) por SMS para verificación de celular en el registro.

Flujo:
1. POST /api/v1/auth/otp/send     -> genera y "envía" un código de 6 dígitos.
2. POST /api/v1/auth/otp/verify   -> valida el código antes de crear la cuenta.

En desarrollo/testing el código se retorna en `dev_code` y se loguea; en
producción se delega a Onurix (https://docs.onurix.com).
"""

import secrets
from datetime import datetime, timedelta, timezone

from flask import current_app
from flask.views import MethodView
from flask_smorest import Blueprint, abort

from app.schemas.auth import OtpSendSchema, OtpVerifySchema, MessageResponseSchema
from app.services.sms import send_sms_2fa, verify_sms_2fa

blp = Blueprint("otp", __name__, description="Verificación de celular por OTP (SMS)")

# Store OTPs in memory (in production, use Redis). Clave: teléfono normalizado.
_otp_store: dict[str, dict] = {}

OTP_LENGTH = 6
OTP_TTL_MINUTES = 5
OTP_MAX_ATTEMPTS = 5


def _normalize_phone_for_onurix(phone: str) -> str:
    """Normaliza el celular para Onurix: solo dígitos, sin +.

    Onurix espera el teléfono sin + (ej: 573001234567).

    Ejemplos:
        +573001234567 -> 573001234567
        3001234567 -> 573001234567
        +57 300 123 4567 -> 573001234567
    """
    digits = "".join(ch for ch in phone if ch.isdigit())

    # Si tiene 10 dígitos, asumir Colombia (57)
    if len(digits) == 10:
        return f"57{digits}"

    # Si tiene 12+ dígitos y empieza con 57, usar tal cual
    if len(digits) >= 12 and digits.startswith("57"):
        return digits

    # Por defecto, agregar 57
    return f"57{digits}"


def _normalize_phone_display(phone: str) -> str:
    """Normaliza el celular para mostrar: formato E.164 con +.

    Ejemplos:
        3001234567 -> +573001234567
        573001234567 -> +573001234567
    """
    digits = "".join(ch for ch in phone if ch.isdigit())

    if len(digits) == 10:
        return f"+57{digits}"

    if len(digits) >= 12 and digits.startswith("57"):
        return f"+{digits}"

    return f"+57{digits}"


def _generate_otp(phone: str) -> str:
    """Genera un OTP numérico de 6 dígitos y lo almacena con expiración."""
    code = "".join(secrets.choice("0123456789") for _ in range(OTP_LENGTH))
    _otp_store[phone] = {
        "code": code,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MINUTES),
        "attempts": 0,
    }
    return code


@blp.route("/otp/send")
class OtpSend(MethodView):
    @blp.arguments(OtpSendSchema)
    @blp.response(200)
    def post(self, data):
        """Genera y envía un código OTP al celular indicado."""
        phone_raw = data.get("telefono", "")
        phone_e164 = _normalize_phone_display(phone_raw)
        phone_onurix = _normalize_phone_for_onurix(phone_raw)

        if len(phone_onurix) < 7 or len(phone_onurix) > 15:
            abort(400, message="Número de celular inválido.")

        code = _generate_otp(phone_e164)

        # Enviar SMS vía Onurix (o loguear en dev)
        result = send_sms_2fa(phone_onurix, code)
        if not result["success"] and not current_app.config.get("DEBUG"):
            _otp_store.pop(phone_e164, None)
            abort(502, message=f"No se pudo enviar el SMS: {result['message']}")

        response = {
            "message": f"Código enviado al celular. Válido por {OTP_TTL_MINUTES} minutos.",
            "expires_in": OTP_TTL_MINUTES * 60,
        }
        # En dev/test exponemos el código para poder completar el flujo sin SMS real.
        if current_app.config.get("TESTING") or current_app.config.get("DEBUG"):
            response["dev_code"] = code
        return response


@blp.route("/otp/verify")
class OtpVerify(MethodView):
    @blp.arguments(OtpVerifySchema)
    @blp.response(200, MessageResponseSchema)
    def post(self, data):
        """Valida el código OTP para el celular indicado."""
        phone_raw = data.get("telefono", "")
        phone_e164 = _normalize_phone_display(phone_raw)
        code = (data.get("code") or "").strip()

        entry = _otp_store.get(phone_e164)
        if entry is None:
            abort(400, message="No hay un código activo para este celular. Solicita uno nuevo.")

        if datetime.now(timezone.utc) > entry["expires_at"]:
            _otp_store.pop(phone_e164, None)
            abort(400, message="El código expiró. Solicita uno nuevo.")

        if entry["attempts"] >= OTP_MAX_ATTEMPTS:
            _otp_store.pop(phone_e164, None)
            abort(429, message="Demasiados intentos. Solicita un código nuevo.")

        entry["attempts"] += 1

        if not secrets.compare_digest(entry["code"], code):
            abort(400, message="Código incorrecto. Verifica e inténtalo de nuevo.")

        # Código válido: lo consumimos (un solo uso).
        _otp_store.pop(phone_e164, None)
        return {"message": "Celular verificado correctamente."}
