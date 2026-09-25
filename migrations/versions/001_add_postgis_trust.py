"""Add PostGIS support and TrustScore model.

Revision ID: 001_add_postgis_trust
Revises: 
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers
revision = '001_add_postgis_trust'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # 1. Habilitar extensión PostGIS
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    
    # 2. Agregar columna geom (geometry) a profiles (idempotente)
    op.execute(
        "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS geom geometry(POINT, 4326)"
    )

    # 3. Poblar desde latitud/longitud existentes (solo si hay datos)
    op.execute("""
        UPDATE profiles 
        SET geom = ST_SetSRID(ST_MakePoint(longitud, latitud), 4326)
        WHERE latitud IS NOT NULL AND longitud IS NOT NULL
    """)

    # 4. Crear índice espacial (idempotente)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_profiles_geom 
        ON profiles USING GIST (geom)
    """)
    
    # 5. Crear tabla trust_scores
    op.create_table(
        'trust_scores',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('pds_id', sa.Integer(), sa.ForeignKey('users.id'), unique=True, nullable=False),
        sa.Column('kyc_verificado', sa.Boolean(), default=False),
        sa.Column('portfolio_calidad', sa.Float(), default=0.0),
        sa.Column('rating_score', sa.Float(), default=0.0),
        sa.Column('contratos_completados', sa.Integer(), default=0),
        sa.Column('referidos_count', sa.Integer(), default=0),
        sa.Column('puntuacion', sa.Float(), default=0.0),
        sa.Column('nivel', sa.Enum('nuevo', 'confiable', 'verificado', 'experto', name='trust_level'), default='nuevo'),
        sa.Column('componentes_json', sa.JSON()),
        sa.Column('calculado_en', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('version', sa.Integer(), default=1),
    )
    
    # 6. Crear índices para trust_scores
    op.create_index('ix_trust_scores_pds_id', 'trust_scores', ['pds_id'])
    op.create_index('ix_trust_scores_nivel', 'trust_scores', ['nivel'])
    op.create_index('ix_trust_scores_puntuacion', 'trust_scores', ['puntuacion'])
    
    # 7. Agregar feature flags ML
    op.execute("""
        INSERT INTO feature_flags (key, enabled, description) VALUES
        ('ml_ranking_enabled', false, 'Activa el ranking ML (LightGBM)'),
        ('ml_shadow_mode', true, 'Log ML pero usa heurístico'),
        ('cascade_notifications', false, 'Activa notificaciones en cascada'),
        ('portfolio_upload', false, 'Activa upload de portafolio'),
        ('thompson_sampling', false, 'Activa rotación con Bandit')
        ON CONFLICT (key) DO NOTHING
    """)


def downgrade():
    # 1. Eliminar feature flags ML
    op.execute("""
        DELETE FROM feature_flags 
        WHERE key IN ('ml_ranking_enabled', 'ml_shadow_mode', 'cascade_notifications', 
                      'portfolio_upload', 'thompson_sampling')
    """)
    
    # 2. Eliminar índices y tabla trust_scores
    op.drop_index('ix_trust_scores_puntuacion')
    op.drop_index('ix_trust_scores_nivel')
    op.drop_index('ix_trust_scores_pds_id')
    op.drop_table('trust_scores')
    
    # 3. Eliminar tipo enum
    op.execute("DROP TYPE IF EXISTS trust_level")
    
    # 4. Eliminar índice espacial y columna geom
    op.execute("DROP INDEX IF EXISTS idx_profiles_geom")
    op.drop_column('profiles', 'geom')
