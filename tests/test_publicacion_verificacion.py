"""Publicación de solicitudes ligada a la verificación de identidad (KYC).

Regla de producto: un SOLICITANTE no puede publicar hasta tener aprobados
todos los documentos KYC obligatorios de su rol. El criterio se calcula
contra `documentos_usuario` (no contra el flag `Profile.verificado`, que
puede quedar obsoleto en datos sembrados/migrados).
"""

import pytest

from app import create_app
from app.extensions import db
from app.models.kyc import DocumentoRequerido, DocumentoUsuario
from app.models.user import Profile, User


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


PASSWORD = "secret123"


def _register(client, email, rol="solicitante"):
    return client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "rol": rol,
            "acepto_tyc": True,
            "ip": "127.0.0.1",
        },
    )


def _headers(client, email):
    tokens = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    ).get_json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _publicar(client, headers):
    return client.post(
        "/api/v1/solicitudes/",
        json={
            "titulo": "Reparar fuga",
            "categoria": "plomeria",
            "descripcion": "Fuga bajo el fregadero",
            "ubicacion": "Valledupar",
        },
        headers=headers,
    )


def _catalogo_solicitante(claves=("doc_identidad", "prueba_vida", "verificacion_contacto")):
    """Crea el catálogo de documentos obligatorios del rol solicitante."""
    for i, clave in enumerate(claves):
        db.session.add(
            DocumentoRequerido(
                rol="solicitante",
                clave=clave,
                nombre=clave.replace("_", " ").title(),
                obligatorio=True,
                grupo="identidad",
                orden=i,
            )
        )
    db.session.commit()


def _catalogo_merchant(claves=("doc_identidad", "prueba_vida", "verificacion_contacto")):
    """Catálogo mínimo del merchant (mismo criterio que el solicitante)."""
    for i, clave in enumerate(claves):
        db.session.add(
            DocumentoRequerido(
                rol="merchant",
                clave=clave,
                nombre=clave.replace("_", " ").title(),
                obligatorio=True,
                grupo="identidad",
                orden=i,
            )
        )
    db.session.commit()


def _aprobar(user_id, claves):
    for clave in claves:
        db.session.add(
            DocumentoUsuario(
                user_id=user_id,
                documento_clave=clave,
                rol="solicitante",
                estado="aprobado",
            )
        )
    db.session.commit()


def _user_id(email):
    return User.query.filter_by(email=email).one().id


def test_solicitante_sin_kyc_no_publica(app, client):
    """Sin documentos aprobados, publicar responde 403 con un mensaje guía."""
    app.config["REQUIRE_KYC_TO_PUBLISH"] = True
    _catalogo_solicitante()
    _register(client, "sin-kyc@example.com")
    headers = _headers(client, "sin-kyc@example.com")

    resp = _publicar(client, headers)

    assert resp.status_code == 403
    assert "Verifica tu identidad" in resp.get_json()["message"]


def test_solicitante_con_docs_incompletos_no_publica(app, client):
    """Con solo parte del KYC aprobado sigue bloqueado."""
    app.config["REQUIRE_KYC_TO_PUBLISH"] = True
    _catalogo_solicitante()
    _register(client, "parcial@example.com")
    _aprobar(_user_id("parcial@example.com"), ["doc_identidad", "prueba_vida"])
    headers = _headers(client, "parcial@example.com")

    assert _publicar(client, headers).status_code == 403


def test_solicitante_con_kyc_aprobado_publica(app, client):
    """Con el KYC completo publica y el flag obsoleto se corrige."""
    app.config["REQUIRE_KYC_TO_PUBLISH"] = True
    _catalogo_solicitante()
    _register(client, "verificado@example.com")
    uid = _user_id("verificado@example.com")
    _aprobar(uid, ["doc_identidad", "prueba_vida", "verificacion_contacto"])

    # Simula el flag desincronizado (como sol003 en la BD sembrada).
    with app.app_context():
        perfil = db.session.get(Profile, uid)
        perfil.verificado = False
        db.session.commit()

    resp = _publicar(client, _headers(client, "verificado@example.com"))

    assert resp.status_code == 201
    with app.app_context():
        assert db.session.get(Profile, uid).verificado is True


def test_merchant_sin_kyc_propio_no_publica(app, client):
    """El merchant también exige su KYC mínimo (identidad + vida + contacto)."""
    app.config["REQUIRE_KYC_TO_MERCHANT"] = True
    _catalogo_solicitante()
    _catalogo_merchant()
    _register(client, "comercio@example.com", rol="merchant")

    resp = _publicar(client, _headers(client, "comercio@example.com"))

    assert resp.status_code == 403
    assert "Verifica tu identidad" in resp.get_json()["message"]


def test_config_desactivada_permite_publicar(app, client):
    """TestingConfig trae el gate apagado: los tests históricos no cambian."""
    assert app.config["REQUIRE_KYC_TO_PUBLISH"] is False
    _catalogo_solicitante()
    _register(client, "libre@example.com")

    assert _publicar(client, _headers(client, "libre@example.com")).status_code == 201
