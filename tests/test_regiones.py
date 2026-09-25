"""pytest — División regional (Fase 4): administración por regiones.

Cubre:
  - GET /api/v1/regions (catálogo).
  - Superadmin crea admin/soporte/verificador con región.
  - Admin regional: solo ve y modera recursos de su región; crea su propio
    personal (verificador/soporte) vía /admin/staff.
  - Verificador: solo ve la cola KYC de su región.
  - Soporte: solo gestiona tickets de su región.
"""

import pytest
from flask_jwt_extended import create_access_token

from app import create_app
from app.extensions import db
from app.models.user import User, RolUsuario, Verification, Profile
from app.models.region import Region
from app.models.kyc import DocumentoRequerido, DocumentoUsuario
from app.models.ticket import Ticket
from app.models.solicitud import Solicitud, EstadoSolicitud
from app.models.contract import Contract, EstadoContrato, Dispute
from app.models.payment import Payment, EstadoPago


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


def _make_region(clave, nombre, departamentos=None):
    r = Region(clave=clave, nombre=nombre, departamentos=departamentos or [])
    db.session.add(r)
    db.session.commit()
    return r


def _make_user(email, rol, nombre=None, region=None, status="active"):
    u = User(
        email=email,
        rol=rol,
        nombre=nombre,
        acepto_tyc=True,
        activo=True,
        status=status,
        region_id=region.id if region else None,
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


# ---------------- catálogo de regiones ----------------

def test_regions_list_200(client):
    r1 = _make_region("caribe", "Región Caribe")
    r2 = _make_region("andina", "Región Andina")
    user = _make_user("u@x.com", RolUsuario.PDS, "U")
    resp = client.get("/api/v1/regions", headers=_headers(user))
    assert resp.status_code == 200
    claves = {item["clave"] for item in resp.get_json()["items"]}
    assert {"caribe", "andina"} <= claves
    assert r1.nombre in {item["nombre"] for item in resp.get_json()["items"]}
    assert r2.id is not None


# ---------------- superadmin crea personal con región ----------------

def test_superadmin_crea_admin_con_region(client):
    sa = _make_user("sa@x.com", RolUsuario.SUPERADMIN, "SA")
    region = _make_region("pacifica", "Región Pacífica")
    r = client.post(
        "/api/v1/superadmin/admins",
        headers=_headers(sa),
        json={
            "email": "admin-p@chambeapp.com",
            "nombre": "Admin Pacífico",
            "rol": "admin",
            "password": "Clave123!",
            "region_id": region.id,
        },
    )
    assert r.status_code == 201
    item = r.get_json()["items"][0]
    assert item["rol"] == "admin"
    assert item["region"]["id"] == region.id
    assert item["region"]["clave"] == "pacifica"


def test_superadmin_crea_admin_region_invalida_400(client):
    sa = _make_user("sa@x.com", RolUsuario.SUPERADMIN, "SA")
    r = client.post(
        "/api/v1/superadmin/admins",
        headers=_headers(sa),
        json={
            "email": "x@chambeapp.com",
            "nombre": "X",
            "rol": "soporte",
            "password": "Clave123!",
            "region_id": 9999,
        },
    )
    assert r.status_code == 400


def test_superadmin_lista_admins_con_region(client):
    sa = _make_user("sa@x.com", RolUsuario.SUPERADMIN, "SA")
    region = _make_region("andina", "Región Andina")
    _make_user("v@x.com", RolUsuario.VERIFICADOR, "V", region=region)
    r = client.get("/api/v1/superadmin/admins", headers=_headers(sa))
    assert r.status_code == 200
    items = r.get_json()["items"]
    assert any(i["email"] == "v@x.com" and i["region"]["id"] == region.id for i in items)


# ---------------- admin regional: alcance de usuarios ----------------

def test_admin_regional_solo_ve_su_region(client):
    rA = _make_region("caribe", "Región Caribe")
    rB = _make_region("andina", "Región Andina")
    admin = _make_user("admin-a@x.com", RolUsuario.ADMIN, "Admin A", region=rA)
    user_a = _make_user("a@x.com", RolUsuario.PDS, "A", region=rA)
    user_b = _make_user("b@x.com", RolUsuario.PDS, "B", region=rB)
    no_region = _make_user("c@x.com", RolUsuario.PDS, "C", region=None)

    r = client.get("/api/v1/admin/users", headers=_headers(admin))
    assert r.status_code == 200
    emails = {item["email"] for item in r.get_json()["items"]}
    assert user_a.email in emails
    assert admin.email in emails
    assert user_b.email not in emails
    assert no_region.email not in emails


def test_superadmin_ve_todas_las_regiones(client):
    rA = _make_region("caribe", "Región Caribe")
    rB = _make_region("andina", "Región Andina")
    sa = _make_user("sa@x.com", RolUsuario.SUPERADMIN, "SA")
    _make_user("a@x.com", RolUsuario.PDS, "A", region=rA)
    _make_user("b@x.com", RolUsuario.PDS, "B", region=rB)

    r = client.get("/api/v1/admin/users", headers=_headers(sa))
    emails = {item["email"] for item in r.get_json()["items"]}
    assert {"a@x.com", "b@x.com"} <= emails


# ---------------- admin regional: crear personal (verificador/soporte) ----------------

def test_admin_crea_verificador_en_su_region(client):
    region = _make_region("caribe", "Región Caribe")
    admin = _make_user("admin@x.com", RolUsuario.ADMIN, "Admin", region=region)

    r = client.post(
        "/api/v1/admin/staff",
        headers=_headers(admin),
        json={"email": "verif@chambeapp.com", "nombre": "Verif Caribe", "rol": "verificador", "password": "Clave123!"},
    )
    assert r.status_code == 201
    item = r.get_json()["items"][0]
    assert item["rol"] == "verificador"
    assert item["region"]["id"] == region.id
    created = db.session.get(User, item["id"])
    assert created.region_id == region.id


def test_admin_crea_soporte_en_su_region(client):
    region = _make_region("andina", "Región Andina")
    admin = _make_user("admin@x.com", RolUsuario.ADMIN, "Admin", region=region)
    r = client.post(
        "/api/v1/admin/staff",
        headers=_headers(admin),
        json={"email": "sop@chambeapp.com", "nombre": "Soporte Andina", "rol": "soporte", "password": "Clave123!"},
    )
    assert r.status_code == 201
    assert r.get_json()["items"][0]["region"]["id"] == region.id


def test_admin_crea_staff_sin_region_400(client):
    admin = _make_user("admin@x.com", RolUsuario.ADMIN, "Admin sin región")
    r = client.post(
        "/api/v1/admin/staff",
        headers=_headers(admin),
        json={"email": "verif@chambeapp.com", "nombre": "V", "rol": "verificador", "password": "Clave123!"},
    )
    assert r.status_code == 400


def test_admin_staff_lista_solo_su_region(client):
    rA = _make_region("caribe", "Región Caribe")
    rB = _make_region("andina", "Región Andina")
    admin = _make_user("admin@x.com", RolUsuario.ADMIN, "Admin", region=rA)
    _make_user("vA@x.com", RolUsuario.VERIFICADOR, "V A", region=rA)
    _make_user("vB@x.com", RolUsuario.VERIFICADOR, "V B", region=rB)

    r = client.get("/api/v1/admin/staff", headers=_headers(admin))
    assert r.status_code == 200
    emails = {item["email"] for item in r.get_json()["items"]}
    assert "vA@x.com" in emails
    assert "vB@x.com" not in emails


def test_admin_no_puede_crear_otro_admin(client):
    region = _make_region("caribe", "Región Caribe")
    admin = _make_user("admin@x.com", RolUsuario.ADMIN, "Admin", region=region)
    r = client.post(
        "/api/v1/admin/staff",
        headers=_headers(admin),
        json={"email": "otro@chambeapp.com", "nombre": "Otro", "rol": "admin", "password": "Clave123!"},
    )
    assert r.status_code == 422  # rol no permitido por StaffCreateSchema


# ---------------- admin regional: moderación acotada ----------------

def test_admin_regional_no_modera_otra_region(client):
    rA = _make_region("caribe", "Región Caribe")
    rB = _make_region("andina", "Región Andina")
    admin = _make_user("admin@x.com", RolUsuario.ADMIN, "Admin", region=rA)
    other = _make_user("b@x.com", RolUsuario.PDS, "B", region=rB)
    v = Verification(user_id=other.id, status="pending")
    db.session.add(v)
    db.session.commit()

    r = client.post(
        f"/api/v1/admin/verifications/{v.id}/approve", headers=_headers(admin)
    )
    assert r.status_code == 404
    db.session.refresh(v)
    assert v.status == "pending"  # no se tocó


def test_admin_regional_si_modera_su_region(client):
    region = _make_region("caribe", "Región Caribe")
    admin = _make_user("admin@x.com", RolUsuario.ADMIN, "Admin", region=region)
    user = _make_user("a@x.com", RolUsuario.PDS, "A", region=region)
    v = Verification(user_id=user.id, status="pending")
    db.session.add(v)
    db.session.commit()
    r = client.post(
        f"/api/v1/admin/verifications/{v.id}/approve", headers=_headers(admin)
    )
    assert r.status_code == 200
    assert r.get_json()["status"] == "approved"


# ---------------- verificador regional: cola KYC ----------------

def test_verificador_solo_ve_kyc_de_su_region(client):
    rA = _make_region("caribe", "Región Caribe")
    rB = _make_region("andina", "Región Andina")
    verificador = _make_user("verif@x.com", RolUsuario.VERIFICADOR, "V", region=rA)
    user_a = _make_user("a@x.com", RolUsuario.PDS, "A", region=rA)
    user_b = _make_user("b@x.com", RolUsuario.PDS, "B", region=rB)
    _make_doc_requerido()
    doc_a = _make_doc(user_a)
    doc_b = _make_doc(user_b)

    r = client.get("/api/v1/kyc/pendientes", headers=_headers(verificador))
    assert r.status_code == 200
    ids = [item["id"] for item in r.get_json()]
    assert doc_a.id in ids
    assert doc_b.id not in ids


def test_verificador_no_verifica_doc_de_otra_region(client):
    rA = _make_region("caribe", "Región Caribe")
    rB = _make_region("andina", "Región Andina")
    verificador = _make_user("verif@x.com", RolUsuario.VERIFICADOR, "V", region=rA)
    user_b = _make_user("b@x.com", RolUsuario.PDS, "B", region=rB)
    _make_doc_requerido()
    doc_b = _make_doc(user_b)

    r = client.post(
        f"/api/v1/kyc/documentos/{doc_b.id}/verificar",
        headers=_headers(verificador),
        json={"decision": "aprobado"},
    )
    assert r.status_code == 404


# ---------------- soporte regional: tickets ----------------

def test_soporte_solo_gestiona_tickets_de_su_region(client):
    rA = _make_region("caribe", "Región Caribe")
    rB = _make_region("andina", "Región Andina")
    soporte = _make_user("sop@x.com", RolUsuario.SOPORTE, "S", region=rA)
    user_a = _make_user("a@x.com", RolUsuario.PDS, "A", region=rA)
    user_b = _make_user("b@x.com", RolUsuario.PDS, "B", region=rB)
    ticket_a = Ticket(user_id=user_a.id, subject="Tick A", body="x")
    ticket_b = Ticket(user_id=user_b.id, subject="Tick B", body="x")
    db.session.add_all([ticket_a, ticket_b])
    db.session.commit()

    r = client.get("/api/v1/admin/tickets", headers=_headers(soporte))
    assert r.status_code == 200
    ids = [item["id"] for item in r.get_json()["items"]]
    assert ticket_a.id in ids
    assert ticket_b.id not in ids

    r2 = client.patch(
        f"/api/v1/admin/tickets/{ticket_b.id}",
        headers=_headers(soporte),
        json={"status": "closed"},
    )
    assert r2.status_code == 404

    r3 = client.patch(
        f"/api/v1/admin/tickets/{ticket_a.id}",
        headers=_headers(soporte),
        json={"status": "closed"},
    )
    assert r3.status_code == 200
    assert r3.get_json()["status"] == "closed"


def _make_doc_requerido():
    dr = DocumentoRequerido(rol="pds", clave="cedula", nombre="Cédula", obligatorio=True)
    db.session.add(dr)
    db.session.commit()
    return dr


def _make_doc(user):
    du = DocumentoUsuario(
        user_id=user.id,
        documento_requerido_id=DocumentoRequerido.query.filter_by(clave="cedula").first().id,
        documento_clave="cedula",
        rol="pds",
        estado="enviado",
        nombre_archivo="doc.png",
        tipo_mime="image/png",
    )
    db.session.add(du)
    db.session.commit()
    return du


# ---------------- región derivada de la ubicación ----------------

def test_region_derivada_de_zona_en_perfil(client):
    region = _make_region("caribe", "Región Caribe", ["Cesar", "Atlántico", "Córdoba", "Magdalena"])
    user = _make_user("u@x.com", RolUsuario.PDS, "U")
    db.session.add(Profile(user=user, zona="Valledupar, Cesar"))
    db.session.commit()

    r = client.put(
        "/api/v1/users/me/profile",
        headers=_headers(user),
        json={"zona": "Barranquilla, Atlántico"},
    )
    assert r.status_code == 200
    db.session.refresh(user)
    assert user.region_id == region.id


def test_region_derivada_de_ubicacion_en_solicitud(client):
    region = _make_region("caribe", "Región Caribe", ["Cesar", "Atlántico", "Córdoba", "Magdalena"])
    user = _make_user("u@x.com", RolUsuario.SOLICITANTE, "U")
    db.session.add(Profile(user=user))
    db.session.commit()

    r = client.post(
        "/api/v1/solicitudes/",
        headers=_headers(user),
        json={
            "titulo": "Arreglar grifo",
            "categoria": "plomería",
            "descripcion": "Demo",
            "ubicacion": "Montería, Córdoba",
            "presupuesto": 100000,
        },
    )
    assert r.status_code == 201
    db.session.refresh(user)
    assert user.region_id == region.id


def test_region_derivada_en_onboarding(client):
    region = _make_region("caribe", "Región Caribe", ["La Guajira", "Magdalena", "Córdoba"])
    user = _make_user("u@x.com", RolUsuario.PDS, "U")
    db.session.add(Profile(user=user))
    db.session.commit()

    r = client.patch(
        "/api/v1/onboarding/step",
        headers=_headers(user),
        json={"step": 2, "data": {"zona": "Riohacha, La Guajira"}},
    )
    assert r.status_code == 200
    db.session.refresh(user)
    assert user.region_id == region.id


def test_region_detect_endpoint(client):
    _make_region("caribe", "Región Caribe", ["Magdalena", "Cesar", "Córdoba"])
    _make_region("andina", "Región Andina", ["Cundinamarca", "Antioquia"])
    user = _make_user("u@x.com", RolUsuario.PDS, "U")

    r = client.get("/api/v1/regions/detectar?ubicacion=Santa Marta, Magdalena", headers=_headers(user))
    assert r.status_code == 200
    assert r.get_json()["region"]["clave"] == "caribe"

    r2 = client.get("/api/v1/regions/detectar?ubicacion=Bogotá, Cundinamarca", headers=_headers(user))
    assert r2.get_json()["region"]["clave"] == "andina"

    r3 = client.get("/api/v1/regions/detectar?ubicacion=Lugar Desconocido", headers=_headers(user))
    assert r3.get_json()["region"] is None


# ---------------- reindexación por superadmin ----------------

def test_superadmin_reindex_region(client):
    sa = _make_user("sa@x.com", RolUsuario.SUPERADMIN, "SA")
    _make_region("caribe", "Región Caribe", ["Cesar", "Magdalena"])
    _make_region("pacifica", "Región Pacífica", ["Valle del Cauca", "Chocó"])
    # 1) sin región, con zona
    u1 = _make_user("u1@x.com", RolUsuario.PDS, "U1")
    db.session.add(Profile(user=u1, zona="Cali, Valle del Cauca"))
    # 2) sin zona ni región, pero con solicitud en Valledupar
    u2 = _make_user("u2@x.com", RolUsuario.SOLICITANTE, "U2")
    db.session.add(Profile(user=u2))
    db.session.commit()
    svc = Solicitud(
        solicitante_id=u2.id, titulo="T", categoria="x",
        descripcion="d", ubicacion="Valledupar, Cesar",
        estado=EstadoSolicitud.PUBLICADO,
    )
    db.session.add(svc)
    db.session.commit()

    r = client.post("/api/v1/superadmin/regions/reindex", headers=_headers(sa))
    assert r.status_code == 200
    data = r.get_json()
    assert data["updated"] >= 2
    db.session.refresh(u1)
    db.session.refresh(u2)
    assert u1.region.nombre == "Región Pacífica"
    assert u2.region.nombre == "Región Caribe"


def test_reindex_no_toca_personal_interno(client):
    sa = _make_user("sa@x.com", RolUsuario.SUPERADMIN, "SA")
    region = _make_region("caribe", "Región Caribe", ["Cesar"])
    _make_region("pacifica", "Región Pacífica", ["Valle del Cauca"])
    verificador = _make_user("v@x.com", RolUsuario.VERIFICADOR, "V", region=region)
    db.session.add(Profile(user=verificador, zona="Cali, Valle del Cauca"))
    db.session.commit()

    r = client.post("/api/v1/superadmin/regions/reindex", headers=_headers(sa))
    assert r.status_code == 200
    db.session.refresh(verificador)
    assert verificador.region_id == region.id  # sin cambios


# ---------------- control de doble conteo (propiedad solicitante) ----------------

def _make_contract(solicitante, proveedor, monto):
    svc = Solicitud(
        solicitante_id=solicitante.id, titulo="T", categoria="x",
        descripcion="d", ubicacion="Valledupar, Cesar",
        estado=EstadoSolicitud.PUBLICADO,
    )
    db.session.add(svc)
    db.session.commit()
    contract = Contract(
        service_id=svc.id, proveedor_id=proveedor.id,
        solicitante_id=solicitante.id, estado=EstadoContrato.EN_PROGRESO,
    )
    db.session.add(contract)
    db.session.commit()
    pay = Payment(contract_id=contract.id, monto=monto, estado=EstadoPago.COMPLETADO)
    db.session.add(pay)
    db.session.commit()
    return contract


def test_contrato_cruzado_solo_lo_ve_region_del_solicitante(client):
    rA = _make_region("caribe", "Región Caribe")
    rB = _make_region("andina", "Región Andina")
    solicitante = _make_user("sol@x.com", RolUsuario.SOLICITANTE, "Sol", region=rA)
    proveedor = _make_user("prov@x.com", RolUsuario.PDS, "Prov", region=rB)
    adminA = _make_user("adminA@x.com", RolUsuario.ADMIN, "Admin A", region=rA)
    adminB = _make_user("adminB@x.com", RolUsuario.ADMIN, "Admin B", region=rB)
    contract = _make_contract(solicitante, proveedor, monto=200000)

    # Admin región A (solicitante) lo ve
    rA_contracts = client.get("/api/v1/admin/contracts", headers=_headers(adminA)).get_json()
    assert contract.id in {c["id"] for c in rA_contracts["items"]}

    # Admin región B (solo proveedor) NO lo ve
    rB_contracts = client.get("/api/v1/admin/contracts", headers=_headers(adminB)).get_json()
    assert contract.id not in {c["id"] for c in rB_contracts["items"]}


def test_stats_cruzado_sin_doble_conteo(client):
    rA = _make_region("caribe", "Región Caribe")
    rB = _make_region("andina", "Región Andina")
    solicitante = _make_user("sol@x.com", RolUsuario.SOLICITANTE, "Sol", region=rA)
    proveedor = _make_user("prov@x.com", RolUsuario.PDS, "Prov", region=rB)
    adminA = _make_user("adminA@x.com", RolUsuario.ADMIN, "Admin A", region=rA)
    adminB = _make_user("adminB@x.com", RolUsuario.ADMIN, "Admin B", region=rB)
    _make_contract(solicitante, proveedor, monto=200000)

    statsA = client.get("/api/v1/admin/stats/overview", headers=_headers(adminA)).get_json()
    statsB = client.get("/api/v1/admin/stats/overview", headers=_headers(adminB)).get_json()

    # El contrato y el ingreso cuentan SOLO en la región del solicitante (A)
    assert statsA["contracts_total"] >= 1
    assert statsA["revenue_total"] >= 200000
    assert statsB["contracts_total"] == 0
    assert statsB["revenue_total"] == 0


def test_disputa_cruzada_pertenece_a_region_del_solicitante(client):
    rA = _make_region("caribe", "Región Caribe")
    rB = _make_region("andina", "Región Andina")
    solicitante = _make_user("sol@x.com", RolUsuario.SOLICITANTE, "Sol", region=rA)
    proveedor = _make_user("prov@x.com", RolUsuario.PDS, "Prov", region=rB)
    adminA = _make_user("adminA@x.com", RolUsuario.ADMIN, "Admin A", region=rA)
    adminB = _make_user("adminB@x.com", RolUsuario.ADMIN, "Admin B", region=rB)
    contract = _make_contract(solicitante, proveedor, monto=200000)
    dispute = Dispute(contract_id=contract.id, reason="Incumplimiento", status="abierta")
    db.session.add(dispute)
    db.session.commit()

    idsA = {d["id"] for d in client.get("/api/v1/admin/disputes", headers=_headers(adminA)).get_json()["items"]}
    idsB = {d["id"] for d in client.get("/api/v1/admin/disputes", headers=_headers(adminB)).get_json()["items"]}
    assert dispute.id in idsA
    assert dispute.id not in idsB

    # El admin B no puede resolver la disputa de otra región
    r = client.post(
        f"/api/v1/admin/disputes/{dispute.id}/resolve",
        headers=_headers(adminB),
        json={"resolution": "sin validez"},
    )
    assert r.status_code == 404