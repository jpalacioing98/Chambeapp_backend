"""Marshmallow schemas for Chamba (Módulo de Gestión de Chamba)."""

from marshmallow import Schema, fields, validate

from app.models.chamba import EstadoChamba


class ChambaCreateSchema(Schema):
    """Body de creación: contrato firmado del que nace la chamba."""

    contract_id = fields.Integer(required=True)


class ChambaEstadoSchema(Schema):
    """Transición de estado de la chamba."""

    estado = fields.String(
        required=True,
        validate=validate.OneOf(EstadoChamba.values()),
    )
    # Coordenadas GPS del prestador al iniciar obra (hito 2, geo-validación).
    latitud = fields.Float(required=False, allow_none=True)
    longitud = fields.Float(required=False, allow_none=True)


class EvidenciaSchema(Schema):
    """URLs de evidencia (fotos / entorno 360°) subidas a MinIO."""

    urls = fields.List(fields.Url(), required=True, validate=validate.Length(min=1))


class EvidenciaUploadSchema(Schema):
    """Body de subida de evidencia (base64 → MinIO → URL)."""

    archivo_base64 = fields.String(required=True)
    nombre_archivo = fields.String(required=False, allow_none=True)


class EvidenciaUploadResponseSchema(Schema):
    """URL pública de la evidencia subida."""

    url = fields.String()


class AdendaSchema(Schema):
    """Adenda al contrato negociada durante la ejecución."""

    descripcion = fields.String(
        required=True, validate=validate.Length(min=1, max=2000)
    )
    monto_extra = fields.Integer(
        required=False, allow_none=True, validate=validate.Range(min=0)
    )
    tiempo_extra = fields.Integer(
        required=False, allow_none=True, validate=validate.Range(min=0)
    )
    # Unidad del tiempo extra (minutos/horas/días). Default: minutos.
    tiempo_extra_unidad = fields.String(
        required=False,
        validate=validate.OneOf(["minutos", "horas", "dias"]),
        load_default="minutos",
    )
    # ¿Quién cubre el trabajo? pds_actual (se suma a la chamba) u otro_pds
    # (trabajo de otro perfil → candidata a maraña/rebusque).
    cubierta_por = fields.String(
        required=False,
        validate=validate.OneOf(["pds_actual", "otro_pds"]),
        load_default="pds_actual",
    )
    categoria_requerida = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=120)
    )


class AdendaUpdateSchema(Schema):
    """Edición parcial de una adenda (solo el solicitante, no derivada)."""

    descripcion = fields.String(
        required=False, validate=validate.Length(min=1, max=2000)
    )
    monto_extra = fields.Integer(
        required=False, allow_none=True, validate=validate.Range(min=0)
    )
    tiempo_extra = fields.Integer(
        required=False, allow_none=True, validate=validate.Range(min=0)
    )
    tiempo_extra_unidad = fields.String(
        required=False,
        validate=validate.OneOf(["minutos", "horas", "dias"]),
    )
    cubierta_por = fields.String(
        required=False,
        validate=validate.OneOf(["pds_actual", "otro_pds"]),
    )
    categoria_requerida = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=120)
    )


class NovedadSchema(Schema):
    """Novedad / incidencia registrada en sitio (botón de pánico incluido)."""

    tipo = fields.String(
        required=True,
        validate=validate.OneOf(["panic", "tiempo", "inconsistencia", "otro"]),
    )
    descripcion = fields.String(
        required=True, validate=validate.Length(min=1, max=2000)
    )


class PagoSchema(Schema):
    """Confirmación de pago directo (efectivo/transferencia fuera de la app)."""

    monto_final = fields.Integer(required=False, allow_none=True)


class CalificacionSchema(Schema):
    """Calificación final, reseña y habilidades validadas en sitio."""

    estrellas = fields.Integer(
        required=True, validate=validate.Range(min=1, max=5)
    )
    comentario = fields.String(required=False, allow_none=True)
    habilidades = fields.List(fields.Integer(), required=False, allow_none=True)


class ValidacionSchema(Schema):
    """Validación de habilidades en la revisión y validación (Hito 4).

    El solicitante marca las habilidades DEMOSTRADAS del prestador al
    inspeccionar la entrega. La liquidación queda solo para el pago.
    """

    habilidades = fields.List(
        fields.Integer(), required=False, allow_none=True
    )


class ContractResumenSchema(Schema):
    """Resumen del contrato anidado en la chamba."""

    id = fields.Integer()
    service_id = fields.Integer()
    proveedor_id = fields.Integer()
    solicitante_id = fields.Integer()
    estado = fields.String()


class ChambaSchema(Schema):
    """Detalle completo de la chamba."""

    id = fields.Integer()
    contract_id = fields.Integer()
    estado = fields.Enum(EstadoChamba, by_value=True)
    estado_previo = fields.Enum(EstadoChamba, by_value=True, allow_none=True)
    fecha_activacion = fields.DateTime(allow_none=True)
    fecha_inicio_obra = fields.DateTime(allow_none=True)
    fecha_solicitud_cierre = fields.DateTime(allow_none=True)
    fecha_liquidacion = fields.DateTime(allow_none=True)
    fecha_finalizacion = fields.DateTime(allow_none=True)
    evidencia_entrada = fields.List(fields.String(), allow_none=True)
    evidencia_salida = fields.List(fields.String(), allow_none=True)
    adendas = fields.List(fields.Dict(), allow_none=True)
    novedades = fields.List(fields.Dict(), allow_none=True)
    pago_confirmado_solicitante = fields.Boolean()
    pago_confirmado_prestador = fields.Boolean()
    pago_directo_confirmado = fields.Boolean()
    pago_monto_final = fields.Integer(allow_none=True)
    rating_estrellas = fields.Integer(allow_none=True)
    rating_comentario = fields.String(allow_none=True)
    habilidades_validadas = fields.List(fields.Integer(), allow_none=True)
    fecha_validacion = fields.DateTime(allow_none=True)
    creado_en = fields.DateTime()
    actualizado_en = fields.DateTime()
    contract = fields.Nested(ContractResumenSchema, dump_only=True, allow_none=True)