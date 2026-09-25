"""Domain models: Habilidad y HabilidadNivel — rutas de niveles certificables.

Una habilidad/oficio tiene una RUTA con niveles (ej. Básico → Intermedio →
Avanzado). Cada nivel se certifica de dos formas posibles:
· 'quiz'          — evaluación de opción múltiple (aciertos >= 70%).
· 'certificacion' — subida de certificado de estudios/curso.

El progreso por usuario vive en HabilidadNivel (un registro por nivel).
"""

from datetime import datetime, timezone

from app.extensions import db


class Habilidad(db.Model):
    """OFICIO del catálogo (categoría) con sus competencias y ruta certificable.

    · habilidades — competencias específicas del oficio (del catálogo,
      ej. "Termofusión de tuberías").
    · niveles — ruta certificable: [{ nombre, tipo: quiz|certificacion,
      quiz: [...] }] (validación de competencias).
    """

    __tablename__ = "habilidades"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False, unique=True, index=True)
    descripcion = db.Column(db.String(500), nullable=True)
    # Categoría del catálogo nacional (CUOC/SENA):
    # construccion | climatizacion | domesticos | estetica | mecanica
    categoria = db.Column(db.String(60), nullable=True, index=True)
    # Competencias específicas del oficio (lista de strings).
    habilidades = db.Column(db.JSON, nullable=False, default=list)
    # Ruta certificable (niveles quiz/certificación).
    niveles = db.Column(db.JSON, nullable=False, default=list)
    activa = db.Column(db.Boolean, default=True, nullable=False)
    creado_en = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    def to_dict(self, nivel_index: int | None = None) -> dict:
        niveles = self.niveles or []
        out_niveles = []
        for i, n in enumerate(niveles):
            item = {
                "nombre": n.get("nombre", f"Nivel {i + 1}"),
                "tipo": n.get("tipo", "certificacion"),
            }
            # El quiz solo se expone si el usuario lo está presentando.
            if nivel_index is not None and nivel_index == i and n.get("quiz"):
                item["quiz"] = n["quiz"]
            out_niveles.append(item)
        return {
            "id": self.id,
            "nombre": self.nombre,
            "descripcion": self.descripcion,
            "categoria": self.categoria,
            "habilidades": self.habilidades or [],
            "niveles": out_niveles,
            "activa": self.activa,
        }


class HabilidadNivel(db.Model):
    """Progreso del usuario: nivel aprobado de una habilidad."""

    __tablename__ = "habilidad_niveles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    habilidad_id = db.Column(
        db.Integer, db.ForeignKey("habilidades.id"), nullable=False, index=True
    )
    nivel_index = db.Column(db.Integer, nullable=False, default=0)
    metodo = db.Column(db.String(20), nullable=False, default="certificacion")  # quiz | certificacion
    evidencia_url = db.Column(db.String(500), nullable=True)
    fecha = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    __table_args__ = (
        db.UniqueConstraint("user_id", "habilidad_id", "nivel_index", name="uq_hab_nivel_user"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "habilidad_id": self.habilidad_id,
            "nivel_index": self.nivel_index,
            "metodo": self.metodo,
            "evidencia_url": self.evidencia_url,
            "fecha": self.fecha.isoformat() if self.fecha else None,
        }


class EndosoHabilidad(db.Model):
    """Endoso por clientes: el solicitante confirma las competencias que el
    prestador demostró al cerrar una orden (validación social)."""

    __tablename__ = "endoso_habilidades"

    id = db.Column(db.Integer, primary_key=True)
    contract_id = db.Column(
        db.Integer, db.ForeignKey("contracts.id"), nullable=False, index=True
    )
    pds_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    solicitante_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    habilidad_id = db.Column(
        db.Integer, db.ForeignKey("habilidades.id"), nullable=False, index=True
    )
    competencia = db.Column(db.String(150), nullable=False)
    creado_en = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    __table_args__ = (
        db.UniqueConstraint(
            "contract_id", "pds_id", "habilidad_id", "competencia",
            name="uq_endoso_contract_competencia",
        ),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "contract_id": self.contract_id,
            "pds_id": self.pds_id,
            "habilidad_id": self.habilidad_id,
            "competencia": self.competencia,
            "creado_en": self.creado_en.isoformat() if self.creado_en else None,
        }


class CertificacionTecnica(db.Model):
    """Formación técnica certificada (SENA / instituciones): título, código de
    verificación y documento. 'Verificado' habilita insignia y niveles 4-5."""

    __tablename__ = "certificaciones_tecnicas"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    habilidad_id = db.Column(
        db.Integer, db.ForeignKey("habilidades.id"), nullable=True, index=True
    )
    institucion = db.Column(db.String(150), nullable=False)
    titulo = db.Column(db.String(200), nullable=False)
    anio = db.Column(db.Integer, nullable=True)
    codigo_verificacion = db.Column(db.String(120), nullable=True)
    documento_url = db.Column(db.String(500), nullable=True)
    estado = db.Column(
        db.String(20), nullable=False, default="en_revision"
    )  # en_revision | verificado | rechazado
    creado_en = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "habilidad_id": self.habilidad_id,
            "institucion": self.institucion,
            "titulo": self.titulo,
            "anio": self.anio,
            "codigo_verificacion": self.codigo_verificacion,
            "documento_url": self.documento_url,
            "estado": self.estado,
            "creado_en": self.creado_en.isoformat() if self.creado_en else None,
        }