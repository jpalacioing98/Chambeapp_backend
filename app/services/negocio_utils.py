"""Utilidades del módulo Negocios: horarios dinámicos y slug generation."""

from datetime import datetime, time


def calcular_estado_horario(horarios: list) -> dict:
    """Calcula si el negocio está abierto y si cierra pronto.

    Recibe una lista de objetos NegocioHorario (o dicts con dia_semana,
    abierto, hora_apertura, hora_cierre).
    """
    ahora = datetime.now()
    dia_actual = ahora.weekday()  # 0=Lunes, 6=Domingo
    hora_actual = ahora.time()

    horario_hoy = None
    for h in horarios:
        dia_h = h.dia_semana if hasattr(h, "dia_semana") else h.get("dia_semana")
        if dia_h == dia_actual:
            horario_hoy = h
            break

    if not horario_hoy:
        return {"esta_abierto": False, "cierra_pronto": False}

    abierto = horario_hoy.abierto if hasattr(horario_hoy, "abierto") else horario_hoy.get("abierto", False)
    if not abierto:
        return {"esta_abierto": False, "cierra_pronto": False}

    hora_apertura = horario_hoy.hora_apertura if hasattr(horario_hoy, "hora_apertura") else horario_hoy.get("hora_apertura")
    hora_cierre = horario_hoy.hora_cierre if hasattr(horario_hoy, "hora_cierre") else horario_hoy.get("hora_cierre")

    if not hora_apertura or not hora_cierre:
        return {"esta_abierto": False, "cierra_pronto": False}

    if hora_apertura <= hora_actual <= hora_cierre:
        delta = datetime.combine(ahora.date(), hora_cierre) - \
                datetime.combine(ahora.date(), hora_actual)
        minutos = delta.total_seconds() / 60
        return {
            "esta_abierto": True,
            "cierra_pronto": minutos <= 30,
        }

    return {"esta_abierto": False, "cierra_pronto": False}


def generar_slug(nombre: str) -> str:
    """Genera un slug URL-friendly a partir del nombre del negocio."""
    import re
    import unicodedata

    # Normalizar unicode y quitar acentos
    slug = unicodedata.normalize("NFKD", nombre)
    slug = slug.encode("ascii", "ignore").decode("utf-8").lower()
    # Reemplazar espacios y caracteres no alfanuméricos por guiones
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[-\s]+", "-", slug).strip("-")
    return slug
