"""KYC del merchant + verificación de contacto automática por OTP.

Reglas nuevas (2026-11):
· El merchant exige el mismo mínimo que el solicitante: documento de
  identidad, prueba de vida y verificación de contacto. RUT, certificado
  comercial y foto del local quedan opcionales.
· La certificación bancaria del PDS pasa a opcional (los pagos se
  gestionan en una fase posterior).
· El documento `verificacion_contacto` se aprueba automáticamente al
  validar el OTP del celular (no requiere revisión humana).
"""

import pytest

from app import create_app
from app.data.seed_kyc import sync_kyc_catalog
from app.extensions import db
from app.models.kyc import DocumentoRequerido, DocumentoUsuario
from app.models.user import Profile, User

PASSWORD = "secret123"

CLAVES_MERCHANT = ("doc_identidad", "prueba_vida", "verificacion_contacto")


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


def _register(client, email, rol="merchant", telefono=None):
    payload = {
        "email": email,
        "password": PASSWORD,
        "rol": rol,
        "acepto_tyc": True,
        "ip": "127.0.0.1",
    }
    if telefono:
        payload["telefono"] = telefono
    return client.post("/api/v1/auth/register", json=payload)


def _headers(client, email):
    tokens = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    ).get_json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _user_id(email):
    return User.query.filter_by(email=email).one().id


def _catalogo(rol, claves, obligatorio=True):
    for i, clave in enumerate(claves):
        db.session.add(
            DocumentoRequerido(
                rol=rol,
                clave=clave,
                nombre=clave.replace("_", " ").title(),
                obligatorio=obligatorio,
                grupo="identidad",
                orden=i,
            )
        )
    db.session.commit()


def _aprobar(user_id, rol, claves):
    for clave in claves:
        db.session.add(
            DocumentoUsuario(
                user_id=user_id,
                documento_clave=clave,
                rol=rol,
                estado="aprobado",
            )
        )
    db.session.commit()


PUBLICAR = {
    "titulo": "Reparar fuga",
    "categoria": "plomeria",
    "descripcion": "Fuga bajo el fregadero",
    "ubicacion": "Valledupar",
}


def test_merchant_sin_kyc_no_publica(app, client):
    app.config["REQUIRE_KYC_TO_MERCHANT"] = True
    _catalogo("merchant", CLAVES_MERCHANT)
    _register(client, "m1@example.com")

    resp = client.post(
        "/api/v1/solicitudes/", json=PUBLICAR, headers=_headers(client, "m1@example.com")
    )

    assert resp.status_code == 403


def test_merchant_con_kyc_minimo_publica(app, client):
    app.config["REQUIRE_KYC_TO_MERCHANT"] = True
    _catalogo("merchant", CLAVES_MERCHANT)
    _register(client, "m2@example.com")
    _aprobar(_user_id("m2@example.com"), "merchant", CLAVES_MERCHANT)

    resp = client.post(
        "/api/v1/solicitudes/", json=PUBLICAR, headers=_headers(client, "m2@example.com")
    )

    assert resp.status_code == 201


def test_merchant_sin_kyc_no_crea_negocio(app, client):
    app.config["REQUIRE_KYC_TO_MERCHANT"] = True
    _catalogo("merchant", CLAVES_MERCHANT)
    _register(client, "m3@example.com")

    resp = client.post(
        "/api/v1/negocios/",
        json={
            "nombre": "Ferretería El Tornillo",
            "latitud": 10.48,
            "longitud": -73.25,
            "direccion": "Calle 1 # 2-3",
            "categoria_principal": "ferreteria",
        },
        headers=_headers(client, "m3@example.com"),
    )

    assert resp.status_code == 403


def test_merchant_sin_kyc_no_crea_anuncio(app, client):
    app.config["REQUIRE_KYC_TO_MERCHANT"] = True
    _catalogo("merchant", CLAVES_MERCHANT)
    _register(client, "m4@example.com")

    resp = client.post(
        "/api/v1/anuncios/",
        json={
            "titulo": "Ayudante de obra",
            "descripcion": "Apoyo en obra menor",
            "categoria": "construccion",
        },
        headers=_headers(client, "m4@example.com"),
    )

    assert resp.status_code == 403


def test_otp_aprueba_verificacion_contacto(app, client):
    """El OTP aprobado marca el documento sin intervención del verificador."""
    _catalogo("solicitante", ("doc_identidad", "prueba_vida", "verificacion_contacto"))
    _register(client, "otp@example.com", rol="solicitante", telefono="3001112233")
    uid = _user_id("otp@example.com")
    _aprobar(uid, "solicitante", ("doc_identidad", "prueba_vida"))

    headers = _headers(client, "otp@example.com")
    envio = client.post(
        "/api/v1/auth/otp/send",
        json={"telefono": "3001112233"},
        headers=headers,
    ).get_json()
    codigo = envio["dev_code"]

    verif = client.post(
        "/api/v1/auth/otp/verify",
        json={"telefono": "3001112233", "code": codigo},
        headers=headers,
    )

    assert verif.status_code == 200
    doc = DocumentoUsuario.query.filter_by(
        user_id=uid, documento_clave="verificacion_contacto"
    ).one()
    assert doc.estado == "aprobado"
    assert db.session.get(Profile, uid).verificado is True


def test_catalogo_actualiza_obligatoriedad(app):
    """`sync_kyc_catalog` sincroniza los cambios de obligatoriedad."""
    db.session.add(
        DocumentoRequerido(
            rol="pds",
            clave="cert_bancaria",
            nombre="Certificación Bancaria",
            obligatorio=True,
            grupo="financiero",
            orden=8,
        )
    )
    db.session.commit()

    sync_kyc_catalog()

    pds_bancaria = DocumentoRequerido.query.filter_by(
        rol="pds", clave="cert_bancaria"
    ).one()
    pds_identidad = DocumentoRequerido.query.filter_by(
        rol="pds", clave="doc_identidad"
    ).one()
    merchant_rut = DocumentoRequerido.query.filter_by(
        rol="merchant", clave="rut"
    ).one()
    merchant_vida = DocumentoRequerido.query.filter_by(
        rol="merchant", clave="prueba_vida"
    ).one()

    assert pds_bancaria.obligatorio is False
    assert pds_identidad.obligatorio is True
    assert merchant_rut.obligatorio is False
    assert merchant_vida.obligatorio is True
