"""Drop payment retention (pago directo, sin retención de fondos).

· payments.liberado_en  → ya no existe la auto-liberación: al confirmar el
  pago queda completado y el monto se transfiere al proveedor.
· disputes.payment_action → la resolución de disputas es solo informativa;
  la plataforma no retiene ni congela fondos.
· enum estadopago → se elimina el valor CONFIRMADO ("en garantía").

Revision ID: 008_drop_payment_retention
Revises: 007_add_solicitud_horario_imagenes
Create Date: 2026-09-18
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '008_drop_payment_retention'
down_revision = '007_add_solicitud_horario_imagenes'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE payments DROP COLUMN IF EXISTS liberado_en")
    op.execute("ALTER TABLE disputes DROP COLUMN IF EXISTS payment_action")

    # Recrear el enum sin CONFIRMADO (Postgres no permite borrar un valor).
    op.execute(
        "UPDATE payments SET estado = 'COMPLETADO' WHERE estado::text = 'CONFIRMADO'"
    )
    op.execute("ALTER TYPE estadopago RENAME TO estadopago_old")
    op.execute(
        "CREATE TYPE estadopago AS ENUM "
        "('PENDIENTE', 'COMPLETADO', 'REEMBOLSADO', 'FALLIDO')"
    )
    op.execute(
        "ALTER TABLE payments ALTER COLUMN estado TYPE estadopago "
        "USING estado::text::estadopago"
    )
    op.execute("DROP TYPE estadopago_old")


def downgrade():
    op.execute("ALTER TYPE estadopago ADD VALUE IF NOT EXISTS 'CONFIRMADO'")
    op.add_column('payments', sa.Column('liberado_en', sa.DateTime(), nullable=True))
    op.add_column(
        'disputes', sa.Column('payment_action', sa.String(20), nullable=True)
    )
