"""Marshmallow schemas para habilidades (rutas de niveles certificables)."""

from marshmallow import Schema, fields, validate


class NivelHabilidadSchema(Schema):
    """Nivel de la ruta: nombre + método de certificación + quiz opcional."""
    nombre = fields.String(required=True, validate=validate.Length(min=2, max=80))
    tipo = fields.String(
        validate=validate.OneOf(["quiz", "certificacion"]),
        load_default="certificacion",
    )
    # Preguntas del quiz (solo si tipo == 'quiz'):
    # [{ "pregunta": str, "opciones": [str], "correcta": int }]
    quiz = fields.Raw(required=False, allow_none=True)


class HabilidadCreateSchema(Schema):
    nombre = fields.String(required=True, validate=validate.Length(min=2, max=120))
    descripcion = fields.String(required=False, allow_none=True)
    categoria = fields.String(
        required=False,
        allow_none=True,
        validate=validate.OneOf(
            ["construccion", "climatizacion", "domesticos", "estetica", "mecanica"]
        ),
    )
    niveles = fields.List(
        fields.Nested(NivelHabilidadSchema), required=False, load_default=[]
    )


class HabilidadSchema(Schema):
    id = fields.Integer()
    nombre = fields.String()
    descripcion = fields.String(allow_none=True)
    categoria = fields.String(allow_none=True)
    habilidades = fields.Raw(allow_none=True)
    niveles = fields.Raw()
    activa = fields.Boolean()


class EndosoSchema(Schema):
    contract_id = fields.Integer(required=True)
    habilidad_id = fields.Integer(required=True)
    competencia = fields.String(required=False, allow_none=True)
    creado_en = fields.DateTime(allow_none=True)


class CertificacionTecnicaCreateSchema(Schema):
    institucion = fields.String(required=True, validate=validate.Length(min=2, max=150))
    titulo = fields.String(required=True, validate=validate.Length(min=2, max=200))
    habilidad_id = fields.Integer(required=False, allow_none=True)
    anio = fields.Integer(required=False, allow_none=True)
    codigo_verificacion = fields.String(required=False, allow_none=True, validate=validate.Length(max=120))
    archivo_base64 = fields.String(required=False, allow_none=True)
    nombre_archivo = fields.String(required=False, allow_none=True)
    tipo_mime = fields.String(required=False, allow_none=True)
    url = fields.String(required=False, allow_none=True)


class CertificacionTecnicaSchema(Schema):
    id = fields.Integer()
    habilidad_id = fields.Integer(allow_none=True)
    institucion = fields.String()
    titulo = fields.String()
    anio = fields.Integer(allow_none=True)
    codigo_verificacion = fields.String(allow_none=True)
    documento_url = fields.String(allow_none=True)
    estado = fields.String()
    creado_en = fields.DateTime(allow_none=True)


class HabilidadNivelSchema(Schema):
    id = fields.Integer()
    habilidad_id = fields.Integer()
    nivel_index = fields.Integer()
    metodo = fields.String()
    evidencia_url = fields.String(allow_none=True)
    fecha = fields.DateTime(allow_none=True)


class QuizPreguntaSchema(Schema):
    pregunta = fields.String()
    opciones = fields.List(fields.String())


class QuizPreguntasSchema(Schema):
    preguntas = fields.List(fields.Nested(QuizPreguntaSchema))
    nivel = fields.String()


class QuizIntentoSchema(Schema):
    """Respuestas del quiz: índice de la opción elegida por pregunta."""
    respuestas = fields.List(
        fields.Integer(), required=True, validate=validate.Length(min=1)
    )


class QuizResultadoSchema(Schema):
    aprobado = fields.Boolean()
    aciertos = fields.Integer()
    total = fields.Integer()
    mensaje = fields.String()


class CertificacionSchema(Schema):
    """Subida de certificado (base64 o URL) para certificar un nivel."""
    archivo_base64 = fields.String(required=False, allow_none=True)
    nombre_archivo = fields.String(required=False, allow_none=True)
    tipo_mime = fields.String(required=False, allow_none=True)
    url = fields.String(required=False, allow_none=True)


class MessageResponseSchema(Schema):
    message = fields.String(required=True)