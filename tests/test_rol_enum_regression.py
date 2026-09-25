"""Regresión — el enum rolusuario debe contener el NOMBRE de cada miembro de RolUsuario.

Contexto del defecto #1:
  SQLAlchemy persiste el NOMBRE del miembro del enum (PDS, MERCHANT...), NO su
  .value. `RolUsuario.MERCHANT = "merchant"` se guarda como 'MERCHANT' en
  PostgreSQL. La migración 005 agregó 'merchant' (minúscula) en vez de
  'MERCHANT', rompiendo el INSERT de merchants con:
  `invalid input value for enum rolusuario: "MERCHANT"`.

Qué verifica este archivo:
  1. Los miembros de RolUsuario son NOMBRES (mayúsculas) y coinciden con el
     listado esperado del enum (falla si alguien agrega un rol sin migrar).
  2. La migración 005 agrega el label 'MERCHANT' (nombre), nunca 'merchant'
     (valor). Verificable en cualquier entorno (SQLite o Postgres).
  3. En PostgreSQL (marcado para el entorno con PostGIS): cada miembro de
     RolUsuario tiene su NOMBRE presente en pg_enum del tipo rolusuario.
     En SQLite no se puede inspeccionar el tipo enum, por eso se salta.
"""

import pathlib

import pytest

from app import create_app
from app.extensions import db
from app.models.user import RolUsuario

# Nombres (miembros) esperados del enum rolusuario en PostgreSQL.
# Si se agrega un rol nuevo a RolUsuario, este set debe actualizarse
# junto con la migración del enum (ADD VALUE '<NOMBRE>').
EXPECTED_LABELS = {
    "PDS",
    "SOLICITANTE",
    "MERCHANT",
    "VERIFICADOR",
    "SOPORTE",
    "ADMIN",
    "SUPERADMIN",
}


@pytest.fixture
def app():
    app = create_app("app.config.TestingConfig")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _migracion_005_src() -> str:
    """Lee el fuente de la migración 005 (verificable en cualquier entorno)."""
    path = (
        pathlib.Path(__file__).resolve().parents[1]
        / "migrations" / "versions" / "005_add_merchant_to_rol_enum.py"
    )
    return path.read_text(encoding="utf-8")


def test_rolusuario_members_son_nombres_esperados():
    """Los miembros de RolUsuario deben ser NOMBRES y cubrir los 7 roles.

    SQLAlchemy persiste el nombre del miembro; si alguien agrega un rol sin
    actualizar EXPECTED_LABELS (y por tanto sin migrar el enum), este test
    falla y obliga a migrar el tipo en Postgres.
    """
    assert set(RolUsuario.__members__.keys()) == EXPECTED_LABELS


def test_migracion_005_agrega_nombre_no_valor():
    """La migración 005 debe agregar 'MERCHANT' (nombre), nunca 'merchant' (valor)."""
    src = _migracion_005_src()
    assert "ADD VALUE 'MERCHANT'" in src
    assert "enumlabel = 'MERCHANT'" in src
    # El valor en minúscula no debe usarse como label a agregar.
    assert "ADD VALUE 'merchant'" not in src


def test_migracion_005_documenta_valor_huerfano():
    """La migración 005 documenta la decisión sobre el valor huérfano 'merchant'."""
    src = _migracion_005_src()
    assert "valor huérfano" in src


def test_rolusuario_db_enum_contiene_todos_los_nombres(app):
    """Cada miembro de RolUsuario debe tener su NOMBRE en el enum de la BD.

    Solo verificable en PostgreSQL (pg_enum). En SQLite el tipo enum no es
    inspeccionable, por eso se salta (los tests corren en SQLite por defecto;
    este test se activa en el entorno con PostGIS/Postgres).
    """
    if db.engine.dialect.name != "postgresql":
        pytest.skip("Requiere PostgreSQL (pg_enum) para inspeccionar el tipo enum.")

    rows = db.session.execute(
        db.text(
            """
            SELECT e.enumlabel
            FROM pg_enum e
            JOIN pg_type t ON e.enumtypid = t.oid
            WHERE t.typname = 'rolusuario'
            """
        )
    ).scalars().all()
    labels = set(rows)
    for member in RolUsuario.__members__:
        assert member in labels, (
            f"Falta el NOMBRE '{member}' en el enum rolusuario de la BD. "
            f"Agrega: ALTER TYPE rolusuario ADD VALUE '{member}';"
        )