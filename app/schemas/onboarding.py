"""Marshmallow schemas for onboarding (P2-2)."""

from marshmallow import Schema, fields


class OnboardingStatusSchema(Schema):
    """Response for onboarding status check."""

    completed = fields.Boolean()
    step = fields.Integer()
    profile = fields.Raw()


class OnboardingStepSchema(Schema):
    """Body for onboarding step update."""

    step = fields.Integer(required=True)
    data = fields.Raw(required=False, load_default=None)


class OnboardingCompleteSchema(Schema):
    """Body for marking onboarding as complete (empty)."""

    pass
