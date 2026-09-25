"""Blueprint de HABILIDADES — catálogo con rutas de niveles certificables.

Endpoints (JWT requerido):
  GET  /habilidades                     -> catálogo con sus niveles.
  POST /habilidades                     -> crea una habilidad con su ruta.
  GET  /habilidades/mis-niveles         -> niveles que el usuario certificó.
  POST /habilidades/<id>/nivel/<n>/quiz -> presenta el quiz del nivel.
  POST /habilidades/<id>/nivel/<n>/certificacion -> sube certificado.

Reglas:
· Un nivel tipo 'quiz' se aprueba con >= 70% de aciertos (una sola ronda
  por intento; el intento fallido NO bloquea, se puede reintentar).
· Un nivel tipo 'certificacion' se aprueba subiendo un documento/URL.
· La certificación se registra en habilidad_niveles (uno por nivel).
"""

import base64
import binascii

from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models.habilidad import Habilidad, HabilidadNivel, EndosoHabilidad, CertificacionTecnica
from app.models.contract import Contract
from app.models.solicitud import Solicitud
from app.models.user import User, Profile
from app.schemas.habilidad import (
    HabilidadCreateSchema,
    HabilidadSchema,
    HabilidadNivelSchema,
    QuizPreguntasSchema,
    QuizIntentoSchema,
    QuizResultadoSchema,
    CertificacionSchema,
    CertificacionTecnicaSchema,
    CertificacionTecnicaCreateSchema,
    EndosoSchema,
    MessageResponseSchema,
)

blp = Blueprint("habilidades", __name__, description="Habilidades y rutas certificables")

UMBRAL_QUIZ = 0.8  # 80% de aciertos para aprobar (doc del módulo)


def _get_habilidad(habilidad_id: int) -> Habilidad:
    hab = db.session.get(Habilidad, habilidad_id)
    if hab is None:
        abort(404, message="Habilidad no encontrada.")
    return hab


def _get_nivel(hab: Habilidad, nivel_index: int) -> dict:
    niveles = hab.niveles or []
    if nivel_index < 0 or nivel_index >= len(niveles):
        abort(404, message="Nivel no encontrado.")
    return niveles[nivel_index]


def _registrar_nivel(user_id: int, hab: Habilidad, nivel_index: int, metodo: str, evidencia: str | None = None) -> HabilidadNivel:
    progreso = HabilidadNivel.query.filter_by(
        user_id=user_id, habilidad_id=hab.id, nivel_index=nivel_index
    ).first()
    if progreso is None:
        progreso = HabilidadNivel(
            user_id=user_id,
            habilidad_id=hab.id,
            nivel_index=nivel_index,
            metodo=metodo,
            evidencia_url=evidencia,
        )
        db.session.add(progreso)
    else:
        progreso.metodo = metodo
        progreso.evidencia_url = evidencia
    db.session.commit()
    return progreso


@blp.route("/habilidades")
class HabilidadesList(MethodView):
    @jwt_required()
    @blp.response(200, HabilidadSchema(many=True))
    def get(self):
        """Catálogo de habilidades activas con su ruta de niveles."""
        habs = Habilidad.query.filter_by(activa=True).order_by(Habilidad.nombre).all()
        return [h.to_dict() for h in habs]

    @jwt_required()
    @blp.arguments(HabilidadCreateSchema)
    @blp.response(201, HabilidadSchema)
    def post(self, data):
        """Crea una habilidad/oficio con su ruta de niveles certificables."""
        nombre = data["nombre"].strip()
        if not nombre:
            abort(400, message="El nombre de la habilidad es obligatorio.")
        if Habilidad.query.filter_by(nombre=nombre).first():
            abort(409, message="Ya existe una habilidad con ese nombre.")

        niveles = []
        for n in data.get("niveles", []):
            niveles.append({
                "nombre": n["nombre"].strip(),
                "tipo": n.get("tipo", "certificacion"),
                "quiz": n.get("quiz") if n.get("tipo") == "quiz" else None,
            })

        hab = Habilidad(
            nombre=nombre,
            descripcion=(data.get("descripcion") or "").strip() or None,
            categoria=data.get("categoria"),
            niveles=niveles,
        )
        db.session.add(hab)
        db.session.commit()
        return hab.to_dict()


@blp.route("/habilidades/mis-niveles")
class MisNiveles(MethodView):
    @jwt_required()
    @blp.response(200, HabilidadNivelSchema(many=True))
    def get(self):
        """Niveles certificados por el usuario (progreso de sus rutas)."""
        user_id = int(get_jwt_identity())
        return HabilidadNivel.query.filter_by(user_id=user_id).order_by(
            HabilidadNivel.habilidad_id, HabilidadNivel.nivel_index
        ).all()


@blp.route("/habilidades/<int:habilidad_id>/nivel/<int:nivel_index>/quiz")
class NivelQuiz(MethodView):
    @jwt_required()
    @blp.response(200, QuizPreguntasSchema)
    def get(self, habilidad_id, nivel_index):
        """Preguntas del quiz del nivel (SIN respuestas correctas)."""
        hab = _get_habilidad(habilidad_id)
        nivel = _get_nivel(hab, nivel_index)
        if nivel.get("tipo") != "quiz":
            abort(400, message="Este nivel no tiene quiz.")
        preguntas = nivel.get("quiz") or []
        return {
            "nivel": nivel.get("nombre", f"Nivel {nivel_index + 1}"),
            "preguntas": [
                {"pregunta": p.get("pregunta", ""), "opciones": p.get("opciones", [])}
                for p in preguntas
            ],
        }

    @jwt_required()
    @blp.arguments(QuizIntentoSchema)
    @blp.response(200, QuizResultadoSchema)
    def post(self, data, habilidad_id, nivel_index):
        """Presenta el quiz del nivel: se califica al instante."""
        user_id = int(get_jwt_identity())
        hab = _get_habilidad(habilidad_id)
        nivel = _get_nivel(hab, nivel_index)

        if nivel.get("tipo") != "quiz":
            abort(400, message="Este nivel no tiene quiz, se certifica con documento.")
        preguntas = nivel.get("quiz") or []
        if not preguntas:
            abort(400, message="El quiz de este nivel no tiene preguntas.")

        respuestas = data["respuestas"]
        if len(respuestas) != len(preguntas):
            abort(400, message="Debes responder todas las preguntas.")

        aciertos = 0
        for i, p in enumerate(preguntas):
            if respuestas[i] == p.get("correcta", -1):
                aciertos += 1

        total = len(preguntas)
        aprobado = aciertos / total >= UMBRAL_QUIZ
        if aprobado:
            _registrar_nivel(user_id, hab, nivel_index, "quiz")

        return {
            "aprobado": aprobado,
            "aciertos": aciertos,
            "total": total,
            "mensaje": (
                f"¡Nivel {nivel.get('nombre')} aprobado! {aciertos}/{total} correctas."
                if aprobado
                else f"No alcanzaste el 70%. {aciertos}/{total} correctas. Reintenta."
            ),
        }


@blp.route("/habilidades/<int:habilidad_id>/nivel/<int:nivel_index>/certificacion")
class NivelCertificacion(MethodView):
    @jwt_required()
    @blp.arguments(CertificacionSchema)
    @blp.response(200, HabilidadNivelSchema)
    def post(self, data, habilidad_id, nivel_index):
        """Certifica un nivel subiendo un certificado de estudios/curso."""
        user_id = int(get_jwt_identity())
        hab = _get_habilidad(habilidad_id)
        nivel = _get_nivel(hab, nivel_index)

        if nivel.get("tipo") != "certificacion":
            abort(400, message="Este nivel se certifica con quiz, no con documento.")

        evidencia: str | None = None
        if data.get("url"):
            evidencia = data["url"]
        elif data.get("archivo_base64"):
            try:
                file_bytes = base64.b64decode(data["archivo_base64"])
            except (binascii.Error, ValueError):
                abort(400, message="Certificado base64 inválido.")
            if not file_bytes:
                abort(400, message="El certificado está vacío.")
            try:
                from app.services.storage import storage as storage_svc
                if storage_svc is not None:
                    filename = (data.get("nombre_archivo") or "certificado.png").replace("/", "_")
                    evidencia = storage_svc.upload_avatar(
                        file_bytes, f"cert-{user_id}-{habilidad_id}-{nivel_index}", filename
                    )
            except Exception:
                abort(502, message="No se pudo subir el certificado.")

        if not evidencia:
            abort(400, message="Sube el certificado (archivo o URL).")

        progreso = _registrar_nivel(user_id, hab, nivel_index, "certificacion", evidencia)
        return progreso


@blp.route("/habilidades/<int:habilidad_id>")
class HabilidadDetail(MethodView):
    @jwt_required()
    @blp.response(200, MessageResponseSchema)
    def delete(self, habilidad_id):
        """Elimina una habilidad del catálogo (solo si nadie la certificó)."""
        hab = _get_habilidad(habilidad_id)
        if HabilidadNivel.query.filter_by(habilidad_id=hab.id).first():
            abort(400, message="No se puede eliminar: hay usuarios con niveles certificados.")
        db.session.delete(hab)
        db.session.commit()
        return {"message": "Habilidad eliminada."}


@blp.route("/habilidades/endosar")
class EndosarHabilidad(MethodView):
    """Endoso por clientes (validación social): al cerrar una orden, el
    solicitante confirma las competencias que el prestador demostró."""

    @jwt_required()
    @blp.arguments(EndosoSchema)
    @blp.response(200, EndosoSchema)
    def post(self, data):
        user_id = int(get_jwt_identity())
        contract = db.session.get(Contract, data["contract_id"])
        if contract is None:
            abort(404, message="Contrato no encontrado.")
        if contract.solicitante_id != user_id:
            abort(403, message="Solo el solicitante del contrato puede endosar.")
        if contract.estado != "completado":
            abort(400, message="Solo se puede endosar en contratos completados.")
        hab = _get_habilidad(data["habilidad_id"])

        competencia = (data.get("competencia") or "").strip()
        if competencia:
            if competencia not in (hab.habilidades or []):
                abort(400, message="La competencia no pertenece a este oficio.")

        existente = EndosoHabilidad.query.filter_by(
            contract_id=contract.id,
            pds_id=contract.proveedor_id,
            habilidad_id=hab.id,
            competencia=competencia,
        ).first()
        if existente:
            abort(409, message="Este contrato ya endosó esa competencia.")

        endoso = EndosoHabilidad(
            contract_id=contract.id,
            pds_id=contract.proveedor_id,
            solicitante_id=user_id,
            habilidad_id=hab.id,
            competencia=competencia,
        )
        db.session.add(endoso)
        db.session.commit()
        return endoso


@blp.route("/habilidades/certificaciones")
class CertificacionesTecnicas(MethodView):
    @jwt_required()
    @blp.response(200, CertificacionTecnicaSchema(many=True))
    def get(self):
        """Formación técnica del usuario (títulos SENA/instituciones)."""
        user_id = int(get_jwt_identity())
        return CertificacionTecnica.query.filter_by(user_id=user_id).order_by(
            CertificacionTecnica.creado_en.desc()
        ).all()

    @jwt_required()
    @blp.arguments(CertificacionTecnicaCreateSchema)
    @blp.response(201, CertificacionTecnicaSchema)
    def post(self, data):
        """Carga una certificación técnica. Queda pendiente de verificación
        por un verificador antes de ser aprobada."""
        user_id = int(get_jwt_identity())

        documento: str | None = None
        if data.get("url"):
            documento = data["url"]
        elif data.get("archivo_base64"):
            try:
                file_bytes = base64.b64decode(data["archivo_base64"])
            except (binascii.Error, ValueError):
                abort(400, message="Certificado base64 inválido.")
            if file_bytes:
                try:
                    from app.services.storage import storage as storage_svc
                    if storage_svc is not None:
                        nombre = (data.get("nombre_archivo") or "titulo.png").replace("/", "_")
                        documento = storage_svc.upload_avatar(
                            file_bytes, f"cert-tec-{user_id}-{int(__import__('time').time())}", nombre
                        )
                except Exception:
                    abort(502, message="No se pudo subir el documento.")

        estado = "en_revision"  # Siempre requiere verificación por verificador
        cert = CertificacionTecnica(
            user_id=user_id,
            habilidad_id=data.get("habilidad_id"),
            institucion=data["institucion"].strip(),
            titulo=data["titulo"].strip(),
            anio=data.get("anio"),
            codigo_verificacion=data.get("codigo_verificacion"),
            documento_url=documento,
            estado=estado,
        )
        db.session.add(cert)
        db.session.commit()
        return cert


@blp.route("/habilidades/progreso")
class ProgresoOficios(MethodView):
    """Progresión 1-5 de cada oficio del usuario (doc del módulo).

    N1 Novato: oficio registrado.
    N2 Conocedor: >= 1 quiz aprobado + >= 3 trabajos + rating >= 4.0.
    N3 Práctico: >= 1 quiz aprobado + >= 15 trabajos + rating >= 4.5.
    N4 Maestro: >= 1 quiz + certificación técnica verificada + >= 35 trabajos + rating >= 4.7.
    N5 Experto: >= 1 quiz + certificación técnica verificada + >= 70 trabajos + rating >= 4.8.
    """

    @jwt_required()
    @blp.response(200)
    def get(self):
        user_id = int(get_jwt_identity())
        user = db.get_or_404(User, user_id)
        profile = user.profile
        rating = profile.calificacion_promedio if profile else 0.0

        # Trabajos completados por oficio (vía categoría de la solicitud)
        completados = (
            db.session.query(Contract, Solicitud)
            .join(Solicitud, Solicitud.id == Contract.service_id)
            .filter(Contract.proveedor_id == user_id, Contract.estado == "completado")
            .all()
        )
        por_categoria: dict[str, int] = {}
        for _c, sol in completados:
            cat = (sol.categoria or "").strip().lower()
            por_categoria[cat] = por_categoria.get(cat, 0) + 1

        # Quizzes por oficio
        quizzes = HabilidadNivel.query.filter_by(user_id=user_id, metodo="quiz").all()
        quizzes_por_oficio: dict[int, int] = {}
        for q in quizzes:
            quizzes_por_oficio[q.habilidad_id] = quizzes_por_oficio.get(q.habilidad_id, 0) + 1

        # Certificaciones técnicas verificadas por oficio
        certificados = [
            c.habilidad_id
            for c in CertificacionTecnica.query.filter_by(
                user_id=user_id, estado="verificado"
            ).all()
        ]

        def normalizar(s: str) -> str:
            import unicodedata
            return "".join(
                c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
            ).lower()

        resultados = []
        for nombre in (profile.habilidades or []):
            hab = Habilidad.query.filter(Habilidad.nombre.ilike(nombre.strip())).first()
            if not hab:
                continue
            trabajos = max(
                por_categoria.get(normalizar(hab.nombre), 0),
                por_categoria.get(normalizar(nombre), 0),
            )
            tiene_quiz = quizzes_por_oficio.get(hab.id, 0) >= 1
            tiene_titulo = hab.id in certificados

            # N5: quiz + certificación verificada + 70 trabajos + 4.8
            if tiene_quiz and tiene_titulo and trabajos >= 70 and rating >= 4.8:
                nivel = 5
            # N4: quiz + certificación verificada + 35 trabajos + 4.7
            elif tiene_quiz and tiene_titulo and trabajos >= 35 and rating >= 4.7:
                nivel = 4
            # N3: quiz + 15 trabajos + 4.5
            elif tiene_quiz and trabajos >= 15 and rating >= 4.5:
                nivel = 3
            # N2: quiz + 3 trabajos + 4.0
            elif tiene_quiz and trabajos >= 3 and rating >= 4.0:
                nivel = 2
            else:
                nivel = 1

            resultados.append({
                "habilidad_id": hab.id,
                "oficio": hab.nombre,
                "nivel": nivel,
                "nombre_nivel": ["", "Novato", "Conocedor", "Práctico", "Maestro", "Experto"][nivel],
                "trabajos_completados": trabajos,
                "calificacion": rating,
                "quizzes_aprobados": quizzes_por_oficio.get(hab.id, 0),
                "endosos": 0,
                "titulo_verificado": tiene_titulo,
                "habilidades": hab.habilidades or [],
            })

        return resultados