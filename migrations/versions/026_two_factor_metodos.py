"""2FA: método (SMS/TOTP), secreto y códigos de recuperación

Revision ID: 026_two_factor_metodos
Revises: 025_push_subscriptions
Create Date: 2026-11-11 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "026_two_factor_metodos"
down_revision: Union[str, None] = "025_push_subscriptions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "two_factor_method",
            sa.String(length=10),
            nullable=False,
            server_default="sms",
        ),
    )
    op.add_column(
        "users",
        sa.Column("two_factor_secret", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "two_factor_pending_secret", sa.String(length=255), nullable=True
        ),
    )
    op.add_column(
        "users",
        sa.Column("two_factor_confirmed_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "two_factor_recovery_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "usado", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("usado_en", sa.DateTime(), nullable=True),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "user_id", "code_hash", name="uq_2fa_recovery_user_code"
        ),
    )
    op.create_index(
        "ix_2fa_recovery_user",
        "two_factor_recovery_codes",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_2fa_recovery_user", table_name="two_factor_recovery_codes"
    )
    op.drop_table("two_factor_recovery_codes")
    op.drop_column("users", "two_factor_confirmed_at")
    op.drop_column("users", "two_factor_pending_secret")
    op.drop_column("users", "two_factor_secret")
    op.drop_column("users", "two_factor_method")
