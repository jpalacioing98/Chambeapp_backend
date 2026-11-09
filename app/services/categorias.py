"""Normalización de categorías/oficios para emparejar habilidades y chambas.

Las categorías son texto libre escrito por solicitantes y PDS: pueden diferir
en mayúsculas, acentos o espacios sobrantes. Se normaliza a minúsculas, sin
acentos y sin espacios al inicio/fin para que "Construcción", "construccion" y
" construcción " sean la misma categoría.
"""

import unicodedata

from sqlalchemy import func

# Mapa de acentos españoles. Se aplica después de lower(); incluye las
# mayúsculas porque lower() de SQLite no pliega caracteres no ASCII.
_ACCENT_MAP = {
    "á": "a",
    "é": "e",
    "í": "i",
    "ó": "o",
    "ú": "u",
    "ü": "u",
    "ñ": "n",
    "Á": "a",
    "É": "e",
    "Í": "i",
    "Ó": "o",
    "Ú": "u",
    "Ü": "u",
    "Ñ": "n",
}


def normalizar_categoria(value: object | None) -> str:
    """Normaliza una categoría a minúsculas, sin acentos y sin bordes."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.strip().lower()


def categoria_norm_expr(column):
    """Expresión SQL equivalente a normalizar_categoria (Postgres y SQLite)."""
    expr = func.trim(func.lower(column))
    for accent, plain in _ACCENT_MAP.items():
        expr = func.replace(expr, accent, plain)
    return expr
