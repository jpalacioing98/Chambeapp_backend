"""pytest suite — suscripciones premium (RF-11) + límite de postulaciones.

Patrón del repo: fixture app con create_app('app.config.TestingConfig') +
db.create_all/drop_all, _make_user y _headers con create_access_token y claims
role/role_v.
"""

import pytest
from datetime import datetime, timezone
from flask_jwt_extended import create_access_token

from app import create_app
from app.extensions import db
from app.models.user import User, Profile, RolUsuario
from app.models.oferta import Oferta
from app.models.solicitud import Solicitud
from app.models.subscription import Suscripcion


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


def _make_user(email, rol=RolUsuario.PDS, nombre="Pepito"):
    u = User(
        email=email,
        rol=rol,
        nombre=nombre,
        acepto_tyc=True,
        activo=True,
        status="active",
    )
    u.set_password("ChambeApp123!")
    db.session.add(u)
    db.session.commit()
    # Asegura perfil (el registro vía API lo crea; aquí lo creamos a mano).
    if Profile.query.get(u.id) is None:
        db.session.add(Profile(user_id=u.id))
        db.session.commit()
    return u


def _headers(user):
    token = create_access_token(
        identity=str(user.id),
        additional_claims={"role": user.rol.value, "role_v": user.role_version},
    )
    return {"Authorization": f"Bearer {token}"}


def _crear_solicitud(client, headers, titulo="Armar mueble"):
    resp = client.post(
        "/api/v1/solicitudes/",
        json={
            "titulo": titulo,
            "categoria": "carpinteria",
            "descripcion": "armar mueble",
            "ubicacion": "Valledupar",
        },
        headers=headers,
    )
    return resp.get_json()["id"]


# ---------------- catálogo de planes ----------------
def test_get_planes_retorna_3(client):
    resp = client.get("/api/v1/subscriptions/planes")
    assert resp.status_code == 200
    planes = resp.get_json()
    assert len(planes) == 3
    planes_dict = {p["plan"]: p for p in planes}
    assert planes_dict["free"]["precio"] == 0
    assert planes_dict["basico"]["precio"] == 15000
    assert planes_dict["profesional"]["precio"] == 35000
    assert "15 postulaciones por mes" in planes_dict["basico"]["beneficios"]
    assert "Postulaciones ilimitadas" in planes_dict["profesional"]["beneficios"]


# ---------------- planes deshabilitados ----------------
def test_suscribir_profesional_deshabilitado(client):
    pds = _make_user("pds1@example.com", rol=RolUsuario.PDS)
    h = _headers(pds)

    resp = client.post("/api/v1/subscriptions/", json={"plan": "profesional"}, headers=h)
    assert resp.status_code == 403
    assert "deshabilitados" in resp.get_json()["message"].lower()

    profile = Profile.query.get(pds.id)
    assert profile.plan == "free"
    assert profile.destacado is False


def test_cancelar_sin_suscripcion_activa(client):
    pds = _make_user("pds2@example.com", rol=RolUsuario.PDS)
    h = _headers(pds)
    resp = client.post("/api/v1/subscriptions/cancel", headers=h)
    assert resp.status_code in (200, 404)


# ---------------- plan inválido ----------------
def test_plan_invalido_422(client):
    pds = _make_user("pds3@example.com", rol=RolUsuario.PDS)
    h = _headers(pds)
    resp = client.post("/api/v1/subscriptions/", json={"plan": "gold"}, headers=h)
    assert resp.status_code == 422


# ---------------- sin planes: postulaciones sin límite ----------------
def test_postulaciones_sin_limite(client):
    emp = _make_user("emp@example.com", rol=RolUsuario.SOLICITANTE)
    pds = _make_user("pdsfree@example.com", rol=RolUsuario.PDS)
    emp_h = _headers(emp)
    pds_h = _headers(pds)

    sid = _crear_solicitud(client, emp_h)
    for i in range(20):
        r = client.post(
            f"/api/v1/solicitudes/{sid}/ofertas",
            json={"monto": 100000 + i},
            headers=pds_h,
        )
        assert r.status_code == 201, f"oferta {i+1} debió ser 201"


# ---------------- profesional NO tiene límite ----------------
def test_profesional_sin_limite(client):
    emp = _make_user("emp2@example.com", rol=RolUsuario.SOLICITANTE)
    pds = _make_user("pdspro@example.com", rol=RolUsuario.PDS)
    emp_h = _headers(emp)
    pds_h = _headers(pds)

    client.post(
        "/api/v1/subscriptions/", json={"plan": "profesional"}, headers=pds_h
    )

    sid = _crear_solicitud(client, emp_h)
    for i in range(7):
        r = client.post(
            f"/api/v1/solicitudes/{sid}/ofertas",
            json={"monto": 100000 + i},
            headers=pds_h,
        )
        assert r.status_code == 201, f"oferta {i+1} debió ser 201 (profesional)"
