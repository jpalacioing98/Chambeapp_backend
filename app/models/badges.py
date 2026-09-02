"""Badge types for user achievements (P2-5)."""

from enum import Enum


class BadgeType(str, Enum):
    """All available badges in ChambeApp."""

    PRIMER_CONTRATO = "primer_contrato"
    DIEZ_CONTRATOS = "diez_contratos"
    CIEN_CONTRATOS = "cien_contratos"
    VERIFICADO = "verificado"
    PERFIL_COMPLETO = "perfil_completo"
    PRIMER_SERVICIO = "primer_servicio"
    TOP_RATED = "top_rated"
    SIN_DISPUTAS = "sin_disputas"
    MONEDERO_ACTIVO = "monedero_activo"

    @classmethod
    def values(cls):
        return [b.value for b in cls]
