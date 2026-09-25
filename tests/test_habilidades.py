"""Tests: habilidades con rutas de niveles certificables (quiz + certificación)."""

import pytest
from app import create_app
from app.extensions import db as _db
from app.models.user import User, RolUsuario
from app.models.habilidad import Habilidad
from flask_jwt_extended import create_access_token


@pytest.fixture(scope="module")
def app():
    app = create_app("app.config.TestingConfig")
    with app.app_context():
        _db.create_all()
        yield app
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def _user(client, email="hab@test.com", rol=RolUsuario.PDS):
    with client.application.app_context():
        u = User(email=email, nombre="Hab User", rol=rol, acepto_tyc=True)
        u.set_password("Test1234!")
        _db.session.add(u)
        _db.session.commit()
        return u.id, {"Authorization": f"Bearer {create_access_token(identity=str(u.id))}"}


def _seed_hab():
    with _db.session() as s:
        if not Habilidad.query.first():
            s.add(Habilidad(
                nombre="Plomería",
                descripcion="test",
                habilidades=["Termofusión de tuberías", "Detección de fugas"],
                niveles=[
                    {"nombre": "Básico", "tipo": "quiz", "quiz": [
                        {"pregunta": "P1", "opciones": ["A", "B"], "correcta": 0},
                        {"pregunta": "P2", "opciones": ["A", "B"], "correcta": 1},
                    ]},
                    {"nombre": "Avanzado", "tipo": "certificacion"},
                ],
            ))
            s.commit()


def test_listar_catalogo_oculta_quiz(client):
    """GET /habilidades lista niveles SIN exponer respuestas del quiz."""
    _seed_hab()
    _, h = _user(client)
    r = client.get("/api/v1/habilidades", headers=h)
    assert r.status_code == 200
    plomeria = next(x for x in r.get_json() if x["nombre"] == "Plomería")
    assert plomeria["niveles"][0]["tipo"] == "quiz"
    assert "quiz" not in plomeria["niveles"][0]


def test_crear_habilidad(client):
    """POST /habilidades crea una ruta con niveles."""
    _, h = _user(client, "hab2@test.com")
    r = client.post("/api/v1/habilidades", headers=h, json={
        "nombre": "Albañilería",
        "descripcion": "Obra gris y acabados.",
        "niveles": [
            {"nombre": "Básico", "tipo": "quiz", "quiz": [
                {"pregunta": "Q", "opciones": ["a", "b"], "correcta": 0},
            ]},
            {"nombre": "Maestro", "tipo": "certificacion"},
        ],
    })
    assert r.status_code == 201
    data = r.get_json()
    assert data["nombre"] == "Albañilería"
    assert len(data["niveles"]) == 2


def test_crear_duplicado_409(client):
    _, h = _user(client, "hab3@test.com")
    r = client.post("/api/v1/habilidades", headers=h, json={"nombre": "Plomería"})
    assert r.status_code == 409


def test_quiz_aprobado_registra_nivel(client):
    """Quiz con >=70% aprueba y registra el nivel como completado."""
    _seed_hab()
    uid, h = _user(client, "hab4@test.com")
    hab = Habilidad.query.filter_by(nombre="Plomería").first()

    r = client.post(
        f"/api/v1/habilidades/{hab.id}/nivel/0/quiz",
        headers=h,
        json={"respuestas": [0, 1]},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["aprobado"] is True
    assert data["aciertos"] == 2

    mine = client.get("/api/v1/habilidades/mis-niveles", headers=h).get_json()
    assert len(mine) == 1
    assert mine[0]["habilidad_id"] == hab.id
    assert mine[0]["nivel_index"] == 0
    assert mine[0]["metodo"] == "quiz"


def test_quiz_no_aprobado_no_registra(client):
    """Quiz con menos del 70% NO aprueba y NO registra el nivel."""
    _seed_hab()
    uid, h = _user(client, "hab5@test.com")
    hab = Habilidad.query.filter_by(nombre="Plomería").first()

    r = client.post(
        f"/api/v1/habilidades/{hab.id}/nivel/0/quiz",
        headers=h,
        json={"respuestas": [1, 0]},
    )
    assert r.status_code == 200
    assert r.get_json()["aprobado"] is False

    mine = client.get("/api/v1/habilidades/mis-niveles", headers=h).get_json()
    assert len(mine) == 0


def test_quiz_faltan_respuestas_400(client):
    _seed_hab()
    _, h = _user(client, "hab6@test.com")
    hab = Habilidad.query.filter_by(nombre="Plomería").first()
    r = client.post(f"/api/v1/habilidades/{hab.id}/nivel/0/quiz", headers=h, json={"respuestas": [0]})
    assert r.status_code == 400


def test_certificacion_con_url(client):
    """Nivel tipo certificación se aprueba con una URL de certificado."""
    _seed_hab()
    uid, h = _user(client, "hab7@test.com")
    hab = Habilidad.query.filter_by(nombre="Plomería").first()

    r = client.post(
        f"/api/v1/habilidades/{hab.id}/nivel/1/certificacion",
        headers=h,
        json={"url": "http://storage/certificado.pdf"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["metodo"] == "certificacion"
    assert data["evidencia_url"] == "http://storage/certificado.pdf"


def test_certificacion_en_nivel_quiz_400(client):
    """Un nivel tipo quiz no acepta certificación por documento."""
    _seed_hab()
    _, h = _user(client, "hab8@test.com")
    hab = Habilidad.query.filter_by(nombre="Plomería").first()
    r = client.post(
        f"/api/v1/habilidades/{hab.id}/nivel/0/certificacion",
        headers=h,
        json={"url": "http://x/y.pdf"},
    )
    assert r.status_code == 400


def test_requiere_jwt(client):
    assert client.get("/api/v1/habilidades").status_code == 401


def _seed_contrato_completado(client, pds_id, solicitante_id):
    """Crea una solicitud + contrato completado para el progreso/endoso."""
    from app.models.contract import Contract
    from app.models.solicitud import Solicitud, EstadoSolicitud
    with client.application.app_context():
        sol = Solicitud(
            solicitante_id=solicitante_id,
            titulo="Chamba plomería",
            descripcion="x",
            categoria="plomeria",
            presupuesto=100000,
            estado=EstadoSolicitud.EN_PROGRESO,
        )
        _db.session.add(sol)
        _db.session.flush()
        contrato = Contract(
            service_id=sol.id,
            proveedor_id=pds_id,
            solicitante_id=solicitante_id,
            estado="completado",
        )
        _db.session.add(contrato)
        _db.session.commit()
        return contrato.id


def test_endoso_por_cliente(client):
    """Solo el solicitante de un contrato completado puede endosar."""
    _seed_hab()
    pds_id, _ = _user(client, "endoso_pds@test.com", RolUsuario.PDS)
    sol_id, h_sol = _user(client, "endoso_sol@test.com", RolUsuario.SOLICITANTE)
    contrato_id = _seed_contrato_completado(client, pds_id, sol_id)
    hab = Habilidad.query.filter_by(nombre="Plomería").first()

    # El PDS no puede endosar
    r = client.post(
        "/api/v1/habilidades/endosar",
        headers=_user(client, "endoso_otro@test.com")[1],
        json={"contract_id": contrato_id, "habilidad_id": hab.id, "competencia": "Detección de fugas"},
    )
    assert r.status_code == 403

    # El solicitante endosa una competencia del oficio
    r2 = client.post(
        "/api/v1/habilidades/endosar",
        headers=h_sol,
        json={"contract_id": contrato_id, "habilidad_id": hab.id, "competencia": "Detección de fugas"},
    )
    assert r2.status_code == 200
    assert r2.get_json()["competencia"] == "Detección de fugas"

    # Duplicado → 409
    r3 = client.post(
        "/api/v1/habilidades/endosar",
        headers=h_sol,
        json={"contract_id": contrato_id, "habilidad_id": hab.id, "competencia": "Detección de fugas"},
    )
    assert r3.status_code == 409

    # Competencia ajena al oficio → 400
    r4 = client.post(
        "/api/v1/habilidades/endosar",
        headers=h_sol,
        json={"contract_id": contrato_id, "habilidad_id": hab.id, "competencia": "Pintar paredes"},
    )
    assert r4.status_code == 400


def test_certificacion_tecnica_verificada(client):
    """Con código de verificación la certificación queda 'verificada'."""
    _seed_hab()
    uid, h = _user(client, "cert@test.com")
    hab = Habilidad.query.filter_by(nombre="Plomería").first()

    r = client.post(
        "/api/v1/habilidades/certificaciones",
        headers=h,
        json={
            "institucion": "SENA",
            "titulo": "Técnico en Instalaciones Eléctricas Domiciliarias",
            "anio": 2024,
            "habilidad_id": hab.id,
            "codigo_verificacion": "SENA-2024-123",
            "url": "http://storage/titulo.pdf",
        },
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["estado"] == "verificado"
    assert data["institucion"] == "SENA"

    lista = client.get("/api/v1/habilidades/certificaciones", headers=h).get_json()
    assert len(lista) == 1


def test_certificacion_sin_codigo_queda_en_revision(client):
    _seed_hab()
    _, h = _user(client, "cert2@test.com")
    r = client.post(
        "/api/v1/habilidades/certificaciones",
        headers=h,
        json={"institucion": "SENA", "titulo": "Curso de plomería"},
    )
    assert r.status_code == 201
    assert r.get_json()["estado"] == "en_revision"


def test_progreso_oficio_nivel_1(client):
    """Sin quizzes/trabajos, el oficio queda en Nivel 1 Novato."""
    _seed_hab()
    uid, h = _user(client, "prog@test.com")
    from app.models.user import Profile
    with client.application.app_context():
        u = _db.session.get(User, uid)
        if not u.profile:
            u.profile = Profile(user_id=uid)
        u.profile.habilidades = ["Plomería"]
        _db.session.commit()

    r = client.get("/api/v1/habilidades/progreso", headers=h)
    assert r.status_code == 200
    data = r.get_json()
    assert len(data) == 1
    assert data[0]["oficio"] == "Plomería"
    assert data[0]["nivel"] == 1
    assert data[0]["nombre_nivel"] == "Novato"
    assert "Termofusión de tuberías" in data[0]["habilidades"]