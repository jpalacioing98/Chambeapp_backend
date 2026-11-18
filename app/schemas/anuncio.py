"""Marshmallow schemas for Anuncios Laborales (ofertas de negocios)."""

from marshmallow import Schema, fields, validate

from app.models.anuncio import (
    EstadoAnuncio,
    EstadoPostulacionAnuncio,
    ModalidadAnuncio,
)


class AnuncioCreateSchema(Schema):
    """Body de creación de un anuncio laboral (negocio)."""

    titulo = fields.String(required=True, validate=validate.Length(min=3, max=200))
    descripcion = fields.String(required=True, validate=validate.Length(min=3, max=4000))
    categoria = fields.String(required=True, validate=validate.Length(min=2, max=120))
    tipo = fields.String(
        required=False,
        load_default="empleo",
        validate=validate.OneOf(["empleo", "servicio", "producto", "oferta"]),
    )
    visible_mapa = fields.Boolean(required=False, load_default=True)
    ubicacion = fields.String(required=False, allow_none=True, validate=validate.Length(max=160))
    latitud = fields.Float(required=False, allow_none=True)
    longitud = fields.Float(required=False, allow_none=True)
    vacantes = fields.Integer(required=False, allow_none=True, validate=validate.Range(min=1))
    # "contacto" (no vinculante, por defecto) | "contrato" (vinculante).
    modalidad = fields.String(
        required=False,
        allow_none=True,
        validate=validate.OneOf(ModalidadAnuncio.values()),
    )
    # Parámetros del contrato (solo cuando modalidad == "contrato").
    presupuesto = fields.Float(required=False, allow_none=True)
    fecha_deseada = fields.Date(required=False, allow_none=True)
    horario = fields.String(required=False, allow_none=True, validate=validate.Length(max=80))


class AnuncioEstadoSchema(Schema):
    """cerrar / abrir un anuncio."""

    accion = fields.String(
        required=True,
        validate=validate.OneOf(["cerrar", "abrir"]),
    )
    # Obligatorio si se cierra sin ningún postulante seleccionado.
    motivo = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=500)
    )


class AnuncioPostulacionCreateSchema(Schema):
    """Body de postulación de un PDS (contacto para el negocio)."""

    mensaje = fields.String(required=False, allow_none=True, validate=validate.Length(max=2000))
    telefono_contacto = fields.String(required=False, allow_none=True, validate=validate.Length(max=40))
    email_contacto = fields.String(required=False, allow_none=True, validate=validate.Email())


class AnuncioPostulacionSchema(Schema):
    """Postulación con datos de contacto (gestión del negocio)."""

    id = fields.Integer()
    anuncio_id = fields.Integer()
    pds_id = fields.Integer()
    # Alias neutro para clientes nuevos. `pds_id` se conserva por compatibilidad.
    postulante_id = fields.Method("get_postulante_id")
    postulante_rol = fields.String()
    pds_nombre = fields.String(dump_only=True, allow_none=True)
    postulante_nombre = fields.Method("get_postulante_nombre")
    seleccionado = fields.Boolean()
    mensaje = fields.String(allow_none=True)
    telefono_contacto = fields.String(allow_none=True)
    email_contacto = fields.String(allow_none=True)
    estado = fields.Enum(EstadoPostulacionAnuncio, by_value=True)
    contract_id = fields.Integer(allow_none=True)
    created_at = fields.DateTime()

    def get_postulante_id(self, obj) -> int:
        return obj.pds_id

    def get_postulante_nombre(self, obj) -> str | None:
        return getattr(obj, "pds_nombre", None)


class PostulacionEstadoSchema(Schema):
    """Gestión del negocio: contactar, descartar o seleccionar."""

    accion = fields.String(
        required=True,
        validate=validate.OneOf(
            ["contactar", "descartar", "seleccionar", "deseleccionar"]
        ),
    )


class AnuncioSchema(Schema):
    """Detalle del anuncio laboral."""

    id = fields.Integer()
    negocio_id = fields.Integer()
    negocio_nombre = fields.String(dump_only=True, allow_none=True)
    titulo = fields.String()
    descripcion = fields.String()
    categoria = fields.String()
    tipo = fields.String()
    visible_mapa = fields.Boolean()
    ubicacion = fields.String(allow_none=True)
    latitud = fields.Float(allow_none=True)
    longitud = fields.Float(allow_none=True)
    vacantes = fields.Integer(allow_none=True)
    modalidad = fields.Enum(ModalidadAnuncio, by_value=True)
    presupuesto = fields.Float(allow_none=True)
    fecha_deseada = fields.Date(allow_none=True)
    horario = fields.String(allow_none=True)
    contract_ids = fields.List(fields.Integer(), allow_none=True)
    motivo_cierre = fields.String(allow_none=True)
    estado = fields.Enum(EstadoAnuncio, by_value=True)
    creado_en = fields.DateTime()
    actualizado_en = fields.DateTime()
    # Solo se incluye para el dueño (dump dinámico por contexto).
    postulaciones = fields.List(
        fields.Nested(AnuncioPostulacionSchema), dump_only=True, allow_none=True
    )
    postulaciones_count = fields.Integer(dump_only=True, dump_default=0)
    # Vacantes aún disponibles (modalidad contrato).
    vacantes_disponibles = fields.Integer(dump_only=True, dump_default=0)