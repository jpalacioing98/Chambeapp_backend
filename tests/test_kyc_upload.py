"""pytest — RF-12 Verificación de Identidad: subida base64 y aprobación KYC."""

import pytest
from flask_jwt_extended import create_access_token

from app import create_app
from app.extensions import db
from app.models.user import User, Profile, RolUsuario
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


def _un_obligatorio(rol, clave):
    req = DocumentoRequerido(
        rol=rol, clave=clave, nombre="Unico Obligatorio", descripcion="desc",
        obligatorio=True, grupo="identidad", orden=1,
    )
    db.session.add(req)
    db.session.commit()
    return req


def _subir(client, user, req, b64="data:image/png;base64,AAAA"):
    return client.post(
        "/api/v1/kyc/documentos",
        headers=_headers(user),
        json={
            "documento_requerido_id": req.id,
            "archivo_base64": b64,
            "nombre_archivo": "doc.png",
            "tipo_mime": "image/png",
        },
    )


# --------------------------------------------------------------------------
# 1) pds sube documento (base64) => estado='enviado' y archivo persistido
# --------------------------------------------------------------------------
def test_pds_sube_documento_base64(client):
    pds = _make_user("up1@test.com", RolUsuario.PDS)
    _seed_kyc()
    req = DocumentoRequerido.query.filter_by(rol="pds", clave="doc_identidad").first()
    r = _subir(client, pds, req)
    assert r.status_code == 200
    data = r.get_json()
    assert data["estado"] == "enviado"
    assert data["documento_clave"] == "doc_identidad"
    assert data["documento_requerido_id"] == req.id
    assert data["requerido"]["nombre"] == "Documento de Identidad"

    du = DocumentoUsuario.query.filter_by(
        user_id=pds.id, documento_clave="doc_identidad"
    ).first()
    assert du is not None
    assert du.archivo_base64 == "data:image/png;base64,AAAA"
    assert du.nombre_archivo == "doc.png"
    assert du.tipo_mime == "image/png"


# --------------------------------------------------------------------------
# 2) GET /documentos/mios retorna el documento subido
# --------------------------------------------------------------------------
def test_get_documentos_mios(client):
    pds = _make_user("up2@test.com", RolUsuario.PDS)
    _seed_kyc()
    req = DocumentoRequerido.query.filter_by(rol="pds", clave="doc_identidad").first()
    _subir(client, pds, req)
    r = client.get("/api/v1/kyc/documentos/mios", headers=_headers(pds))
    assert r.status_code == 200
    docs = r.get_json()
    assert isinstance(docs, list)
    d = [x for x in docs if x["documento_clave"] == "doc_identidad"]
    assert d, "el documento subido debe aparecer en /mios"
    assert d[0]["estado"] == "enviado"
    assert d[0]["requerido"]["obligatorio"] is True
    assert d[0]["requerido"]["nombre"] == "Documento de Identidad"


# --------------------------------------------------------------------------
# 3) verificador aprueba => estado='aprobado'
# --------------------------------------------------------------------------
def test_verificador_aprueba(client):
    pds = _make_user("up3@test.com", RolUsuario.PDS)
    verif = _make_user("verif1@test.com", RolUsuario.VERIFICADOR)
    _seed_kyc()
    req = DocumentoRequerido.query.filter_by(rol="pds", clave="doc_identidad").first()
    _subir(client, pds, req)
    du = DocumentoUsuario.query.filter_by(
        user_id=pds.id, documento_clave="doc_identidad"
    ).first()
    r = client.post(
        f"/api/v1/kyc/documentos/{du.id}/verificar",
        headers=_headers(verif),
        json={"decision": "aprobado", "nota": "looks good"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["estado"] == "aprobado"
    assert data["revisor_id"] == verif.id
    assert data["nota"] == "looks good"
    assert data["revisado_en"] is not None


# --------------------------------------------------------------------------
# 4) todos los obligatorios aprobados => Profile.verificado == True
#    (escenario aislado: un único obligatorio para el rol)
# --------------------------------------------------------------------------
def test_verificado_true_todos_obligatorios_aprobados(client):
    pds = _make_user("up4@test.com", RolUsuario.PDS)
    verif = _make_user("verif2@test.com", RolUsuario.VERIFICADOR)
    req = _un_obligatorio("pds", "unico_oblig")
    _subir(client, pds, req)
    du = DocumentoUsuario.query.filter_by(
        user_id=pds.id, documento_clave="unico_oblig"
    ).first()
    r = client.post(
        f"/api/v1/kyc/documentos/{du.id}/verificar",
        headers=_headers(verif),
        json={"decision": "aprobado"},
    )
    assert r.status_code == 200
    profile = Profile.query.get(pds.id)
    assert profile is not None
    assert profile.verificado is True


# --------------------------------------------------------------------------
# 5) verificador rechaza => estado='rechazado' y Profile.verificado == False
# --------------------------------------------------------------------------
def test_verificador_rechaza(client):
    pds = _make_user("up5@test.com", RolUsuario.PDS)
    verif = _make_user("verif3@test.com", RolUsuario.VERIFICADOR)
    req = _un_obligatorio("pds", "unico_oblig2")
    _subir(client, pds, req)
    du = DocumentoUsuario.query.filter_by(
        user_id=pds.id, documento_clave="unico_oblig2"
    ).first()
    r = client.post(
        f"/api/v1/kyc/documentos/{du.id}/verificar",
        headers=_headers(verif),
        json={"decision": "rechazado", "nota": "ilegible"},
    )
    assert r.status_code == 200
    assert r.get_json()["estado"] == "rechazado"
    profile = Profile.query.get(pds.id)
    assert profile is not None
    assert profile.verificado is False


# --------------------------------------------------------------------------
# 6) GET /pendientes (verificador) lista los enviados con datos de usuario
# --------------------------------------------------------------------------
def test_get_pendientes_verificador(client):
    pds = _make_user("up6@test.com", RolUsuario.PDS)
    verif = _make_user("verif4@test.com", RolUsuario.VERIFICADOR)
    _seed_kyc()
    req = DocumentoRequerido.query.filter_by(rol="pds", clave="doc_identidad").first()
    _subir(client, pds, req)
    r = client.get("/api/v1/kyc/pendientes", headers=_headers(verif))
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list)
    d = [x for x in data if x["documento_clave"] == "doc_identidad"]
    assert d, "el doc enviado debe aparecer en /pendientes"
    assert d[0]["estado"] == "enviado"
    assert d[0]["usuario"]["email"] == "up6@test.com"
    assert d[0]["usuario"]["rol"] == "pds"
    assert d[0]["requerido"]["nombre"] == "Documento de Identidad"


# --------------------------------------------------------------------------
# 7) control de acceso: pds no puede listar /pendientes (403)
# --------------------------------------------------------------------------
def test_pds_no_ve_pendientes(client):
    pds = _make_user("up7@test.com", RolUsuario.PDS)
    r = client.get("/api/v1/kyc/pendientes", headers=_headers(pds))
    assert r.status_code == 403


# --------------------------------------------------------------------------
# 8) decisión inválida es rechazada por el schema (422)
# --------------------------------------------------------------------------
def test_decision_invalida(client):
    pds = _make_user("up8@test.com", RolUsuario.PDS)
    verif = _make_user("verif5@test.com", RolUsuario.VERIFICADOR)
    req = _un_obligatorio("pds", "unico_oblig3")
    _subir(client, pds, req)
    du = DocumentoUsuario.query.filter_by(
        user_id=pds.id, documento_clave="unico_oblig3"
    ).first()
    r = client.post(
        f"/api/v1/kyc/documentos/{du.id}/verificar",
        headers=_headers(verif),
        json={"decision": "quizas"},
    )
    assert r.status_code == 422
