"""Schemas de validación para Portfolio.

Estos schemas definen la estructura de entrada/salida para los
endpoints de portafolio usando Marshmallow.
"""

from marshmallow import Schema, fields, validate


class PortfolioUploadSchema(Schema):
    """Schema para subida de items de portafolio."""
    
    titulo = fields.String(
        required=True,
        validate=validate.Length(min=3, max=100),
        error_messages={'required': 'Título requerido'}
    )
    tipo = fields.String(
        required=True,
        validate=validate.OneOf(['foto', 'video', 'documento']),
        error_messages={'required': 'Tipo requerido'}
    )
    categoria = fields.String(
        required=True,
        validate=validate.Length(min=2, max=50),
        error_messages={'required': 'Categoría requerida'}
    )
    descripcion = fields.String(
        required=False,
        validate=validate.Length(max=500),
        load_default=None
    )


class PortfolioItemSchema(Schema):
    """Schema para serialización de items de portafolio."""
    
    id = fields.Integer(dump_only=True)
    pds_id = fields.Integer(dump_only=True)
    titulo = fields.String()
    descripcion = fields.String(allow_none=True)
    tipo = fields.String()
    categoria = fields.String()
    url = fields.String()
    file_size_bytes = fields.Integer(allow_none=True)
    mime_type = fields.String(allow_none=True)
    estado = fields.String()
    vistas = fields.Integer()
    created_at = fields.DateTime(dump_only=True)


class PortfolioListSchema(Schema):
    """Schema para lista de items de portafolio."""
    
    items = fields.List(fields.Nested(PortfolioItemSchema))
