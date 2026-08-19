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
