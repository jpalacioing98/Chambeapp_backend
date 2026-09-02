"""Schemas: precios sugeridos (RF-28)."""

from marshmallow import Schema, fields


class PriceSuggestionSchema(Schema):
    """Schema para respuesta de precios sugeridos de una categoría."""
    categoria = fields.Str(required=True, metadata={"description": "Categoría del servicio"})
    min = fields.Int(required=True, metadata={"description": "Precio mínimo sugerido (COP)"})
    max = fields.Int(required=True, metadata={"description": "Precio máximo sugerido (COP)"})
    promedio = fields.Int(required=True, metadata={"description": "Precio promedio sugerido (COP)"})
    muestra = fields.Int(required=True, metadata={"description": "Número de solicitudes completadas usadas para el cálculo"})
    moneda = fields.Str(required=True, metadata={"description": "Código de moneda (COP)"})
    fuente = fields.Str(required=True, metadata={"description": "Fuente de los datos: solicitudes_completadas o estimacion_base"})


class CategoryPricesSchema(Schema):
    """Schema para precios de una categoría individual."""
    min = fields.Int(required=True)
    max = fields.Int(required=True)
    promedio = fields.Int(required=True)
    muestra = fields.Int(required=True)


class AllPricesSchema(Schema):
    """Schema para respuesta de todas las categorías."""
    categorias = fields.Dict(
        keys=fields.Str(),
        values=fields.Nested(CategoryPricesSchema),
        required=True,
        metadata={"description": "Precios por categoría"}
    )
    moneda = fields.Str(required=True)
    total_categorias = fields.Int(required=True)
