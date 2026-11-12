"""Gate de verificación de identidad para el PDS.

Regla de producto: un PDS sin KYC aprobado no puede ofertar en solicitudes,
postularse a marañas ni a anuncios laborales; y no recibe avisos de nuevas
solicitudes (no podría actuar sobre ellos).
"""

import pytest

from app import create_app
from app.extensions import db
from app.models.kyc import DocumentoRequerido, DocumentoUsuario
from app.models.solicitud import Solicitud
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
LAT, LNG = 10.4806, -73.2495  # Valledupar


def _register(client, email, rol):
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


def _catalogo_pds():
    for i, clave in enumerate(("doc_identidad", "antecedentes", "validacion_profesional")):
        db.session.add(
            DocumentoRequerido(
                rol="pds",
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
                rol="pds",
                estado="aprobado",
            )
        )
    db.session.commit()


def _uid(email):
    return User.query.filter_by(email=email).one().id


def _preparar_pds_verificado(app, email, claves):
    """Deja el PDS con KYC completo, perfil completo y ubicación."""
    uid = _uid(email)
    _aprobar(uid, claves)
    with app.app_context():
        perfil = db.session.get(Profile, uid)
        perfil.perfil_completo = True
        perfil.latitud = LAT
        perfil.longitud = LNG
        db.session.commit()
    return uid


def _crear_solicitud(client, headers):
    resp = client.post(
        "/api/v1/solicitudes/",
        json={
            "titulo": "Arreglar tubería",
            "categoria": "plomeria",
            "descripcion": "Fuga bajo el lavaplatos",
            "ubicacion": "Valledupar",
            "latitud": LAT,
            "longitud": LNG,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["id"]


def _ofertar(client, headers, sid):
    return client.post(
        f"/api/v1/solicitudes/{sid}/ofertas",
        json={"monto": 80000, "mensaje": "Puedo el sábado"},
        headers=headers,
    )


TODO_PDS = ("doc_identidad", "antecedentes", "validacion_profesional")


# ── Ofertas en solicitudes ───────────────────────────────────────────


def test_pds_sin_kyc_no_puede_ofertar(app, client):
    app.config["REQUIRE_KYC_TO_OFFER"] = True
    app.config["REQUIRE_KYC_TO_PUBLISH"] = False
    _catalogo_pds()
    _register(client, "sol@example.com", "solicitante")
    _register(client, "pds-sin@example.com", "pds")
    sid = _crear_solicitud(client, _headers(client, "sol@example.com"))

    resp = _ofertar(client, _headers(client, "pds-sin@example.com"), sid)

    assert resp.status_code == 403
    assert "Verifica tu identidad" in resp.get_json()["message"]


def test_pds_con_kyc_aprobado_puede_ofertar(app, client):
    app.config["REQUIRE_KYC_TO_OFFER"] = True
    app.config["REQUIRE_KYC_TO_PUBLISH"] = False
    _catalogo_pds()
    _register(client, "sol2@example.com", "solicitante")
    _register(client, "pds-ok@example.com", "pds")
    _preparar_pds_verificado(app, "pds-ok@example.com", TODO_PDS)
    sid = _crear_solicitud(client, _headers(client, "sol2@example.com"))

    resp = _ofertar(client, _headers(client, "pds-ok@example.com"), sid)

    assert resp.status_code == 201, resp.get_json()


def test_pds_con_kyc_incompleto_no_puede_ofertar(app, client):
    app.config["REQUIRE_KYC_TO_OFFER"] = True
    app.config["REQUIRE_KYC_TO_PUBLISH"] = False
    _catalogo_pds()
    _register(client, "sol3@example.com", "solicitante")
    _register(client, "pds-parcial@example.com", "pds")
    _aprobar(_uid("pds-parcial@example.com"), ["doc_identidad"])
    sid = _crear_solicitud(client, _headers(client, "sol3@example.com"))

    assert (
        _ofertar(client, _headers(client, "pds-parcial@example.com"), sid).status_code
        == 403
    )


def test_config_apagada_permite_ofertar(app, client):
    assert app.config["REQUIRE_KYC_TO_OFFER"] is False
    _catalogo_pds()
    _register(client, "sol4@example.com", "solicitante")
    _register(client, "pds-libre@example.com", "pds")
    sid = _crear_solicitud(client, _headers(client, "sol4@example.com"))

    assert _ofertar(client, _headers(client, "pds-libre@example.com"), sid).status_code == 201


# ── Postulaciones (maraña y anuncio) ─────────────────────────────────
# El gate corre ANTES del get_or_404, así que un id inexistente con un PDS
# no verificado devuelve 403 (gate) y no 404: prueba el gate sin montar
# toda la estructura de chamba/anuncio.


def test_pds_sin_kyc_no_postula_maraña(app, client):
    app.config["REQUIRE_KYC_TO_OFFER"] = True
    _catalogo_pds()
    _register(client, "pds-mar@example.com", "pds")

    resp = client.post(
        "/api/v1/maranas/999999/ofertas",
        json={"monto": 50000, "mensaje": "Disponible"},
        headers=_headers(client, "pds-mar@example.com"),
    )

    assert resp.status_code == 403
    assert "Verifica tu identidad" in resp.get_json()["message"]


def test_pds_sin_kyc_no_postula_anuncio(app, client):
    app.config["REQUIRE_KYC_TO_OFFER"] = True
    _catalogo_pds()
    _register(client, "pds-anu@example.com", "pds")

    resp = client.post(
        "/api/v1/anuncios/999999/postulaciones",
        json={"mensaje": "Me interesa"},
        headers=_headers(client, "pds-anu@example.com"),
    )

    assert resp.status_code == 403
    assert "Verifica tu identidad" in resp.get_json()["message"]


# ── Descubrimiento: no se avisa a quien no puede postular ────────────


def test_descubrimiento_excluye_pds_no_verificados(app, client):
    from app.services.descubrimiento import pds_elegibles

    app.config["REQUIRE_KYC_TO_OFFER"] = True
    app.config["REQUIRE_KYC_TO_PUBLISH"] = False
    _catalogo_pds()
    _register(client, "sol-desc@example.com", "solicitante")
    _register(client, "pds-noverif@example.com", "pds")
    _register(client, "pds-verif@example.com", "pds")
    _preparar_pds_verificado(app, "pds-verif@example.com", TODO_PDS)

    with app.app_context():
        no_verif = db.session.get(Profile, _uid("pds-noverif@example.com"))
        no_verif.perfil_completo = True
        no_verif.latitud = LAT
        no_verif.longitud = LNG
        no_verif.categorias = ["plomeria"]
        verif = db.session.get(Profile, _uid("pds-verif@example.com"))
        verif.categorias = ["plomeria"]
        db.session.add(
            Solicitud(
                solicitante_id=_uid("sol-desc@example.com"),
                titulo="Fuga",
                categoria="plomeria",
                descripcion="x",
                ubicacion="Valledupar",
                latitud=LAT,
                longitud=LNG,
                radio_km=20,
            )
        )
        db.session.commit()
        solicitud = Solicitud.query.filter_by(titulo="Fuga").one()

        elegibles = {u.email for u in pds_elegibles(solicitud)}

    assert "pds-verif@example.com" in elegibles
    assert "pds-noverif@example.com" not in elegibles
