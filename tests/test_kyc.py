"""pytest — KYC documental por rol (Politica_KYC.md)."""

import pytest
from flask_jwt_extended import create_access_token

from app import create_app
from app.extensions import db
from app.models.user import User, RolUsuario
from app.models.kyc import DocumentoRequerido, DocumentoUsuario


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


def _make_user(email, rol):
    u = User(
        email=email, rol=rol, acepto_tyc=True, activo=True, status="active"
    )
    u.set_password("ChambeApp123!")
    db.session.add(u)
    db.session.commit()
    return u


def _headers(user):
    token = create_access_token(
        identity=str(user.id),
        additional_claims={"role": user.rol.value, "role_v": user.role_version},
    )
    return {"Authorization": f"Bearer {token}"}


def _seed_kyc():
    catalogo = [
        ("pds", "doc_identidad", "Documento de Identidad", "desc", True, "identidad", 1),
        ("pds", "prueba_vida", "Prueba de Vida", "desc", True, "identidad", 2),
        ("pds", "antecedentes_judiciales", "Antecedentes", "desc", True, "antecedentes", 3),
        ("pds", "rnmc", "RNMC", "desc", True, "antecedentes", 4),
        ("pds", "cert_bancaria", "Cert Bancaria", "desc", True, "financiero", 5),
        ("pds", "validacion_profesional", "Validacion Profesional", "desc", False, "opcional", 6),
        ("pds", "salud_seguridad", "Salud y Seguridad", "desc", False, "opcional", 7),
        ("solicitante", "doc_identidad", "Documento de Identidad", "desc", True, "identidad", 1),
        ("solicitante", "verificacion_contacto", "Verificacion Contacto", "desc", True, "identidad", 2),
        ("solicitante", "validacion_pago", "Validacion Pago", "desc", True, "financiero", 3),
    ]
    for rol, clave, nombre, descripcion, obligatorio, grupo, orden in catalogo:
        if not DocumentoRequerido.query.filter_by(rol=rol, clave=clave).first():
            db.session.add(
                DocumentoRequerido(
                    rol=rol, clave=clave, nombre=nombre, descripcion=descripcion,
                    obligatorio=obligatorio, grupo=grupo, orden=orden,
                )
            )
    db.session.commit()


def test_documentos_requeridos_pds(client):
    pds = _make_user("pds@test.com", RolUsuario.PDS)
    _seed_kyc()
    r = client.get("/api/v1/kyc/documentos-requeridos", headers=_headers(pds))
    assert r.status_code == 200
    data = r.get_json()
    assert data["rol"] == "pds"
    claves = [d["clave"] for d in data["documentos"]]
    assert len(claves) == 7
    for c in [
        "doc_identidad", "prueba_vida", "antecedentes_judiciales", "rnmc",
        "cert_bancaria", "validacion_profesional", "salud_seguridad",
    ]:
        assert c in claves


def test_documentos_requeridos_solicitante(client):
    s = _make_user("sol@test.com", RolUsuario.SOLICITANTE)
    _seed_kyc()
    r = client.get("/api/v1/kyc/documentos-requeridos", headers=_headers(s))
    assert r.status_code == 200
    data = r.get_json()
    assert data["rol"] == "solicitante"
    claves = [d["clave"] for d in data["documentos"]]
    assert claves == ["doc_identidad", "verificacion_contacto", "validacion_pago"]


def test_enviar_documento(client):
    pds = _make_user("pds2@test.com", RolUsuario.PDS)
    _seed_kyc()
    r = client.post(
        "/api/v1/kyc/documentos",
        headers=_headers(pds),
        json={"clave": "doc_identidad", "url": "http://x"},
    )
    assert r.status_code == 200
    assert r.get_json()["estado"] == "enviado"


def test_mis_documentos_refleja_enviado(client):
    pds = _make_user("pds3@test.com", RolUsuario.PDS)
    _seed_kyc()
    client.post(
        "/api/v1/kyc/documentos", headers=_headers(pds), json={"clave": "doc_identidad"}
    )
    r = client.get("/api/v1/kyc/mis-documentos", headers=_headers(pds))
    assert r.status_code == 200
    docs = {d["clave"]: d["estado"] for d in r.get_json()["documentos"]}
    assert docs["doc_identidad"] == "enviado"
    assert docs["prueba_vida"] == "no_enviado"


def test_clave_invalida_para_rol(client):
    pds = _make_user("pds4@test.com", RolUsuario.PDS)
    _seed_kyc()
    r = client.post(
        "/api/v1/kyc/documentos", headers=_headers(pds), json={"clave": "validacion_pago"}
    )
    assert r.status_code == 400


def test_requiere_jwt(client):
    r = client.get("/api/v1/kyc/documentos-requeridos")
    assert r.status_code == 401
