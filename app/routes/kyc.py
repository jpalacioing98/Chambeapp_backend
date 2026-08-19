"""Blueprint KYC documental por rol (Politica_KYC.md / RF-12).

Endpoints (JWT requerido):
  GET  /api/v1/kyc/documentos-requeridos -> catálogo filtrado por rol del usuario.
  GET  /api/v1/kyc/mis-documentos        -> estado de los documentos del usuario.
  POST /api/v1/kyc/documentos           -> envía (upsert) un documento del usuario (base64 MVP).
  GET  /api/v1/kyc/documentos/mios      -> documentos subidos por el usuario (con catálogo).
  GET  /api/v1/kyc/pendientes           -> docs enviados para revisión (verificador/admin/soporte).
  POST /api/v1/kyc/documentos/<id>/verificar -> aprueba/rechaza (verificador/admin).
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
    tienen un DocumentoUsuario aprobado."""
    obligatorios = DocumentoRequerido.query.filter_by(
        rol=user.rol.value, obligatorio=True
    ).all()
    if not obligatorios:
        return
    claves_oblig = {d.clave for d in obligatorios}
    aprobados = {
        du.documento_clave
        for du in DocumentoUsuario.query.filter_by(
            user_id=user.id, estado="aprobado"
        ).all()
    }
    profile.verificado = claves_oblig.issubset(aprobados)


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
        """Estado de los documentos KYC del usuario, unido con el catálogo."""
        user = _current_user()
        requeridos = DocumentoRequerido.query.filter_by(rol=user.rol.value).all()
        enviados = {
            du.documento_clave: du
            for du in DocumentoUsuario.query.filter_by(user_id=user.id).all()
        }
        documentos = []
        for d in requeridos:
            du = enviados.get(d.clave)
            documentos.append(
                {
                    "clave": d.clave,
                    "nombre": d.nombre,
                    "descripcion": d.descripcion,
                    "obligatorio": d.obligatorio,
                    "grupo": d.grupo,
                    "estado": du.estado if du else "no_enviado",
                    "url": du.url if du else None,
                    "fecha_envio": (
                        du.fecha_envio.isoformat() if du and du.fecha_envio else None
                    ),
                }
            )
        return jsonify({"documentos": documentos}), 200


@blp.route("/documentos")
class Documentos(MethodView):
    @role_required(["pds", "solicitante"])
    @blp.arguments(DocumentoUploadSchema)
    @blp.response(200, DocumentoUsuarioOutSchema)
    def post(self, data):
        """Envía (upsert) un documento KYC válido para el rol del usuario.

        Acepta documento_requerido_id (nuevo) o clave (legacy). El archivo se
        guarda en base64 (MVP sin S3).
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

        du = DocumentoUsuario.query.filter_by(
            user_id=user.id, documento_clave=clave
        ).first()
        now = datetime.now(timezone.utc)
        if du is None:
            du = DocumentoUsuario(
                user_id=user.id,
                documento_clave=clave,
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
