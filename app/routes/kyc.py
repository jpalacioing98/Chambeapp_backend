"""Blueprint KYC documental por rol (Politica_KYC.md / RF-12).

Endpoints (JWT requerido):
  GET  /api/v1/kyc/documentos-requeridos -> catálogo filtrado por rol del usuario.
  GET  /api/v1/kyc/mis-documentos        -> estado de los documentos del usuario.
  POST /api/v1/kyc/documentos            -> envía (upsert) un documento del usuario (base64 MVP).
  GET  /api/v1/kyc/documentos/mios       -> documentos subidos por el usuario (con catálogo).
  GET  /api/v1/kyc/pendientes            -> docs enviados para revisión (verificador/admin/soporte).
  POST /api/v1/kyc/documentos/<id>/verificar -> aprueba/rechaza (verificador/admin).

Multi-instancia:
  Documentos como validacion_profesional, cert_bancaria o certificado_laboral
  admiten múltiples ejemplares (uno por habilidad, cuenta o empleo).
  Se diferencian por la columna `instancia`.
"""

from datetime import datetime, timezone

from flask import jsonify, request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.auth.decorators import role_required
from app.models.user import User, Profile
from app.models.kyc import DocumentoRequerido, DocumentoUsuario
from app.schemas.kyc import (
    DocumentoUploadSchema,
    DocumentoVerificarSchema,
    DocumentoUsuarioOutSchema,
    PendienteOutSchema,
)

blp = Blueprint("kyc", __name__, description="KYC documental por rol")


def _current_user() -> User:
    return db.get_or_404(User, int(get_jwt_identity()))


def _recalcular_verificado(user: User, profile: Profile) -> None:
    """Recalcula Profile.verificado: True si TODOS los docs obligatorios del rol
    tienen al menos un DocumentoUsuario aprobado.

    Para documentos multi-instancia solo se requiere al menos una instancia
    aprobada (ej: una validación profesional, un cert bancario, un cert laboral).
    """
    obligatorios = DocumentoRequerido.query.filter_by(
        rol=user.rol.value, obligatorio=True
    ).all()
    if not obligatorios:
        return

    aprobados = {
        du.documento_clave
        for du in DocumentoUsuario.query.filter_by(
            user_id=user.id, estado="aprobado"
        ).all()
    }

    for doc_req in obligatorios:
        if doc_req.clave not in aprobados:
            profile.verificado = False
            return

    profile.verificado = True


@blp.route("/documentos-requeridos")
class DocumentosRequeridos(MethodView):
    @jwt_required()
    def get(self):
        """Lista los documentos KYC requeridos para el rol del usuario."""
        user = _current_user()
        docs = (
            DocumentoRequerido.query.filter_by(rol=user.rol.value)
            .order_by(DocumentoRequerido.orden)
            .all()
        )
        return (
            jsonify(
                {
                    "rol": user.rol.value,
                    "documentos": [
                        {
                            "clave": d.clave,
                            "nombre": d.nombre,
                            "descripcion": d.descripcion,
                            "obligatorio": d.obligatorio,
                            "grupo": d.grupo,
                            "multi_instancia": d.multi_instancia,
                            "orden": d.orden,
                        }
                        for d in docs
                    ],
                }
            ),
            200,
        )


@blp.route("/mis-documentos")
class MisDocumentos(MethodView):
    @jwt_required()
    def get(self):
        """Estado de los documentos KYC del usuario, unido con el catálogo.

        Para docs multi-instancia, incluye todas las instancias subidas.
        """
        user = _current_user()
        requeridos = DocumentoRequerido.query.filter_by(rol=user.rol.value).all()
        enviados = DocumentoUsuario.query.filter_by(user_id=user.id).all()

        enviados_por_clave: dict[str, list] = {}
        for du in enviados:
            enviados_por_clave.setdefault(du.documento_clave, []).append(du)

        documentos = []
        for d in requeridos:
            instancias = enviados_por_clave.get(d.clave, [])
            if d.multi_instancia:
                documentos.append({
                    "clave": d.clave,
                    "nombre": d.nombre,
                    "descripcion": d.descripcion,
                    "obligatorio": d.obligatorio,
                    "grupo": d.grupo,
                    "multi_instancia": True,
                    "instancias": [
                        {
                            "instancia_id": du.id,
                            "instancia": du.instancia,
                            "estado": du.estado,
                            "url": du.url,
                            "nombre_archivo": du.nombre_archivo,
                            "fecha_envio": du.fecha_envio.isoformat() if du.fecha_envio else None,
                        }
                        for du in instancias
                    ],
                    "enviado": len(instancias) > 0,
                })
            else:
                du = instancias[0] if instancias else None
                documentos.append({
                    "clave": d.clave,
                    "nombre": d.nombre,
                    "descripcion": d.descripcion,
                    "obligatorio": d.obligatorio,
                    "grupo": d.grupo,
                    "multi_instancia": False,
                    "estado": du.estado if du else "no_enviado",
                    "url": du.url if du else None,
                    "fecha_envio": (
                        du.fecha_envio.isoformat() if du and du.fecha_envio else None
                    ),
                    "enviado": du is not None,
                })
        return jsonify({"documentos": documentos}), 200


@blp.route("/documentos")
class Documentos(MethodView):
    @role_required(["pds", "solicitante"])
    @blp.arguments(DocumentoUploadSchema)
    @blp.response(200, DocumentoUsuarioOutSchema)
    def post(self, data):
        """Envía (upsert) un documento KYC válido para el rol del usuario.

        Para documentos multi-instancia, el campo `instancia` diferencia
        cada ejemplar (ej: "Electricidad", "Nequi", "Empresa XYZ").
        Para documentos single-instance, `instancia` debe ser null/omiso.
        """
        user = _current_user()
        req = None
        if data.get("documento_requerido_id"):
            req = db.get_or_404(
                DocumentoRequerido, data["documento_requerido_id"]
            )
            if req.rol != user.rol.value:
                abort(400, message="El documento no corresponde a su rol.")
            clave = req.clave
        elif data.get("clave"):
            clave = data["clave"]
            req = DocumentoRequerido.query.filter_by(
                rol=user.rol.value, clave=clave
            ).first()
        else:
            abort(400, message="Debe enviar 'documento_requerido_id' o 'clave'.")

        if req is None:
            abort(400, message="La clave de documento no es válida para su rol.")

        instancia = data.get("instancia") or None

        if req.multi_instancia:
            if not instancia:
                abort(400, message=f"El documento '{req.nombre}' requiere un nombre de instancia (ej: habilidad, cuenta, empleo).")
        else:
            instancia = None

        du = DocumentoUsuario.query.filter_by(
            user_id=user.id, documento_clave=clave, instancia=instancia
        ).first()
        now = datetime.now(timezone.utc)
        if du is None:
            du = DocumentoUsuario(
                user_id=user.id,
                documento_clave=clave,
                instancia=instancia,
                rol=user.rol.value,
            )
            db.session.add(du)
        du.documento_requerido_id = req.id
        du.estado = "enviado"
        du.fecha_envio = now
        du.archivo_base64 = data.get("archivo_base64")
        du.nombre_archivo = data.get("nombre_archivo")
        du.tipo_mime = data.get("tipo_mime")
        du.url = data.get("url")
        du.revisado_en = None
        du.revisor_id = None
        du.nota = None
        db.session.commit()

        du.requerido = req
        return du


@blp.route("/documentos/mios")
class MisDocumentosSubidos(MethodView):
    @jwt_required()
    @blp.response(200, DocumentoUsuarioOutSchema(many=True))
    def get(self):
        """Lista los documentos KYC subidos por el usuario con info del requerido."""
        user = _current_user()
        docs = (
            DocumentoUsuario.query.filter_by(user_id=user.id)
            .order_by(DocumentoUsuario.id)
            .all()
        )
        for du in docs:
            du.requerido = DocumentoRequerido.query.filter_by(
                rol=user.rol.value, clave=du.documento_clave
            ).first()
        return docs


@blp.route("/pendientes")
class DocumentosPendientes(MethodView):
    @role_required(["verificador", "admin", "superadmin", "soporte"])
    @blp.response(200, PendienteOutSchema(many=True))
    def get(self):
        """Lista documentos enviados (estado='enviado') para revisión del verificador."""
        docs = (
            DocumentoUsuario.query.filter_by(estado="enviado")
            .order_by(DocumentoUsuario.id)
            .all()
        )
        for du in docs:
            user = db.session.get(User, du.user_id)
            du.usuario = (
                {
                    "id": user.id,
                    "nombre": user.nombre,
                    "email": user.email,
                    "rol": user.rol.value,
                }
                if user
                else None
            )
            du.requerido = DocumentoRequerido.query.filter_by(
                rol=du.rol, clave=du.documento_clave
            ).first()
        return docs


@blp.route("/documentos/<int:doc_usuario_id>/verificar")
class DocumentoVerificar(MethodView):
    @role_required(["verificador", "admin", "superadmin"])
    @blp.arguments(DocumentoVerificarSchema)
    @blp.response(200, DocumentoUsuarioOutSchema)
    def post(self, data, doc_usuario_id):
        """Aprueba o rechaza un documento KYC y recalcula Profile.verificado."""
        actor_id = int(get_jwt_identity())
        du = db.get_or_404(DocumentoUsuario, doc_usuario_id)
        decision = data["decision"]
        now = datetime.now(timezone.utc)

        du.estado = decision
        du.revisado_en = now
        du.revisor_id = actor_id
        du.nota = data.get("nota")

        user = db.get_or_404(User, du.user_id)
        profile = user.profile
        if profile is None:
            profile = Profile(user_id=user.id)
            db.session.add(profile)
        _recalcular_verificado(user, profile)
        db.session.commit()

        du.requerido = DocumentoRequerido.query.filter_by(
            rol=user.rol.value, clave=du.documento_clave
        ).first()
        return du
