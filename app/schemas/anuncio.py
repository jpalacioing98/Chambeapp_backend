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
    pds_nombre = fields.String(dump_only=True, allow_none=True)
    mensaje = fields.String(allow_none=True)
    telefono_contacto = fields.String(allow_none=True)
    email_contacto = fields.String(allow_none=True)
    estado = fields.Enum(EstadoPostulacionAnuncio, by_value=True)
    contract_id = fields.Integer(allow_none=True)
    created_at = fields.DateTime()


class PostulacionEstadoSchema(Schema):
    """Gestión de contacto: contactar / descartar."""

    accion = fields.String(
        required=True,
        validate=validate.OneOf(["contactar", "descartar"]),
    )


class ContratarPostulacionSchema(Schema):
    """Body para contratar a un postulante de un anuncio vinculante.

    Todos los campos son opcionales: por defecto se toma el presupuesto,
    fecha y horario definidos en el anuncio. Permite ajustar el valor
    pactado en el momento de contratar.
    """

    monto = fields.Float(required=False, allow_none=True)
    fecha_deseada = fields.Date(required=False, allow_none=True)
    horario = fields.String(required=False, allow_none=True, validate=validate.Length(max=80))
    condiciones = fields.List(fields.String(), required=False, allow_none=True)


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