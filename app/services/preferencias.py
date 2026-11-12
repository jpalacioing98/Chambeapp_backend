"""Preferencias de notificación (MerchantPreference) — RF-10 / HU-70.

Un solo mapa `tipo → toggle` para que todos los emisores (controladores,
descubrimiento, cascada) respeten las mismas reglas.

Si el usuario no tiene fila de preferencias, todo está permitido: los
defaults del modelo son True.
"""

# (prefijo del tipo, nombre del toggle)
_PREFERENCIA_POR_PREFIJO = (
    ("negocio:rating", "notif_nueva_resena"),
    ("resena", "notif_nueva_resena"),
    ("kyc", "notif_estado_kyc"),
    ("documento", "notif_estado_kyc"),
    ("pago", "notif_pago_recibido"),
    ("wallet", "notif_pago_recibido"),
)

_TIPOS_PAGO = {"contrato_confirmado", "chamba_pago_confirmado", "marana_pago"}

# Avisos legales/sistema: no se pueden silenciar.
_TIPOS_SIEMPRE = {
    "formalizacion",
    "sistema",
    "alerta_motor_recomendacion",
    "recomendacion_proveedor",
}


def preferencia_para_tipo(tipo: str) -> str | None:
    """Devuelve el toggle que controla `tipo` (None = siempre permitido)."""
    if not tipo:
        return None
    if tipo in _TIPOS_SIEMPRE or tipo.startswith(("alerta_", "recomendacion_")):
        return None
    if tipo in _TIPOS_PAGO:
        return "notif_pago_recibido"
    for prefijo, preferencia in _PREFERENCIA_POR_PREFIJO:
        if tipo.startswith(prefijo):
            return preferencia
    return "notif_nueva_solicitud"


def preferencia_permite(user_id: int, tipo: str) -> bool:
    """True si el usuario quiere recibir notificaciones de este tipo."""
    preferencia = preferencia_para_tipo(tipo)
    if preferencia is None:
        return True
    try:
        from app.models.merchant import MerchantPreference

        prefs = MerchantPreference.query.filter_by(user_id=user_id).first()
        if prefs is None:
            return True
        return bool(getattr(prefs, preferencia, True))
    except Exception:  # noqa: BLE001 — una preferencia nunca bloquea el flujo
        return True
