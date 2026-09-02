"""Tests: precios sugeridos RF-28."""

import pytest
from app import create_app
from app.extensions import db as _db
from app.models.user import User, RolUsuario
from app.models.solicitud import Solicitud, EstadoSolicitud


@pytest.fixture(scope="module")
def app():
    app = create_app("app.config.TestingConfig")
    with app.app_context():
        _db.create_all()
        yield app
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def _create_user(client, email, rol=RolUsuario.SOLICITANTE):
    """Helper para crear un usuario."""
    with client.application.app_context():
        from app.extensions import bcrypt as _bcrypt
        user = User(
            email=email,
            nombre=email.split("@")[0],
            rol=rol,
            acepto_tyc=True,
        )
        user.set_password("Test1234!")
        _db.session.add(user)
        _db.session.commit()
        return user.id


def _create_solicitud_completada(client, solicitante_id, categoria, presupuesto):
    """Helper para crear una solicitud completada."""
    with client.application.app_context():
        sol = Solicitud(
            solicitante_id=solicitante_id,
            titulo=f"Servicio de {categoria}",
            categoria=categoria,
            descripcion=f"Servicio de {categoria} completado",
            ubicacion="Valledupar",
            presupuesto=presupuesto,
            estado=EstadoSolicitud.COMPLETADO,
        )
        _db.session.add(sol)
        _db.session.commit()
        return sol.id


def test_precios_plomeria_base(client):
    """RF-28: Retorna precios base cuando no hay solicitudes completadas."""
    resp = client.get("/api/v1/prices/precios/plomeria")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["categoria"] == "plomeria"
    assert "min" in data
    assert "max" in data
    assert "promedio" in data
    assert data["moneda"] == "COP"


def test_precios_categoria_invalida(client):
    """RF-28: Retorna 404 para categoría no válida."""
    resp = client.get("/api/v1/prices/precios/categoria_fantasma")
    assert resp.status_code == 404


def test_precios_con_solicitudes_completadas(client):
    """RF-28: Calcula precios reales basados en solicitudes completadas."""
    from app.extensions import cache as _cache
    _cache.clear()

    user_id = _create_user(client, "precios_test@test.com")
    _create_solicitud_completada(client, user_id, "plomeria", 100000)
    _create_solicitud_completada(client, user_id, "plomeria", 200000)

    resp = client.get("/api/v1/prices/precios/plomeria")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["muestra"] == 2
    assert data["min"] == 100000
    assert data["max"] == 200000
    assert data["promedio"] == 150000
    assert data["fuente"] == "solicitudes_completadas"


def test_todas_las_categorias(client):
    """RF-28: Retorna precios para todas las categorías."""
    resp = client.get("/api/v1/prices/precios")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "categorias" in data
    assert "plomeria" in data["categorias"]
    assert "electricidad" in data["categorias"]
    assert data["moneda"] == "COP"
    assert data["total_categorias"] > 0
