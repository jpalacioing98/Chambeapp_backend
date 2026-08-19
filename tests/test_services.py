"""pytest suite — services, ratings, perfiles (RF-02, RF-03, RF-04)."""

import pytest

from app import create_app
from app.extensions import db
from app.config import TestingConfig


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


def _register(client, email="w@example.com", rol="trabajador", password="secret123"):
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


def _user(client, email, rol="trabajador"):
    _register(client, email=email, rol=rol)
    return _headers(client, email)


# ---------------- RF-04: crear servicio ----------------
def test_create_service_ok(client):
    h = _user(client, "emp@example.com", rol="empleador")
    resp = client.post(
        "/api/v1/solicitudes/",
        json={
            "categoria": "plomeria",
            "descripcion": "arreglar tuberia",
            "ubicacion": "Valledupar",
        },
        headers=h,
    )
    assert resp.status_code == 201
    d = resp.get_json()
    assert d["categoria"] == "plomeria"
    assert d["estado"] == "publicado"
    assert d["presupuesto"] is None
    assert d["advertencia"] is None


def test_create_service_missing_fields(client):
    h = _user(client, "emp2@example.com", rol="empleador")
    resp = client.post("/api/v1/solicitudes/", json={"categoria": "x"}, headers=h)
    assert resp.status_code == 400


def test_create_service_presupuesto_low(client):
    h = _user(client, "emp3@example.com", rol="empleador")
    resp = client.post(
        "/api/v1/solicitudes/",
        json={
            "categoria": "x",
            "descripcion": "d",
            "ubicacion": "Valledupar",
            "presupuesto": 1000,
        },
        headers=h,
    )
    assert resp.status_code == 400


def test_create_service_sin_presupuesto(client):
    h = _user(client, "emp4@example.com", rol="empleador")
    resp = client.post(
        "/api/v1/solicitudes/",
        json={"categoria": "x", "descripcion": "d", "ubicacion": "Valledupar"},
        headers=h,
    )
    assert resp.status_code == 201
    assert resp.get_json()["presupuesto"] is None


def test_create_service_fuera_valledupar(client):
    h = _user(client, "emp5@example.com", rol="empleador")
    resp = client.post(
        "/api/v1/solicitudes/",
        json={"categoria": "x", "descripcion": "d", "ubicacion": "Bogota"},
        headers=h,
    )
    assert resp.status_code == 201
    assert resp.get_json()["advertencia"] is not None


def test_list_and_filter_services(client):
    h = _user(client, "emp6@example.com", rol="empleador")
    client.post(
        "/api/v1/solicitudes/",
        json={"categoria": "a", "descripcion": "desc uno", "ubicacion": "Valledupar"},
        headers=h,
    )
    client.post(
        "/api/v1/solicitudes/",
        json={"categoria": "b", "descripcion": "desc dos", "ubicacion": "Valledupar"},
        headers=h,
    )
    assert len(client.get("/api/v1/solicitudes/").get_json()) == 2
    assert len(client.get("/api/v1/solicitudes/?categoria=a").get_json()) == 1
    assert len(client.get("/api/v1/solicitudes/?q=uno").get_json()) == 1


def test_detail_404(client):
    _user(client, "emp7@example.com", rol="empleador")
    assert client.get("/api/v1/solicitudes/999").status_code == 404


# ---------------- RF-02: perfil ----------------
def test_update_profile_marks_complete(client):
    h = _user(client, "t1@example.com", rol="trabajador")
    resp = client.put(
        "/api/v1/users/me/profile",
        json={
            "habilidades": ["cocina"],
            "categorias": ["gastronomia"],
            "zona": "Valledupar",
        },
        headers=h,
    )
    assert resp.status_code == 200
    d = resp.get_json()
    assert d["habilidades"] == ["cocina"]
    assert d["categorias"] == ["gastronomia"]
    assert d["perfil_completo"] is True


def test_public_profile_shows_fields(client):
    h = _user(client, "t2@example.com", rol="trabajador")
    client.put(
        "/api/v1/users/me/profile",
        json={"habilidades": ["x"], "categorias": ["y"]},
        headers=h,
    )
    resp = client.get("/api/v1/users/1/profile")
    assert resp.status_code == 200
    d = resp.get_json()
    assert d["habilidades"] == ["x"]
    assert d["sin_calificaciones"] is True
    assert d["calificacion_promedio"] == 0.0


# ---------------- RF-03: ratings ----------------
def test_rating_flow(client):
    emp_h = _user(client, "emp@example.com", rol="empleador")
    create = client.post(
        "/api/v1/solicitudes/",
        json={"categoria": "a", "descripcion": "d", "ubicacion": "Valledupar"},
        headers=emp_h,
    )
    sid = create.get_json()["id"]

    tr_h = _user(client, "tr@example.com", rol="trabajador")

    # completar (dueño = empleador, id 1)
    patch = client.patch(
        f"/api/v1/solicitudes/{sid}/estado",
        json={"estado": "completado"},
        headers=emp_h,
    )
    assert patch.status_code == 200

    # trabajador califica empleador (id 1)
    r = client.post(
        f"/api/v1/solicitudes/{sid}/ratings",
        json={"puntaje": 5, "calificado_id": 1},
        headers=tr_h,
    )
    assert r.status_code == 201

    pub = client.get("/api/v1/users/1/profile")
    assert pub.get_json()["calificacion_promedio"] == 5.0

    # duplicado -> 409
    r2 = client.post(
        f"/api/v1/solicitudes/{sid}/ratings",
        json={"puntaje": 4, "calificado_id": 1},
        headers=tr_h,
    )
    assert r2.status_code == 409

    # rating sin completar -> 409
    create2 = client.post(
        "/api/v1/solicitudes/",
        json={"categoria": "b", "descripcion": "d2", "ubicacion": "Valledupar"},
        headers=emp_h,
    )
    sid2 = create2.get_json()["id"]
    r3 = client.post(
        f"/api/v1/solicitudes/{sid2}/ratings",
        json={"puntaje": 3, "calificado_id": 1},
        headers=tr_h,
    )
    assert r3.status_code == 409


def test_patch_estado_forbidden(client):
    emp_h = _user(client, "emp@example.com", rol="empleador")
    create = client.post(
        "/api/v1/solicitudes/",
        json={"categoria": "a", "descripcion": "d", "ubicacion": "Valledupar"},
        headers=emp_h,
    )
    sid = create.get_json()["id"]
    other_h = _user(client, "other@example.com", rol="empleador")
    resp = client.patch(
        f"/api/v1/solicitudes/{sid}/estado",
        json={"estado": "completado"},
        headers=other_h,
    )
    assert resp.status_code == 403


def test_list_ratings(client):
    emp_h = _user(client, "emp@example.com", rol="empleador")
    create = client.post(
        "/api/v1/solicitudes/",
        json={"categoria": "a", "descripcion": "d", "ubicacion": "Valledupar"},
        headers=emp_h,
    )
    sid = create.get_json()["id"]
    client.patch(
        f"/api/v1/solicitudes/{sid}/estado",
        json={"estado": "completado"},
        headers=emp_h,
    )
    tr_h = _user(client, "tr@example.com", rol="trabajador")
    client.post(
        f"/api/v1/solicitudes/{sid}/ratings",
        json={"puntaje": 4, "calificado_id": 1},
        headers=tr_h,
    )
    resp = client.get(f"/api/v1/solicitudes/{sid}/ratings")
    assert resp.status_code == 200
    assert len(resp.get_json()) == 1
