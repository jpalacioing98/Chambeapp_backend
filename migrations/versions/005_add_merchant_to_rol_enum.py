"""Agrega 'MERCHANT' al enum rol de users + tablas merchant_preferences y merchant_payment_methods.

Revision ID: 005_add_merchant_to_rol_enum
Revises: 004_add_negocios_module
Create Date: 2026-09-16

Nombre real del tipo enum en PostgreSQL: rolusuario
(Creado por SQLAlchemy: db.Enum(RolUsuario) → lowercase del nombre de clase).

⚠️ IMPORTANTE — SQLAlchemy persiste el NOMBRE del miembro del enum, NO su .value:
  `class RolUsuario(str, Enum): MERCHANT = "merchant"` se guarda en la BD como
  'MERCHANT' (el nombre del miembro), no como 'merchant'. Por eso esta migración
  agrega el label 'MERCHANT' (mayúscula). Agregar el valor en minúscula rompe el
  INSERT con: `invalid input value for enum rolusuario: "MERCHANT"`.

Decisión de diseño — autocommit_block():
  PostgreSQL NO permite ejecutar `ALTER TYPE ... ADD VALUE` dentro de una
  transacción normal (error: "ALTER TYPE ... ADD cannot run inside a
  transaction block" en PG < 9.1; y en versiones modernas el nuevo valor
  no es visible dentro de la misma transacción). Por eso el DDL del enum
  se aísla con `op.get_context().autocommit_block()`, que hace COMMIT de
  la transacción actual y ejecuta el statement en modo autocommit.

  El bloque DO $$ ... IF NOT EXISTS ... $$ es idempotente: si el label
  'MERCHANT' ya existe en pg_enum, no hace nada. Esto permite re-ejecutar
  la migración sin error.

  Las tablas merchant_preferences y merchant_payment_methods SÍ se crean
  dentro de la transacción normal de Alembic (son DDL transaccional).

Estado real de la BD (2026-09-17) — valor huérfano 'merchant' (minúscula):
  La versión original de esta migración agregó 'merchant' (minúscula) en vez
  de 'MERCHANT'. El tipo rolusuario quedó con AMBOS labels:
  {PDS,SOLICITANTE,VERIFICADOR,SOPORTE,ADMIN,SUPERADMIN,merchant,MERCHANT}.
  El label 'merchant' (minúscula) es un valor huérfano SIN uso: SQLAlchemy
  siempre persiste el NOMBRE del miembro ('MERCHANT'), por lo que ningún
  INSERT/UPDATE usa la minúscula. DECISIÓN: se deja tal cual y se documenta,
  porque PostgreSQL no permite remover un valor de enum sin recrear el tipo
  completo (CREATE TYPE nuevo + ALTER COLUMN + DROP TYPE viejo), y recrearlo
  en una BD con datos es riesgoso. No hay filas que dependan de 'merchant'.

downgrade():
  PostgreSQL NO permite eliminar valores de un enum. Para revertir habría
  que recrear el tipo completo (CREATE TYPE nuevo + ALTER COLUMN + DROP
  TYPE viejo). Por seguridad y simplicidad, el downgrade solo elimina las
  tablas nuevas y deja el enum intacto (no-op documentado).
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '005_add_merchant_to_rol_enum'
down_revision = '004_add_negocios_module'
branch_labels = None
depends_on = None


def upgrade():
    # ── 1. Agregar label 'MERCHANT' al enum rolusuario (idempotente) ─────
    # SQLAlchemy persiste el NOMBRE del miembro del enum, no su .value.
    # RolUsuario.MERCHANT = "merchant" → se guarda como 'MERCHANT'.
    # autocommit_block: ALTER TYPE ... ADD VALUE no puede ejecutarse dentro
    # de una transacción normal en PostgreSQL. Ver docstring.
    with op.get_context().autocommit_block():
        op.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_enum e
                    JOIN pg_type t ON e.enumtypid = t.oid
                    WHERE t.typname = 'rolusuario'
                      AND e.enumlabel = 'MERCHANT'
                ) THEN
                    ALTER TYPE rolusuario ADD VALUE 'MERCHANT';
                END IF;
            END$$;
        """)

    # ── 2. Tabla merchant_preferences ─────────────────────────────────────
    op.create_table(
        'merchant_preferences',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'),
                  nullable=False),
        sa.Column('notif_nueva_solicitud', sa.Boolean(), nullable=False,
                  server_default='1'),
        sa.Column('notif_nueva_resena', sa.Boolean(), nullable=False,
                  server_default='1'),
        sa.Column('notif_estado_kyc', sa.Boolean(), nullable=False,
                  server_default='1'),
        sa.Column('notif_pago_recibido', sa.Boolean(), nullable=False,
                  server_default='1'),
        sa.Column('push_enabled', sa.Boolean(), nullable=False,
                  server_default='1'),
        sa.Column('email_digest', sa.String(10), nullable=False,
                  server_default='daily'),
        sa.Column('creado_en', sa.DateTime(), nullable=True),
        sa.Column('actualizado_en', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('user_id', name='uq_merchant_preferences_user'),
    )
    op.create_index('ix_merchant_preferences_user_id',
                    'merchant_preferences', ['user_id'])

    # ── 3. Tabla merchant_payment_methods ─────────────────────────────────
    op.create_table(
        'merchant_payment_methods',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'),
                  nullable=False),
        sa.Column('tipo', sa.String(30), nullable=False),
        sa.Column('detalle', sa.JSON(), nullable=False),
        sa.Column('principal', sa.Boolean(), nullable=False,
                  server_default='0'),
        sa.Column('activo', sa.Boolean(), nullable=False,
                  server_default='1'),
        sa.Column('creado_en', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_merchant_payment_methods_user_id',
                    'merchant_payment_methods', ['user_id'])


def downgrade():
    # ── Eliminar tablas nuevas ───────────────────────────────────────────
    op.drop_table('merchant_payment_methods')
    op.drop_table('merchant_preferences')

    # PostgreSQL NO permite eliminar valores de enum.
    # Si se necesita revertir, se debe recrear el enum completo
    # (CREATE TYPE nuevo + ALTER COLUMN TYPE + DROP TYPE viejo).
    # No-op documentado por seguridad.
    pass