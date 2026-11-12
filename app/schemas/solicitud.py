"""Marshmallow schemas for solicitudes (RF-04)."""

from marshmallow import Schema, fields

from app.models.solicitud import EstadoSolicitud, UrgenciaSolicitud


class SolicitudCreateSchema(Schema):
    """Body de creación. Validación estricta (400) se hace en la ruta."""

    titulo = fields.String(required=True)
    categoria = fields.String(required=False, allow_none=True)
    descripcion = fields.String(required=False, allow_none=True)
    ubicacion = fields.String(required=False, allow_none=True)
    presupuesto = fields.Integer(required=False, allow_none=True)
    fecha_deseada = fields.Date(required=False, allow_none=True)
    urgencia = fields.String(
        required=False,
        allow_none=True,
        validate=fields.validate.OneOf(UrgenciaSolicitud.values()),
    )
    especificaciones_tecnicas = fields.Raw(required=False, allow_none=True)
    imagen_360 = fields.String(required=False, allow_none=True)
    horario = fields.String(required=False, allow_none=True)
    imagenes = fields.List(fields.String(), required=False, allow_none=True)
    latitud = fields.Float(required=False, allow_none=True)
    longitud = fields.Float(required=False, allow_none=True)
    direccion = fields.String(required=False, allow_none=True)
    radio_km = fields.Float(required=False, allow_none=True, load_default=5.0)


class SolicitudEstadoSchema(Schema):
    estado = fields.String(
        required=True, validate=fields.validate.OneOf(EstadoSolicitud.values())
    )


class SolicitudListSchema(Schema):
    """Payload liviano para listados públicos.

    Excluye a propósito `ratings` (N+1), imágenes/especificaciones pesadas y
    las coordenadas exactas (privacidad). Economiza ~80% del JSON.
    """

    id = fields.Integer()
    solicitante_id = fields.Integer()
    titulo = fields.String()
    categoria = fields.String()
    descripcion = fields.String()
    ubicacion = fields.String()
    presupuesto = fields.Integer(allow_none=True)
    fecha_deseada = fields.Date(allow_none=True)
    urgencia = fields.Enum(UrgenciaSolicitud, by_value=True, allow_none=True)
    estado = fields.Enum(EstadoSolicitud, by_value=True)
    horario = fields.String(allow_none=True)
    radio_km = fields.Float(allow_none=True, dump_default=5.0)
    creado_en = fields.DateTime()
    actualizado_en = fields.DateTime()
    advertencia = fields.String(dump_only=True, allow_none=True)
    ofertas_count = fields.Integer(dump_default=0)
    # Distancia REAL (km) del PDS autenticado a la solicitud. La rellena
    # GET /solicitudes/ cuando el solicitante es un PDS con coordenadas.
    # Es lo que necesita el mapa del Chambeador para filtrar por radio:
    # `radio_km` es el radio que pidió el cliente, NO la distancia.
    distancia_km = fields.Float(dump_only=True, allow_none=True)


class SolicitudSchema(Schema):
    id = fields.Integer()
    solicitante_id = fields.Integer()
    categoria = fields.String()
    descripcion = fields.String()
    ubicacion = fields.String()
    presupuesto = fields.Integer(allow_none=True)
    titulo = fields.String()
    fecha_deseada = fields.Date(allow_none=True)
    urgencia = fields.Enum(UrgenciaSolicitud, by_value=True, allow_none=True)
    estado = fields.Enum(EstadoSolicitud, by_value=True)
    especificaciones_tecnicas = fields.Raw(allow_none=True)
    imagen_360 = fields.String(allow_none=True)
    horario = fields.String(allow_none=True)
    imagenes = fields.List(fields.String(), allow_none=True)
    latitud = fields.Float(allow_none=True)
    longitud = fields.Float(allow_none=True)
    direccion = fields.String(allow_none=True)
    radio_km = fields.Float(allow_none=True, dump_default=5.0)
    creado_en = fields.DateTime()
    actualizado_en = fields.DateTime()
    advertencia = fields.String(dump_only=True, allow_none=True)
    # Cuántas ofertas ha recibido. Lo rellena GET /solicitudes/mias con un
    # GROUP BY para que la tarjeta no tenga que pedir las ofertas una a una.
    ofertas_count = fields.Integer(dump_default=0)
    ratings = fields.List(fields.Nested("RatingSchema"), dump_only=True, allow_none=True)


class SolicitudMapaSchema(Schema):
    """Punto anónimo del mapa global (solicitudes y marañas).

    Sin id, título ni dirección: solo ubicación aproximada, categoría y el
    tipo (`chamba` | `marana`) para elegir el icono. El cliente no puede
    saber a qué registro corresponde cada punto.
    """

    lat = fields.Float()
    lng = fields.Float()
    categoria = fields.String(allow_none=True)
    tipo = fields.String(allow_none=True)
