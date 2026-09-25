"""pytest — Endpoint público de Términos y Condiciones (sin JWT)."""

import pytest

from app import create_app
from app.extensions import db
from app.models.config import SystemConfig
from app.data.tyc import TYC_CONTENT, TYC_VERSION


@pytest.fixture
def app():
    app = create_app("app.config.TestingConfig")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def _seed_tyc():
    if not SystemConfig.query.filter_by(key="tyc_current").first():
        db.session.add(
            SystemConfig(
                key="tyc_current",
                value_type="json",
                value=SystemConfig.serialize_value(
                    {
                        "version": TYC_VERSION,
                        "content": TYC_CONTENT,
                        "published_at": "2026-01-01T00:00:00+00:00",
                    },
                    "json",
                ),
                description="T&C",
            )
        )
        db.session.commit()


def test_tyc_public_ok(client):
    _seed_tyc()
    r = client.get("/api/v1/legal/tyc")
    assert r.status_code == 200
    data = r.get_json()
    assert data["version"] == TYC_VERSION
    assert data["content"] == TYC_CONTENT
    assert "Términos y Condiciones" in data["content"]


def test_tyc_public_not_found(client):
    r = client.get("/api/v1/legal/tyc")
    assert r.status_code == 404


def test_tyc_incluye_modulo_habilidades_y_contrato(client):
    """Los T&C incorporan el módulo de habilidades y el contrato firmable."""
    _seed_tyc()
    r = client.get("/api/v1/legal/tyc")
    assert r.status_code == 200
    content = r.get_json()["content"]
    assert "Módulo de Habilidades, Certificaciones y Progresión de Oficios" in content
    assert "Contrato de Prestación de Servicios y Firma Electrónica" in content
    assert "80%" in content
    assert "Ley 527 de 1999" in content


def test_politica_datos_incluye_modulo_y_contratos(client):
    """La política de datos incorpora habilidades/certificaciones y contratos."""
    r = client.get("/api/v1/legal/politica-datos")
    assert r.status_code == 200
    content = r.get_json()["content"]
    assert "Datos del Módulo de Habilidades, Certificaciones y Oficios" in content
    assert "Datos de los Contratos y de la Negociación" in content
    assert "Ley 527 de 1999" in content
