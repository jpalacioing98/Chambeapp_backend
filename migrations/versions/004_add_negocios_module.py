"""Add Negocios module: Negocio, NegocioHorario, NegocioRating, NegocioReporte.

Revision ID: 004_add_negocios_module
Revises: 003_add_user_username
Create Date: 2026-09-15
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '004_add_negocios_module'
down_revision = '003_add_user_username'
branch_labels = None
depends_on = None


def upgrade():
    # ── Enums (CREATE TYPE IF NOT EXISTS via raw SQL) ────────────────
    op.execute("DO $$ BEGIN CREATE TYPE tiponegocio AS ENUM ('comercio','servicio','virtual','hibrido'); EXCEPTION WHEN duplicate_object THEN null; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE estadonegocio AS ENUM ('borrador','pendiente_verificacion','activo','suspendido','rechazado'); EXCEPTION WHEN duplicate_object THEN null; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE tiporeporte AS ENUM ('fraude','spam','contenido_inapropiado','servicio_no_prestado','otro'); EXCEPTION WHEN duplicate_object THEN null; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE estadoreporte AS ENUM ('abierto','investigando','resuelto','desestimado'); EXCEPTION WHEN duplicate_object THEN null; END $$")

    tipo_negocio = sa.Enum(
        'comercio', 'servicio', 'virtual', 'hibrido',
        name='tiponegocio', create_type=False,
    )
    estado_negocio = sa.Enum(
        'borrador', 'pendiente_verificacion', 'activo', 'suspendido', 'rechazado',
        name='estadonegocio', create_type=False,
    )
    tipo_reporte = sa.Enum(
        'fraude', 'spam', 'contenido_inapropiado', 'servicio_no_prestado', 'otro',
        name='tiporeporte', create_type=False,
    )
    estado_reporte = sa.Enum(
        'abierto', 'investigando', 'resuelto', 'desestimado',
        name='estadoreporte', create_type=False,
    )

    # ── Tabla negocios ────────────────────────────────────────────────
    op.create_table(
        'negocios',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id'),
                  nullable=False),
        # Identidad
        sa.Column('nombre', sa.String(150), nullable=False),
        sa.Column('slug', sa.String(170), nullable=False),
        sa.Column('descripcion', sa.Text(), nullable=True),
        sa.Column('tipo', tipo_negocio, nullable=False,
                  server_default='comercio'),
        # Multimedia
        sa.Column('logo_url', sa.String(500), nullable=True),
        sa.Column('banner_url', sa.String(500), nullable=True),
        sa.Column('imagenes', sa.JSON(), nullable=True),
        # Geolocalización
        sa.Column('latitud', sa.Float(), nullable=False),
        sa.Column('longitud', sa.Float(), nullable=False),
        sa.Column('direccion', sa.String(255), nullable=False),
        sa.Column('ciudad', sa.String(100), nullable=False,
                  server_default='Valledupar'),
        sa.Column('departamento', sa.String(100), nullable=True),
        sa.Column('radio_cobertura_km', sa.Float(), nullable=True,
                  server_default='5.0'),
        # Geom se agrega con SQL raw (PostGIS)
        # Categoría y servicios
        sa.Column('categoria_principal', sa.String(120), nullable=False),
        sa.Column('categorias_secundarias', sa.JSON(), nullable=True),
        sa.Column('servicios', sa.JSON(), nullable=True),
        sa.Column('palabras_clave', sa.JSON(), nullable=True),
        # Enlaces externos
        sa.Column('whatsapp', sa.String(30), nullable=True),
        sa.Column('whatsapp_mensaje_pre', sa.Text(), nullable=True),
        sa.Column('instagram', sa.String(255), nullable=True),
        sa.Column('facebook', sa.String(255), nullable=True),
        sa.Column('tiktok', sa.String(255), nullable=True),
        sa.Column('sitio_web', sa.String(255), nullable=True),
        # Reputación
        sa.Column('calificacion_promedio', sa.Float(), nullable=True,
                  server_default='0.0'),
        sa.Column('total_calificaciones', sa.Integer(), nullable=True,
                  server_default='0'),
        sa.Column('verificado', sa.Boolean(), nullable=True,
                  server_default='0'),
        # Estado
        sa.Column('estado', estado_negocio, nullable=False,
                  server_default='borrador'),
        sa.Column('motivo_rechazo', sa.Text(), nullable=True),
        # Timestamps
        sa.Column('creado_en', sa.DateTime(), nullable=True),
        sa.Column('actualizado_en', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_negocios_owner_id', 'negocios', ['owner_id'])
    op.create_index('ix_negocios_slug', 'negocios', ['slug'], unique=True)

    # PostGIS geometry column (raw SQL)
    op.execute(
        "ALTER TABLE negocios ADD COLUMN geom geometry(POINT, 4326)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_negocios_geom "
        "ON negocios USING GIST (geom)"
    )

    # ── Tabla negocio_horarios ────────────────────────────────────────
    op.create_table(
        'negocio_horarios',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('negocio_id', sa.Integer(), sa.ForeignKey('negocios.id'),
                  nullable=False),
        sa.Column('dia_semana', sa.Integer(), nullable=False),
        sa.Column('abierto', sa.Boolean(), nullable=True, server_default='1'),
        sa.Column('hora_apertura', sa.Time(), nullable=True),
        sa.Column('hora_cierre', sa.Time(), nullable=True),
        sa.UniqueConstraint('negocio_id', 'dia_semana',
                            name='uq_negocio_dia'),
    )
    op.create_index('ix_negocio_horarios_negocio_id', 'negocio_horarios',
                    ['negocio_id'])

    # ── Tabla negocio_ratings ─────────────────────────────────────────
    op.create_table(
        'negocio_ratings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('negocio_id', sa.Integer(), sa.ForeignKey('negocios.id'),
                  nullable=False),
        sa.Column('autor_id', sa.Integer(), sa.ForeignKey('users.id'),
                  nullable=False),
        sa.Column('puntaje', sa.Integer(), nullable=False),
        sa.Column('comentario', sa.Text(), nullable=True),
        sa.Column('reportado', sa.Boolean(), nullable=True,
                  server_default='0'),
        sa.Column('creado_en', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('negocio_id', 'autor_id',
                            name='uq_negocio_autor'),
        sa.CheckConstraint('puntaje >= 1 AND puntaje <= 5',
                           name='ck_negocio_rating_puntaje'),
    )
    op.create_index('ix_negocio_ratings_negocio_id', 'negocio_ratings',
                    ['negocio_id'])

    # ── Tabla negocio_reportes ────────────────────────────────────────
    op.create_table(
        'negocio_reportes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('negocio_id', sa.Integer(), sa.ForeignKey('negocios.id'),
                  nullable=False),
        sa.Column('reporter_id', sa.Integer(), sa.ForeignKey('users.id'),
                  nullable=False),
        sa.Column('tipo', tipo_reporte, nullable=False),
        sa.Column('descripcion', sa.Text(), nullable=True),
        sa.Column('estado', estado_reporte, nullable=False,
                  server_default='abierto'),
        sa.Column('ticket_id', sa.Integer(), sa.ForeignKey('tickets.id'),
                  nullable=True),
        sa.Column('creado_en', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_negocio_reportes_negocio_id', 'negocio_reportes',
                    ['negocio_id'])


def downgrade():
    # ── Eliminar tablas (orden inverso por FKs) ───────────────────────
    op.drop_table('negocio_reportes')
    op.drop_table('negocio_ratings')
    op.drop_table('negocio_horarios')

    # PostGIS: índice y columna geom
    op.execute("DROP INDEX IF EXISTS idx_negocios_geom")
    op.execute("ALTER TABLE negocios DROP COLUMN IF EXISTS geom")

    op.drop_index('ix_negocios_slug', table_name='negocios')
    op.drop_index('ix_negocios_owner_id', table_name='negocios')
    op.drop_table('negocios')

    # ── Eliminar enums ────────────────────────────────────────────────
    op.execute("DROP TYPE IF EXISTS estadoreporte")
    op.execute("DROP TYPE IF EXISTS tiporeporte")
    op.execute("DROP TYPE IF EXISTS estadonegocio")
    op.execute("DROP TYPE IF EXISTS tiponegocio")
