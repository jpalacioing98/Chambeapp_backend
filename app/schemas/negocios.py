"""Marshmallow schemas del módulo Negocios."""

from marshmallow import Schema, fields, validate

from app.models.negocio import TipoNegocio, EstadoNegocio, EstadoReporte, TipoReporte


class HorarioSchema(Schema):
    dia_semana = fields.Integer(required=True, validate=validate.Range(min=0, max=6))
    abierto = fields.Boolean(load_default=True)
    hora_apertura = fields.Time(allow_none=True, format="%H:%M")
    hora_cierre = fields.Time(allow_none=True, format="%H:%M")


class NegocioCreateSchema(Schema):
    nombre = fields.String(required=True, validate=validate.Length(max=150))
    descripcion = fields.String(allow_none=True)
    tipo = fields.String(load_default="comercio",
                         validate=validate.OneOf([e.value for e in TipoNegocio]))
    latitud = fields.Float(required=True)
    longitud = fields.Float(required=True)
    direccion = fields.String(required=True)
    ciudad = fields.String(load_default="Valledupar")
    departamento = fields.String(allow_none=True)
    radio_cobertura_km = fields.Float(load_default=5.0)
    categoria_principal = fields.String(required=True)
    categorias_secundarias = fields.List(fields.String(), load_default=[])
    servicios = fields.List(fields.String(), load_default=[])
    palabras_clave = fields.List(fields.String(), load_default=[])
    whatsapp = fields.String(allow_none=True)
    instagram = fields.String(allow_none=True)
    facebook = fields.String(allow_none=True)
    tiktok = fields.String(allow_none=True)
    sitio_web = fields.String(allow_none=True)


class NegocioUpdateSchema(Schema):
    nombre = fields.String(validate=validate.Length(max=150))
    descripcion = fields.String(allow_none=True)
    tipo = fields.String(validate=validate.OneOf([e.value for e in TipoNegocio]))
    logo_url = fields.String(allow_none=True)
    banner_url = fields.String(allow_none=True)
    imagenes = fields.List(fields.String())
    latitud = fields.Float()
    longitud = fields.Float()
    direccion = fields.String()
    radio_cobertura_km = fields.Float()
    categoria_principal = fields.String()
    categorias_secundarias = fields.List(fields.String())
    servicios = fields.List(fields.String())
    palabras_clave = fields.List(fields.String())
    whatsapp = fields.String(allow_none=True)
    instagram = fields.String(allow_none=True)
    facebook = fields.String(allow_none=True)
    tiktok = fields.String(allow_none=True)
    sitio_web = fields.String(allow_none=True)


class NegocioResponseSchema(Schema):
    id = fields.Integer()
    owner_id = fields.Integer()
    nombre = fields.String()
    slug = fields.String()
    descripcion = fields.String(allow_none=True)
    tipo = fields.String()
    logo_url = fields.String(allow_none=True)
    banner_url = fields.String(allow_none=True)
    imagenes = fields.List(fields.String())
    latitud = fields.Float()
    longitud = fields.Float()
    direccion = fields.String()
    ciudad = fields.String()
    departamento = fields.String(allow_none=True)
    radio_cobertura_km = fields.Float()
    categoria_principal = fields.String()
    categorias_secundarias = fields.List(fields.String())
    servicios = fields.List(fields.String())
    palabras_clave = fields.List(fields.String())
    whatsapp = fields.String(allow_none=True)
    instagram = fields.String(allow_none=True)
    facebook = fields.String(allow_none=True)
    tiktok = fields.String(allow_none=True)
    sitio_web = fields.String(allow_none=True)
    calificacion_promedio = fields.Float()
    total_calificaciones = fields.Integer()
    verificado = fields.Boolean()
    estado = fields.String()
    horarios = fields.List(fields.Nested(HorarioSchema))
    esta_abierto = fields.Method("get_esta_abierto")
    cierra_pronto = fields.Method("get_cierra_pronto")
    creado_en = fields.DateTime()
    actualizado_en = fields.DateTime()

    def get_esta_abierto(self, obj):
        from app.services.negocio_utils import calcular_estado_horario
        return calcular_estado_horario(obj.horarios).get("esta_abierto", False)

    def get_cierra_pronto(self, obj):
        from app.services.negocio_utils import calcular_estado_horario
        return calcular_estado_horario(obj.horarios).get("cierra_pronto", False)


class NegocioReporteSchema(Schema):
    tipo = fields.String(required=True,
                         validate=validate.OneOf([e.value for e in TipoReporte]))
    descripcion = fields.String(allow_none=True)


class NegocioReporteResponseSchema(Schema):
    id = fields.Integer()
    negocio_id = fields.Integer()
    reporter_id = fields.Integer()
    tipo = fields.String()
    descripcion = fields.String(allow_none=True)
    estado = fields.String()
    creado_en = fields.DateTime()


class NegocioRatingCreateSchema(Schema):
    puntaje = fields.Integer(required=True, validate=validate.Range(min=1, max=5))
    comentario = fields.String(allow_none=True)


class NegocioRatingResponseSchema(Schema):
    id = fields.Integer()
    negocio_id = fields.Integer()
    autor_id = fields.Integer()
    autor_nombre = fields.Method("get_autor_nombre")
    puntaje = fields.Integer()
    comentario = fields.String(allow_none=True)
    creado_en = fields.DateTime()

    def get_autor_nombre(self, obj):
        return obj.autor.nombre if obj.autor else None


class NegocioMapPinSchema(Schema):
    id = fields.Integer()
    nombre = fields.String()
    slug = fields.String()
    lat = fields.Float()
    lng = fields.Float()
    categoria = fields.String()
    calificacion = fields.Float()
    verificado = fields.Boolean()
    abierto = fields.Boolean()
    logo_url = fields.String(allow_none=True)


class NegocioMapClusterSchema(Schema):
    lat = fields.Float()
    lng = fields.Float()
    count = fields.Integer()
    items = fields.List(fields.Nested(NegocioMapPinSchema))


class NegocioMapResponseSchema(Schema):
    clusters = fields.List(fields.Nested(NegocioMapClusterSchema))
    pins = fields.List(fields.Nested(NegocioMapPinSchema))
