"""pytest suite — Anuncios Laborales (ofertas no vinculantes de negocios)."""

import pytest

from app import create_app
from app.extensions import db
from app.config import TestingConfig
from app.models.anuncio import AnuncioLaboral, EstadoAnuncio


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


def _register(client, email, rol="pds"):
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "secret123", "rol": rol, "acepto_tyc": True, "ip": "127.0.0.1"},
    )
    # Monedas suficientes para el cobro de publicación de anuncios.
    from app.models.user import User
    from app.models.wallet import Coin, TipoMoneda, Wallet

    u = User.query.filter_by(email=email).first()
    if u is not None:
        wallet = Wallet.query.filter_by(user_id=u.id).first()
        if wallet is None:
            wallet = Wallet(user_id=u.id, monedas_saldo=1000)
            db.session.add(wallet)
        else:
            wallet.monedas_saldo = 1000
        db.session.add(Coin(user_id=u.id, cantidad=1000, tipo=TipoMoneda.GANADA))
        db.session.commit()


def _login(client, email):
    return client.post(
        "/api/v1/auth/login", json={"email": email, "password": "secret123"}
    ).get_json()


def _headers(client, email):
    return {"Authorization": f"Bearer {_login(client, email)['access_token']}"}


def _user_id(app, email):
    with app.app_context():
        from app.models.user import User
        return User.query.filter_by(email=email).first().id


def _anuncio(client, neg_h, titulo="Se busca plomero", categoria="plomeria"):
    return client.post(
        "/api/v1/anuncios/",
        json={
            "titulo": titulo,
            "descripcion": "Necesitamos un plomero para mantenimiento mensual.",
            "categoria": categoria,
            "ubicacion": "Valledupar",
            "latitud": 10.4806,
            "longitud": -73.2495,
            "vacantes": 2,
        },
        headers=neg_h,
    ).get_json()


# ---------------- Creación (solo negocio) ----------------
def test_crear_anuncio_negocio(client):
    _register(client, "neg@example.com", rol="merchant")
    neg_h = _headers(client, "neg@example.com")
    anuncio = _anuncio(client, neg_h)
    assert anuncio["estado"] == "publicado"
    assert anuncio["titulo"] == "Se busca plomero"
    assert anuncio["vacantes"] == 2
    assert anuncio["negocio_nombre"]


def test_crear_anuncio_solo_negocio(client):
    _register(client, "pds@example.com", rol="pds")
    pds_h = _headers(client, "pds@example.com")
    resp = client.post(
        "/api/v1/anuncios/",
        json={"titulo": "Se busca plomero", "descripcion": "Mantenimiento", "categoria": "plomeria"},
        headers=pds_h,
    )
    assert resp.status_code == 403


def test_anuncio_servicio_solo_perfil_publico(client, app):
    _register(client, "neg@example.com", rol="merchant")
    neg_h = _headers(client, "neg@example.com")
    uid = _user_id(app, "neg@example.com")
    r = client.post(
        "/api/v1/anuncios/",
        json={
            "titulo": "Mantenimiento de aire acondicionado",
            "descripcion": "Limpieza y recarga de gas.",
            "categoria": "tecnologia",
            "tipo": "servicio",
            "visible_mapa": False,
            "presupuesto": 80000,
        },
        headers=neg_h,
    )
    assert r.status_code == 201, r.get_json()
    assert r.get_json()["tipo"] == "servicio"
    assert r.get_json()["visible_mapa"] is False

    # No aparece en el mapa/feed público…
    feed = client.get("/api/v1/anuncios/")
    assert feed.status_code == 200
    assert all(a["id"] != r.get_json()["id"] for a in feed.get_json())

    # …pero sí en el perfil público del negocio (sin JWT).
    perfil = client.get(f"/api/v1/anuncios/negocio/{uid}")
    assert perfil.status_code == 200
    assert any(a["id"] == r.get_json()["id"] for a in perfil.get_json())


# ---------------- Feed público (todos los roles) ----------------
def test_crear_anuncio_oferta(client):
    """El tipo oferta (promoción) es válido y sale en el feed del mapa."""
    _register(client, "neg@example.com", rol="merchant")
    neg_h = _headers(client, "neg@example.com")
    r = client.post(
        "/api/v1/anuncios/",
        json={
            "titulo": "2x1 en almuerzos ejecutivos",
            "descripcion": "Promoción válida de lunes a viernes.",
            "categoria": "restaurante",
            "tipo": "oferta",
            "presupuesto": 25000,
            "visible_mapa": True,
        },
        headers=neg_h,
    )
    assert r.status_code == 201, r.get_json()
    body = r.get_json()
    assert body["tipo"] == "oferta"
    assert body["presupuesto"] == 25000

    feed = client.get("/api/v1/anuncios/")
    assert feed.status_code == 200
    assert any(a["id"] == body["id"] for a in feed.get_json())


def test_feed_publico_solo_publicados(client):
    _register(client, "neg@example.com", rol="merchant")
    neg_h = _headers(client, "neg@example.com")
    _anuncio(client, neg_h)
    _register(client, "neg2@example.com", rol="merchant")
    neg2_h = _headers(client, "neg2@example.com")
    _anuncio(client, neg2_h, titulo="Se busca cocinero", categoria="cocina")

    # Un pds y un solicitante ven el mismo feed.
    _register(client, "pds@example.com", rol="pds")
    pds_h = _headers(client, "pds@example.com")
    feed = client.get("/api/v1/anuncios/", headers=pds_h)
    assert feed.status_code == 200
    assert len(feed.get_json()) == 2

    _register(client, "sol@example.com", rol="solicitante")
    sol_h = _headers(client, "sol@example.com")
    feed2 = client.get("/api/v1/anuncios/?categoria=plomeria", headers=sol_h)
    assert len(feed2.get_json()) == 1


# ---------------- Postulación (PDS) ----------------
def test_postular_anuncio(client, app):
    _register(client, "neg@example.com", rol="merchant")
    neg_h = _headers(client, "neg@example.com")
    anuncio = _anuncio(client, neg_h)
    _register(client, "pds@example.com", rol="pds")
    pds_h = _headers(client, "pds@example.com")

    resp = client.post(
        f"/api/v1/anuncios/{anuncio['id']}/postulaciones",
        json={"mensaje": "Tengo 5 años de experiencia", "telefono_contacto": "3001112233"},
        headers=pds_h,
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["estado"] == "pendiente"
    assert body["telefono_contacto"] == "3001112233"
    assert body["pds_nombre"]


def test_postulacion_duplicada(client):
    _register(client, "neg@example.com", rol="merchant")
    neg_h = _headers(client, "neg@example.com")
    anuncio = _anuncio(client, neg_h)
    _register(client, "pds@example.com", rol="pds")
    pds_h = _headers(client, "pds@example.com")
    client.post(f"/api/v1/anuncios/{anuncio['id']}/postulaciones", json={}, headers=pds_h)
    resp = client.post(f"/api/v1/anuncios/{anuncio['id']}/postulaciones", json={}, headers=pds_h)
    assert resp.status_code == 400


def test_postular_solo_pds(client):
    _register(client, "neg@example.com", rol="merchant")
    neg_h = _headers(client, "neg@example.com")
    anuncio = _anuncio(client, neg_h)
    _register(client, "sol@example.com", rol="solicitante")
    sol_h = _headers(client, "sol@example.com")
    resp = client.post(
        f"/api/v1/anuncios/{anuncio['id']}/postulaciones",
        json={},
        headers=sol_h,
    )
    assert resp.status_code == 403


# ---------------- Gestión de contacto (negocio dueño) ----------------
def test_gestion_postulaciones_contactar(client):
    _register(client, "neg@example.com", rol="merchant")
    neg_h = _headers(client, "neg@example.com")
    anuncio = _anuncio(client, neg_h)
    _register(client, "pds@example.com", rol="pds")
    pds_h = _headers(client, "pds@example.com")
    postulacion_id = client.post(
        f"/api/v1/anuncios/{anuncio['id']}/postulaciones",
        json={"mensaje": "Disponible", "telefono_contacto": "3001112233"},
        headers=pds_h,
    ).get_json()["id"]

    # El negocio ve la postulación con los datos de contacto.
    lista = client.get(f"/api/v1/anuncios/{anuncio['id']}/postulaciones", headers=neg_h)
    assert lista.status_code == 200
    assert len(lista.get_json()) == 1
    assert lista.get_json()[0]["telefono_contacto"] == "3001112233"

    # Gestiona: contactar.
    r = client.patch(
        f"/api/v1/anuncios/{anuncio['id']}/postulaciones/{postulacion_id}",
        json={"accion": "contactar"},
        headers=neg_h,
    )
    assert r.status_code == 200
    assert r.get_json()["estado"] == "contactado"

    # Descartar.
    r2 = client.patch(
        f"/api/v1/anuncios/{anuncio['id']}/postulaciones/{postulacion_id}",
        json={"accion": "descartar"},
        headers=neg_h,
    )
    assert r2.status_code == 200
    assert r2.get_json()["estado"] == "descartado"


def test_gestion_solo_dueño(client):
    _register(client, "neg@example.com", rol="merchant")
    neg_h = _headers(client, "neg@example.com")
    anuncio = _anuncio(client, neg_h)
    _register(client, "neg2@example.com", rol="merchant")
    neg2_h = _headers(client, "neg2@example.com")
    _register(client, "pds@example.com", rol="pds")
    pds_h = _headers(client, "pds@example.com")
    pid = client.post(
        f"/api/v1/anuncios/{anuncio['id']}/postulaciones", json={}, headers=pds_h
    ).get_json()["id"]
    resp = client.patch(
        f"/api/v1/anuncios/{anuncio['id']}/postulaciones/{pid}",
        json={"accion": "contactar"},
        headers=neg2_h,
    )
    assert resp.status_code == 403


# ---------------- Cerrar / reabrir ----------------
def test_cerrar_y_reabrir_anuncio(client):
    _register(client, "neg@example.com", rol="merchant")
    neg_h = _headers(client, "neg@example.com")
    anuncio = _anuncio(client, neg_h)

    r1 = client.patch(
        f"/api/v1/anuncios/{anuncio['id']}/estado",
        json={"accion": "cerrar"},
        headers=neg_h,
    )
    assert r1.status_code == 200
    assert r1.get_json()["estado"] == "cerrado"

    # Cerrado: ya no aparece en el feed ni acepta postulaciones.
    feed = client.get("/api/v1/anuncios/", headers=neg_h)
    assert len(feed.get_json()) == 0

    r2 = client.patch(
        f"/api/v1/anuncios/{anuncio['id']}/estado",
        json={"accion": "abrir"},
        headers=neg_h,
    )
    assert r2.status_code == 200
    assert r2.get_json()["estado"] == "publicado"


# ---------------- Anuncios del negocio ----------------
def test_anuncios_del_negocio(client, app):
    _register(client, "neg@example.com", rol="merchant")
    neg_h = _headers(client, "neg@example.com")
    _anuncio(client, neg_h)
    neg_id = _user_id(app, "neg@example.com")
    lista = client.get(f"/api/v1/anuncios/negocio/{neg_id}", headers=neg_h)
    assert lista.status_code == 200
    assert len(lista.get_json()) == 1
    assert lista.get_json()[0]["postulaciones_count"] == 0