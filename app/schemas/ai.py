"""Marshmallow schemas para recomendaciones (RF-05)."""

from marshmallow import Schema, fields


class RecommendationSchema(Schema):
    """Una recomendación con explicación (transparencia RF-05.4)."""

    user_id = fields.Integer()
    email = fields.Email(allow_none=True)
    score = fields.Float()
    explicacion = fields.String()


class RecommendationsSchema(Schema):
    """Envoltura de lista de recomendaciones."""

    recommendations = fields.List(fields.Nested(RecommendationSchema))
