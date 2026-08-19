"""pytest suite — motor de match / recomendaciones (RF-05)."""

import pytest

from app import create_app
from app.extensions import db
from app.config import TestingConfig
from app.models.user import User


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


def _register(client, email, rol="pds", password="secret123"):
    return client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "rol": rol,
            "acepto_tyc": True,
            "ip": "127.0.0.1",
        },
    )


def _login(client, email, password="secret123"):
    return client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    ).get_json()


def _headers(client, email, password="secret123"):
    return {"Authorization": f"Bearer {_login(client, email, password)['access_token']}"}


def _make_provider(client, email, categorias, habilidades, calificacion, verificado):
    _register(client, email=email, rol="pds")
    h = _headers(client, email)
    client.put(
        "/api/v1/users/me/profile",
        json={
            "categorias": categorias,
            "habilidades": habilidades,
            "zona": "Valledupar",
        },
        headers=h,
    )
    # calificacion_promedio y verificado se fijan directo en BD (app context activo)
    user = db.session.query(User).filter_by(email=email).first()
    user.profile.calificacion_promedio = calificacion
    user.profile.verificado = verificado
    db.session.commit()
    return h


def _make_service(client, email, categoria):
    h = _headers(client, email)
    resp = client.post(
        "/api/v1/solicitudes/",
        json={"titulo": "Reparar grifo", "categoria": categoria, "descripcion": "d", "ubicacion": "Valledupar"},
        headers=h,
    )
    return resp.get_json()["id"]


# ---------------- RF-05.1/2/4: recomendaciones de proveedores ----------------
def test_recommendations_ordered_and_explained(client, app):
    _make_provider(client, "p1@x.com", ["plomeria"], ["tuberia"], 5.0, True)
    _make_provider(client, "p2@x.com", ["jardineria"], [], 3.0, False)
    _make_provider(client, "p3@x.com", ["plomeria", "electricidad"], [], 4.0, True)
    _register(client, email="emp@x.com", rol="solicitante")
    sid = _make_service(client, "emp@x.com", "plomeria")

    resp = client.get(f"/api/v1/ai/recommendations?service_id={sid}")
    assert resp.status_code == 200
    data = resp.get_json()["recommendations"]

    # 3 proveedores con perfil completo
    assert len(data) == 3
    # ordenado por score desc
    scores = [r["score"] for r in data]
    assert scores == sorted(scores, reverse=True)
    # cada item con explicacion no vacía
    assert all(r["explicacion"] for r in data)
    # provider con categoria coincidente primero (p1 score 1.0), sin match ultimo (p2)
    assert data[0]["user_id"] == 1
    assert data[-1]["user_id"] == 2
    # score en rango 0-1
    assert all(0.0 <= r["score"] <= 1.0 for r in data)


def test_recommendations_404(client, app):
    resp = client.get("/api/v1/ai/recommendations?service_id=999")
    assert resp.status_code == 404


def test_recommendations_missing_param(client, app):
    resp = client.get("/api/v1/ai/recommendations")
    assert resp.status_code == 400


# ---------------- RF-05.3: servicios para proveedor ----------------
def test_services_for_provider(client, app):
    _make_provider(client, "prov@x.com", ["plomeria"], [], 4.5, True)
    _register(client, email="emp@x.com", rol="solicitante")
    _make_service(client, "emp@x.com", "plomeria")  # match
    _make_service(client, "emp@x.com", "carpinteria")  # no match

    h = _headers(client, "prov@x.com")
    resp = client.get("/api/v1/ai/solicitudes-for-provider", headers=h)
    assert resp.status_code == 200
    data = resp.get_json()  # ARRAY PLANO (sin envoltura)
    assert isinstance(data, list)
    assert len(data) == 2
    # cada item tiene shape de Service + score/explicacion
    for r in data:
        assert "id" in r and "categoria" in r
        assert all(k in r for k in ("descripcion", "ubicacion", "presupuesto", "estado"))
        assert "score" in r and "explicacion" in r
    # servicio con categoria coincidente primero
    assert data[0]["score"] > data[1]["score"]
    # ordenado por score desc
    scores = [r["score"] for r in data]
    assert scores == sorted(scores, reverse=True)
    assert all(r["explicacion"] for r in data)
    assert all(0.0 <= r["score"] <= 1.0 for r in data)


def test_services_for_provider_requires_jwt(client, app):
    resp = client.get("/api/v1/ai/solicitudes-for-provider")
    assert resp.status_code == 401
