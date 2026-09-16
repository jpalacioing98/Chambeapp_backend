"""Servicio de envío de SMS vía Onurix.

En desarrollo/testing se loguea el código (sin enviar SMS real).
En producción se usa Onurix para enviar el SMS.

Documentación: https://docs.onurix.com/sms/send_code_2fa_sms
"""

import logging
import os
import requests
from flask import current_app

logger = logging.getLogger(__name__)

ONURIX_API_BASE = "https://www.onurix.com/api/v1"


def _get_onurix_credentials() -> dict:
    """Obtiene las credenciales de Onurix desde config o environment."""
    return {
        "client": current_app.config.get("ONURIX_CLIENT") or os.environ.get("ONURIX_CLIENT"),
        "key": current_app.config.get("ONURIX_KEY") or os.environ.get("ONURIX_KEY"),
        "app_name": current_app.config.get("ONURIX_APP_NAME") or os.environ.get("ONURIX_APP_NAME", "ChambeApp"),
    }


def send_sms_2fa(phone: str, code: str) -> dict:
    """Envía un código 2FA por SMS usando Onurix.

    Args:
        phone: Número de teléfono sin + (ej: 573001234567)
        code: Código de verificación a enviar

    Returns:
        dict con {success: bool, message: str, onurix_id: str|None, minutes_to_expire: int|None}
    """
    creds = _get_onurix_credentials()

    # En dev/test solo loguear (a menos que SMS_SEND_DEV=1)
    send_in_dev = current_app.config.get("SMS_SEND_DEV", False)
    if current_app.config.get("TESTING") or (current_app.config.get("DEBUG") and not send_in_dev):
        logger.info("[SMS-DEV] Onurix 2FA para %s (credenciales: client=%s)", phone, creds["client"])
        return {
            "success": True,
            "message": "Código enviado (modo desarrollo)",
            "onurix_id": "dev-mode",
            "minutes_to_expire": 5,
        }

    if not creds["client"] or not creds["key"]:
        logger.warning("[SMS] Onurix no configurado. SMS no enviado a %s", phone)
        return {"success": False, "message": "Onurix no configurado", "onurix_id": None, "minutes_to_expire": None}

    try:
        # Usar /sms/send para enviar nuestro propio código
        sms_message = f"Tu código ChambeApp es {code}. Válido por 5 minutos."
        response = requests.post(
            f"{ONURIX_API_BASE}/sms/send",
            data={
                "client": creds["client"],
                "key": creds["key"],
                "phone": phone,
                "sms": sms_message,
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            timeout=10,
        )

        result = response.json()
        logger.info("[SMS] Onurix raw response: %s", result)

        if response.status_code == 200 and result.get("status") == "success":
            logger.info("[SMS] Onurix 2FA enviado a %s | ID: %s", phone, result.get("id"))
            return {
                "success": True,
                "message": "Código enviado",
                "onurix_id": result.get("id"),
                "minutes_to_expire": result.get("minutes_to_expire"),
            }
        else:
            error_msg = result.get("msg", "Error desconocido")
            error_code = result.get("error", "N/A")
            logger.error("[SMS] Onurix error para %s: %s (code: %s)", phone, error_msg, error_code)
            return {"success": False, "message": error_msg, "onurix_id": None, "minutes_to_expire": None}

    except Exception as e:
        logger.error("[SMS] Excepción enviando a %s: %s", phone, e)
        return {"success": False, "message": str(e), "onurix_id": None, "minutes_to_expire": None}


def verify_sms_2fa(phone: str, code: str) -> dict:
    """Verifica un código 2FA usando Onurix.

    Args:
        phone: Número de teléfono sin + (ej: 573001234567)
        code: Código de verificación

    Returns:
        dict con {success: bool, message: str}
    """
    creds = _get_onurix_credentials()

    # En dev/test asumir que es correcto (el OTP se valida localmente)
    if current_app.config.get("TESTING") or current_app.config.get("DEBUG"):
        return {"success": True, "message": "Código verificado (modo desarrollo)"}

    if not creds["client"] or not creds["key"]:
        return {"success": False, "message": "Onurix no configurado"}

    try:
        response = requests.post(
            f"{ONURIX_API_BASE}/2fa/verification-code",
            data={
                "client": creds["client"],
                "key": creds["key"],
                "phone": phone,
                "app-name": creds["app_name"],
                "code": code,
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            timeout=10,
        )

        result = response.json()

        if response.status_code == 200 and result.get("status") == "success":
            logger.info("[SMS] Onurix verificación exitosa para %s", phone)
            return {"success": True, "message": "Código verificado"}
        else:
            error_msg = result.get("msg", "Código incorrecto")
            logger.warning("[SMS] Onurix verificación fallida para %s: %s", phone, error_msg)
            return {"success": False, "message": error_msg}

    except Exception as e:
        logger.error("[SMS] Excepción verificando %s: %s", phone, e)
        return {"success": False, "message": str(e)}
