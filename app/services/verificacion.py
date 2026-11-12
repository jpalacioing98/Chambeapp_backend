"""Verificación de identidad (KYC) — criterio único de "cuenta verificada".

Una cuenta está verificada cuando TODOS los documentos KYC obligatorios de su
rol tienen al menos un ejemplar aprobado en `documentos_usuario`.

¿Por qué calcularlo y no leer `Profile.verificado` a secas?
El flag se recalcula solo cuando un verificador aprueba/rechaza un documento.
Los datos sembrados, migrados o corregidos por soporte pueden dejarlo
obsoleto (p. ej. `sol003` tiene los 3 documentos aprobados y el flag en
False). Las decisiones de permisos deben basarse en los documentos reales.
"""

from app.extensions import db
from app.models.kyc import DocumentoRequerido, DocumentoUsuario
from app.models.user import Profile


def rol_valor(user) -> str:
    """Devuelve el rol como string ('pds', 'solicitante', ...)."""
    rol = getattr(user, "rol", None)
    return getattr(rol, "value", rol) or ""


def claves_obligatorias(rol: str) -> list[str]:
    """Claves de los documentos KYC obligatorios de un rol."""
    return [
        d.clave
        for d in DocumentoRequerido.query.filter_by(
            rol=rol, obligatorio=True
        ).all()
    ]


def claves_aprobadas(user_id: int) -> set[str]:
    """Claves con al menos un ejemplar aprobado del usuario."""
    return {
        du.documento_clave
        for du in DocumentoUsuario.query.filter_by(
            user_id=user_id, estado="aprobado"
        ).all()
    }


def esta_verificado(user) -> bool:
    """True si el usuario cumple el KYC obligatorio de su rol.

    Si el rol no tiene catálogo de documentos obligatorios (p. ej. merchant),
    no se exige nada y se considera verificado.
    """
    obligatorias = claves_obligatorias(rol_valor(user))
    if not obligatorias:
        return True
    return set(obligatorias).issubset(claves_aprobadas(user.id))


def sincronizar_verificado(user) -> bool:
    """Recalcula y persiste `Profile.verificado`. Devuelve el valor calculado.

    No hace commit: el llamador decide cuándo persistir.
    """
    verificado = esta_verificado(user)
    profile = db.session.get(Profile, user.id)
    if profile is not None:
        profile.verificado = verificado
    return verificado


def ids_verificados_rol(rol: str, user_ids: list[int]) -> set[int]:
    """Subconjunto de `user_ids` que cumple el KYC obligatorio del rol.

    Una sola query para N usuarios (evita el N+1 al filtrar candidatos).
    """
    obligatorias = set(claves_obligatorias(rol))
    if not obligatorias or not user_ids:
        return set(user_ids) if not obligatorias else set()

    filas = (
        db.session.query(
            DocumentoUsuario.user_id, DocumentoUsuario.documento_clave
        )
        .filter(
            DocumentoUsuario.user_id.in_(user_ids),
            DocumentoUsuario.estado == "aprobado",
            DocumentoUsuario.documento_clave.in_(obligatorias),
        )
        .distinct()
        .all()
    )

    por_usuario: dict[int, set[str]] = {}
    for uid, clave in filas:
        por_usuario.setdefault(uid, set()).add(clave)

    return {
        uid for uid, claves in por_usuario.items() if claves >= obligatorias
    }


def aprobar_documento_automatico(user, clave: str, nota: str) -> bool:
    """Aprueba (o crea ya aprobado) un documento del usuario sin revisor.

    Se usa para validaciones automáticas, como el OTP del celular
    (`verificacion_contacto`). No hace commit: el llamador decide.
    Devuelve True si el documento quedó aprobado.
    """
    from datetime import datetime, timezone

    rol = rol_valor(user)
    requerido = DocumentoRequerido.query.filter_by(rol=rol, clave=clave).first()
    if requerido is None:
        return False

    du = DocumentoUsuario.query.filter_by(
        user_id=user.id, documento_clave=clave, instancia=None
    ).first()
    ahora = datetime.now(timezone.utc)

    if du is None:
        du = DocumentoUsuario(
            user_id=user.id,
            documento_clave=clave,
            instancia=None,
            rol=rol,
        )
        db.session.add(du)

    du.documento_requerido_id = requerido.id
    du.estado = "aprobado"
    du.fecha_envio = du.fecha_envio or ahora
    du.revisado_en = ahora
    du.nota = nota

    sincronizar_verificado(user)
    return True


def exigir_verificado(user_id: int, config_key: str, accion: str) -> None:
    """Aborta con 403 si el gate está activo y el usuario no está verificado.

    `config_key` permite apagar la exigencia por entorno (los tests la
    desactivan). `accion` se usa en el mensaje: "postularte", "enviar ofertas"…
    """
    from flask import current_app
    from flask_smorest import abort

    from app.models.user import User

    if not current_app.config.get(config_key, True):
        return

    user = db.session.get(User, user_id)
    if user is None:
        abort(404, message="Usuario no encontrado.")

    if not esta_verificado(user):
        abort(
            403,
            message=(
                f"Verifica tu identidad antes de {accion}: necesitas tener "
                "aprobados tus documentos KYC. Entra a Verificación de "
                "identidad para completarlos."
            ),
        )
