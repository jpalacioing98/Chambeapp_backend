"""Catálogo canónico de documentos KYC por rol (Politica_KYC.md).

Este módulo es la ÚNICA fuente de verdad del catálogo. `seed.py` y el
arranque de la app lo usan vía `sync_kyc_catalog()`, que inserta los
documentos faltantes y PODA los obsoletos (p. ej. "validacion_pago" del
solicitante) para que la BD existente quede siempre alineada con el código.
"""

from app.extensions import db
from app.models.kyc import DocumentoRequerido
from app.data.seed_kyc_merchant import DOCUMENTOS_MERCHANT

# (rol, clave, nombre, descripcion, obligatorio, grupo, multi_instancia, orden)
CATALOGO_KYC: list[tuple] = [
    # ── ROL pds · OBLIGATORIOS ──
    # Grupo: identidad
    ("pds", "doc_identidad", "Documento de Identidad",
     "Fotografía por ambas caras de CC, CE o PPT.", True, "identidad", False, 1),
    ("pds", "prueba_vida", "Prueba de Vida (Biometría)",
     "Selfie en tiempo real que coincide con el documento de identidad.", True, "identidad", False, 2),
    ("pds", "comprobante_residencia", "Comprobante de Residencia",
     "Recibo de servicios públicos, extracto bancario o certificación de dirección (máx. 3 meses).", True, "identidad", False, 3),
    # Grupo: antecedentes
    ("pds", "antecedentes_judiciales", "Certificado de Antecedentes Judiciales",
     "Consulta en bases de la Policía Nacional.", True, "antecedentes", False, 4),
    ("pds", "rnmc", "Registro Nacional de Medidas Correctivas (RNMC)",
     "Verificación de multas por comportamientos contrarios a la convivencia.", True, "antecedentes", False, 5),
    ("pds", "antecedentes_procuraduria", "Antecedentes de Procuraduría",
     "Consulta de antecedentes disciplinarios — Procuraduría General de la Nación.", True, "antecedentes", False, 6),
    ("pds", "antecedentes_contraduria", "Antecedentes de Contraloría",
     "Consulta de responsabilidad fiscal — Contraloría General de la República.", True, "antecedentes", False, 7),
    # Grupo: financiero
    ("pds", "cert_bancaria", "Certificación Bancaria",
     "Cuenta a nombre exclusivo del titular (Nequi, Daviplata, Bancolombia…). Se puede registrar varias (una por cuenta).", True, "financiero", True, 8),
    # ── ROL pds · OPCIONALES ──
    ("pds", "validacion_profesional", "Validación Profesional",
     "Tarjeta profesional, certificado SENA o constancia de competencia. Se puede registrar varias (una por habilidad/certificación).", False, "opcional", True, 9),
    ("pds", "salud_seguridad", "Salud y Seguridad (EPS + ARL)",
     "Afiliación activa al Sistema de Seguridad Social. Obligatorio para planes Premium.", False, "opcional", False, 10),
    ("pds", "certificado_laboral", "Certificado Laboral / Referencia de Empleo",
     "Constancia de trabajo o referencia de un empleador anterior. Se puede registrar varias (una por empleo).", False, "opcional", True, 11),
    # ── ROL solicitante · OBLIGATORIOS ──
    ("solicitante", "doc_identidad", "Escaneo del Documento",
     "Escaneo o foto del documento de identidad (CC, CE o NIT).", True, "identidad", False, 1),
    ("solicitante", "prueba_vida", "Prueba de Vida (Selfie)",
     "Selfie frontal para biometría facial. Confirma que eres tú.", True, "identidad", False, 2),
    ("solicitante", "verificacion_contacto", "Verificación del Número",
     "Se valida con OTP al celular (no requiere subir documento).", True, "identidad", False, 3),
]


def sync_kyc_catalog() -> int:
    """Inserta los documentos faltantes y ELIMINA los obsoletos.

    Idempotente y seguro de re-ejecutar: al final, la tabla
    `documentos_requeridos` queda exactamente igual al catálogo definido
    aquí (más los documentos del rol merchant).

    Returns:
        Número de cambios (creados + eliminados).
    """
    catalogo = CATALOGO_KYC + DOCUMENTOS_MERCHANT
    claves_validas = {(rol, clave) for rol, clave, *_ in catalogo}

    cambios = 0
    for rol, clave, nombre, descripcion, obligatorio, grupo, multi, orden in catalogo:
        if DocumentoRequerido.query.filter_by(rol=rol, clave=clave).first():
            continue
        db.session.add(
            DocumentoRequerido(
                rol=rol, clave=clave, nombre=nombre, descripcion=descripcion,
                obligatorio=obligatorio, grupo=grupo, multi_instancia=multi, orden=orden,
            )
        )
        cambios += 1
        print(f"  CREADO doc KYC: {rol}/{clave}")

    for doc in DocumentoRequerido.query.all():
        if (doc.rol, doc.clave) not in claves_validas:
            db.session.delete(doc)
            cambios += 1
            print(f"  ELIMINADO doc KYC obsoleto: {doc.rol}/{doc.clave}")

    db.session.commit()
    return cambios


def seed_kyc() -> int:
    """Siembra el catálogo KYC (compatibilidad con seed.py)."""
    return sync_kyc_catalog()