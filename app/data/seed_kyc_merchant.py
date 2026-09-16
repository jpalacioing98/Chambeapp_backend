"""Seed de documentos KYC requeridos para el rol merchant.

Fuente: IMPLEMENTACION_MODULO_NEGOCIOS.md §10.1
Cada entrada es tupla: (rol, clave, nombre, descripcion, obligatorio, grupo, multi_instancia, orden).

Uso standalone:
    python -m app.data.seed_kyc_merchant

Uso desde seed.py:
    from app.data.seed_kyc_merchant import DOCUMENTOS_MERCHANT, seed_kyc_merchant
"""

from app.extensions import db
from app.models.kyc import DocumentoRequerido


# ── Catálogo de documentos requeridos para merchant ──
# (rol, clave, nombre, descripcion, obligatorio, grupo, multi_instancia, orden)
DOCUMENTOS_MERCHANT: list[tuple] = [
    # Grupo: identidad
    (
        "merchant",
        "doc_identidad",
        "Documento de Identidad",
        "Cédula de Ciudadanía, CE o PPT del representante legal.",
        True,       # obligatorio
        "identidad",
        False,      # multi_instancia
        1,          # orden
    ),
    # Grupo: financiero
    (
        "merchant",
        "rut",
        "RUT",
        "Registro Único Tributario expedido por la DIAN.",
        True,       # obligatorio
        "financiero",
        False,      # multi_instancia
        2,          # orden
    ),
    # Grupo: antecedentes
    (
        "merchant",
        "certificado_comercial",
        "Certificado de Existencia y Representación Legal",
        "Expedido por la Cámara de Comercio o equivalente.",
        True,       # obligatorio
        "antecedentes",
        False,      # multi_instancia
        3,          # orden
    ),
    # Grupo: opcional
    (
        "merchant",
        "foto_local",
        "Foto del Local Comercial",
        "Foto frontal del establecimiento con letrero visible.",
        False,      # obligatorio (opcional)
        "opcional",
        False,      # multi_instancia
        4,          # orden
    ),
]


def seed_kyc_merchant() -> int:
    """Siembra los documentos KYC para el rol merchant (idempotente).

    Returns:
        Número de documentos creados.
    """
    created = 0
    for rol, clave, nombre, descripcion, obligatorio, grupo, multi, orden in DOCUMENTOS_MERCHANT:
        if DocumentoRequerido.query.filter_by(rol=rol, clave=clave).first():
            continue
        db.session.add(
            DocumentoRequerido(
                rol=rol,
                clave=clave,
                nombre=nombre,
                descripcion=descripcion,
                obligatorio=obligatorio,
                grupo=grupo,
                multi_instancia=multi,
                orden=orden,
            )
        )
        created += 1
        print(f"  CREADO doc KYC merchant: {clave}")
    return created


if __name__ == "__main__":
    from app import create_app

    app = create_app()
    with app.app_context():
        print("Sembrando documentos KYC para merchant...")
        n = seed_kyc_merchant()
        db.session.commit()
        print(f"Seed KYC merchant completado: {n} documentos creados")
