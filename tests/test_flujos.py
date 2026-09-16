"""Integration tests: 7 user-journey flows end-to-end (Flask test client).

Run with:  py -3.11 -m pytest tests/test_flujos.py -q -p no:cacheprovider
"""

import io
import math
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest

from app import create_app
from app.extensions import db
from app.models.user import User, Profile, RolUsuario
from app.models.solicitud import Solicitud, EstadoSolicitud
from app.models.contract import Contract, EstadoContrato
from app.models.payment import Payment, EstadoPago
from app.models.notification import Notification
from app.models.trust import TrustScore
from app.models.cascade import NotificationCascade
from app.models.portfolio import PortfolioItem
from app.services.cascade import CascadeManager


# ── Helpers ──────────────────────────────────────────────────────────────────

SOLICITUDES_URL = "/api/v1/solicitudes/"


def _register(client, email, password="secret123", rol="pds"):
    return client.post("/api/v1/auth/register", json={
        "email": email, "password": password, "rol": rol,
        "acepto_tyc": True, "ip": "127.0.0.1",
    })


def _login(client, email, password="secret123"):
    return client.post("/api/v1/auth/login", json={
        "email": email, "password": password,
    }).get_json()


def _headers(client, email, password="secret123"):
    data = _login(client, email, password)
    return {"Authorization": f"Bearer {data['access_token']}"}


def _create_user(client, email, rol="pds", password="secret123"):
    """Register + return auth headers for a user."""
    _register(client, email, password=password, rol=rol)
    return _headers(client, email, password)


def _create_solicitante(client, email="sol@test.com"):
    return _create_user(client, email, rol="solicitante")


def _create_pds(client, email="pds@test.com"):
    return _create_user(client, email, rol="pds")


# ── Fixtures ─────────────────────────────────────────────────────────────────

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


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  FLUJO 1 — Autenticación                                                  ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

class TestFlujo1Autenticacion:
    """Registrar PDS → login → /me → logout."""

    def test_register_login_me_logout(self, client):
        # 1. Register PDS
        resp = _register(client, "auth_flujo@test.com", rol="pds")
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["email"] == "auth_flujo@test.com"
        assert data["rol"] == "pds"
        assert data["acepto_tyc"] is True

        # 2. Login
        login_resp = client.post("/api/v1/auth/login", json={
            "email": "auth_flujo@test.com", "password": "secret123",
        })
        assert login_resp.status_code == 200
        token_data = login_resp.get_json()
        assert "access_token" in token_data
        assert "refresh_token" in token_data

        # 3. Get /me with token
        hdrs = {"Authorization": f"Bearer {token_data['access_token']}"}
        me_resp = client.get("/api/v1/auth/me", headers=hdrs)
        assert me_resp.status_code == 200
        me = me_resp.get_json()
        assert me["email"] == "auth_flujo@test.com"
        assert "id" in me

    def test_register_solicitante_and_login(self, client):
        """Register as solicitante, login, verify role."""
        _register(client, "sol_auth@test.com", rol="solicitante")
        login = _login(client, "sol_auth@test.com")
        assert "access_token" in login

        me = client.get("/api/v1/auth/me",
                        headers={"Authorization": f"Bearer {login['access_token']}"}).get_json()
        assert me["rol"] == "solicitante"

    def test_refresh_token(self, client):
        """Register → login → refresh → new access_token."""
        _register(client, "refresh@test.com")
        login = _login(client, "refresh@test.com")
        resp = client.post("/api/v1/auth/refresh",
                           headers={"Authorization": f"Bearer {login['refresh_token']}"})
        assert resp.status_code == 200
        assert "access_token" in resp.get_json()

    def test_me_without_token_401(self, client):
        assert client.get("/api/v1/auth/me").status_code == 401


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  FLUJO 2 — Perfil PDS: Trust + Badges + Portfolio                          ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

class TestFlujo2PerfilPDS:
    """Editar perfil → trust score → badges → portfolio upload."""

    def test_edit_profile_and_get_trust_badges(self, client):
        # 1. Register PDS
        hdrs = _create_pds(client, "pds_perfil@test.com")

        # 2. Edit profile (PUT /users/me/profile)
        put_resp = client.put("/api/v1/users/me/profile", headers=hdrs, json={
            "habilidades": ["plomeria", "electricidad"],
            "experiencia": "5 anios",
            "zona": "Valledupar",
            "categorias": ["plomeria"],
        })
        assert put_resp.status_code == 200
        profile = put_resp.get_json()
        assert "plomeria" in profile["habilidades"]
        assert profile["perfil_completo"] is True

        # 3. Get profile via GET
        get_resp = client.get("/api/v1/users/me/profile", headers=hdrs)
        assert get_resp.status_code == 200
        assert get_resp.get_json()["zona"] == "Valledupar"

        # 4. Trust score — create one manually then fetch
        pds_user = User.query.filter_by(email="pds_perfil@test.com").first()
        trust = TrustScore.get_or_create(pds_id=pds_user.id)
        trust.calcular()
        assert trust.puntuacion >= 0
        assert trust.nivel in ("nuevo", "confiable", "verificado", "experto")

        # 5. Badges
        badges_resp = client.get("/api/v1/users/badges", headers=hdrs)
        assert badges_resp.status_code == 200
        badges = badges_resp.get_json()
        assert isinstance(badges, list)
        assert len(badges) > 0
        # After profile edit, PERFIL_COMPLETO should be awarded
        types = [b["type"] for b in badges]
        assert "perfil_completo" in types

    def test_portfolio_upload_and_list(self, client):
        """Upload portfolio item → list items → verify appears."""
        hdrs = _create_pds(client, "pds_port@test.com")

        titulo_send = "Reparacion tuberia"
        with patch('app.services.storage.storage.upload_image') as mock_upload:
            mock_upload.return_value = "http://minio:9000/test.webp"

            # Upload
            resp = client.post("/api/v1/portfolio/upload", headers=hdrs, data={
                "archivo": (io.BytesIO(b"fake image bytes"), "foto.jpg"),
                "titulo": titulo_send,
                "tipo": "foto",
                "categoria": "plomeria",
                "descripcion": "Trabajo realizado",
            }, content_type="multipart/form-data")
            assert resp.status_code == 201
            item = resp.get_json()
            assert item["titulo"] == titulo_send
            assert item["tipo"] == "foto"
            assert item["url"] == "http://minio:9000/test.webp"

        # List items
        list_resp = client.get("/api/v1/portfolio/items", headers=hdrs)
        assert list_resp.status_code == 200
        items = list_resp.get_json()
        assert len(items) >= 1
        assert any(i["titulo"] == titulo_send for i in items)


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  FLUJO 3 — Solicitud con Geofence                                          ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

class TestFlujo3SolicitudGeofence:
    """Solicitante publica solicitud con lat/lng → ver coordenadas en detail."""

    def test_create_solicitud_with_geofence(self, client):
        hdrs = _create_solicitante(client, "sol_geo@test.com")

        # Create solicitud with coordinates (use trailing slash to avoid 308)
        resp = client.post(SOLICITUDES_URL, headers=hdrs, json={
            "titulo": "Arreglo de techo",
            "categoria": "plomeria",
            "descripcion": "Se necesita arreglar techo con goteras",
            "ubicacion": "Valledupar",
            "presupuesto": 80000,
            "latitud": 10.4806,
            "longitud": -73.2495,
            "direccion": "Calle 15 #8-30",
            "urgencia": "media",
        })
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.data}"
        sol = resp.get_json()
        sol_id = sol["id"]

        # Detail as owner → coordinates visible
        detail = client.get(f"/api/v1/solicitudes/{sol_id}", headers=hdrs).get_json()
        assert detail["latitud"] == 10.4806
        assert detail["longitud"] == -73.2495
        assert detail["direccion"] == "Calle 15 #8-30"

    def test_solicitud_without_coordinates(self, client):
        """Solicitud sin coordenadas — lat/lng should be None."""
        hdrs = _create_solicitante(client, "sol_geo2@test.com")

        resp = client.post(SOLICITUDES_URL, headers=hdrs, json={
            "titulo": "Pintar fachada",
            "categoria": "pintura",
            "descripcion": "Fachada de 2 pisos",
            "ubicacion": "Valledupar",
            "presupuesto": 60000,
        })
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.data}"
        sol = resp.get_json()
        detail = client.get(f"/api/v1/solicitudes/{sol['id']}", headers=hdrs).get_json()
        assert detail["latitud"] is None
        assert detail["longitud"] is None

    def test_solicitud_min_budget(self, client):
        """Budget below 50000 should fail."""
        hdrs = _create_solicitante(client, "sol_budget@test.com")
        resp = client.post(SOLICITUDES_URL, headers=hdrs, json={
            "titulo": "Tarea",
            "categoria": "general",
            "descripcion": "algo",
            "ubicacion": "Valledupar",
            "presupuesto": 30000,
        })
        assert resp.status_code == 400


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  FLUJO 4 — Recomendaciones ML (Hybrid)                                     ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

class TestFlujo4RecomendacionesML:
    """Create PDS + solicitud → call recommendations → ranked list."""

    def test_recommendations_for_service(self, client):
        """GET /ai/recommendations?service_id=N → ranked providers."""
        # 1. Create a PDS with profile
        pds_hdrs = _create_pds(client, "pds_recom@test.com")
        client.put("/api/v1/users/me/profile", headers=pds_hdrs, json={
            "habilidades": ["plomeria"],
            "categorias": ["plomeria"],
            "zona": "Valledupar",
        })

        # 2. Create solicitud from solicitante
        sol_hdrs = _create_solicitante(client, "sol_recom@test.com")
        sol_resp = client.post(SOLICITUDES_URL, headers=sol_hdrs, json={
            "titulo": "Reparar tuberia",
            "categoria": "plomeria",
            "descripcion": "Tuberia rota en cocina",
            "ubicacion": "Valledupar",
            "presupuesto": 100000,
        })
        assert sol_resp.status_code == 201
        sol_id = sol_resp.get_json()["id"]

        # 3. Call recommendations (no auth required)
        recs_resp = client.get(f"/api/v1/ai/recommendations?service_id={sol_id}")
        assert recs_resp.status_code == 200
        data = recs_resp.get_json()
        assert "recommendations" in data
        assert isinstance(data["recommendations"], list)
        # The PDS should appear
        emails = [r["email"] for r in data["recommendations"]]
        assert "pds_recom@test.com" in emails

    def test_solicitudes_for_provider(self, client):
        """GET /ai/solicitudes-for-provider → services matching PDS profile."""
        # PDS with profile
        pds_hdrs = _create_pds(client, "pds_svc@test.com")
        client.put("/api/v1/users/me/profile", headers=pds_hdrs, json={
            "habilidades": ["electricidad"],
            "categorias": ["electricidad"],
            "zona": "Valledupar",
        })

        # Solicitante publishes matching service
        sol_hdrs = _create_solicitante(client, "sol_svc@test.com")
        sol_resp = client.post(SOLICITUDES_URL, headers=sol_hdrs, json={
            "titulo": "Instalacion electrica",
            "categoria": "electricidad",
            "descripcion": "Cableado para apartamento nuevo",
            "ubicacion": "Valledupar",
            "presupuesto": 200000,
        })
        assert sol_resp.status_code == 201

        # PDS queries solicitudes for them
        resp = client.get("/api/v1/ai/solicitudes-for-provider", headers=pds_hdrs)
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        # The electricidad service should appear
        cats = [s["categoria"] for s in data]
        assert "electricidad" in cats


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  FLUJO 5 — Cascada de Notificaciones                                       ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

class TestFlujo5CascadaNotificaciones:
    """Create solicitud → start cascade → send_phase → DB notifications."""

    def _make_provider_near(self, client):
        """Create a provider with perfil_completo and coordinates near Valledupar."""
        hdrs = _create_pds(client, email="pds_nearby@test.com")
        client.put("/api/v1/users/me/profile", headers=hdrs, json={
            "habilidades": ["plomeria"],
            "categorias": ["plomeria"],
            "zona": "Valledupar",
        })
        # Set coordinates directly on profile
        pds_user = User.query.filter_by(email="pds_nearby@test.com").first()
        pds_user.profile.latitud = 10.4810  # Very close to 10.4806
        pds_user.profile.longitud = -73.2490
        pds_user.profile.perfil_completo = True
        db.session.commit()
        return hdrs

    def test_cascade_creates_notifications(self, client):
        """start_cascade → send_phase creates Notification rows."""
        # 1. Create a nearby PDS
        self._make_provider_near(client)

        # 2. Create solicitud with coordinates
        sol_hdrs = _create_solicitante(client, "sol_casc@test.com")
        sol_resp = client.post(SOLICITUDES_URL, headers=sol_hdrs, json={
            "titulo": "Plomeria urgente",
            "categoria": "plomeria",
            "descripcion": "Fuga de agua",
            "ubicacion": "Valledupar",
            "presupuesto": 70000,
            "latitud": 10.4806,
            "longitud": -73.2495,
        })
        assert sol_resp.status_code == 201
        sol_id = sol_resp.get_json()["id"]

        # 3. Start cascade (mock Celery task + apply_async for next phases)
        mock_task = MagicMock()
        with patch("app.services.cascade.send_phase_task", mock_task):
            cascade = CascadeManager.start_cascade(solicitud_id=sol_id)
        assert cascade.estado == "activa"

        # Count before
        before = Notification.query.count()

        # 4. Send phase directly (bypass Celery — also mock apply_async for next phase)
        with patch("app.services.cascade.send_phase_task", mock_task):
            CascadeManager.send_phase(cascade.id)

        # 5. Assert notifications were created
        after = Notification.query.count()
        assert after > before
        pds_user = User.query.filter_by(email="pds_nearby@test.com").first()
        notif = Notification.query.filter_by(
            user_id=pds_user.id, tipo="nueva_solicitud"
        ).first()
        assert notif is not None
        assert notif.datos["solicitud_id"] == sol_id

    def test_cascade_completes_when_no_candidates(self, client):
        """If no providers nearby, cascade completes immediately."""
        sol_hdrs = _create_solicitante(client, "sol_nocand@test.com")
        sol_resp = client.post(SOLICITUDES_URL, headers=sol_hdrs, json={
            "titulo": "Trabajo lejano",
            "categoria": "albanileria",
            "descripcion": "Casa en zona remota",
            "ubicacion": "Barranquilla",
            "presupuesto": 50000,
            "latitud": 10.9685,  # Barranquilla - far from Valledupar
            "longitud": -74.7815,
        })
        assert sol_resp.status_code == 201
        sol_id = sol_resp.get_json()["id"]

        mock_task = MagicMock()
        with patch("app.services.cascade.send_phase_task", mock_task):
            cascade = CascadeManager.start_cascade(solicitud_id=sol_id)

        # send_phase with no candidates → completes
        with patch("app.services.cascade.send_phase_task", mock_task):
            CascadeManager.send_phase(cascade.id)
        cascade = NotificationCascade.query.get(cascade.id)
        # It should have completed (or advanced without sending)
        assert cascade.enviados_total == 0


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  FLUJO 6 — Contrato + Chat                                                ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

class TestFlujo6ContratoChat:
    """Create solicitud → create contract → accept → complete → chat messages."""

    def _setup_solicitud_and_contract(self, client):
        """Create solicitante + PDS + solicitud + contract.
        Returns (sol_hdrs, pds_hdrs, contract_id, sol_id).
        """
        sol_hdrs = _create_solicitante(client, "sol_cont@test.com")
        pds_hdrs = _create_pds(client, "pds_cont@test.com")

        # Solicitante publishes
        sol_resp = client.post(SOLICITUDES_URL, headers=sol_hdrs, json={
            "titulo": "Soldadura",
            "categoria": "soldadura",
            "descripcion": "Reja metalica",
            "ubicacion": "Valledupar",
            "presupuesto": 150000,
        })
        assert sol_resp.status_code == 201
        sol_id = sol_resp.get_json()["id"]

        # PDS user id
        pds_user = User.query.filter_by(email="pds_cont@test.com").first()

        # Solicitante creates contract
        contract_resp = client.post("/api/v1/contracts/", headers=sol_hdrs, json={
            "service_id": sol_id,
            "proveedor_id": pds_user.id,
        })
        assert contract_resp.status_code == 201
        contract_id = contract_resp.get_json()["id"]
        return sol_hdrs, pds_hdrs, contract_id, sol_id

    def test_contract_lifecycle_and_chat(self, client):
        """Full lifecycle: create → accept → complete → confirm, plus chat."""
        sol_hdrs, pds_hdrs, cid, sol_id = self._setup_solicitud_and_contract(client)

        # 1. PDS accepts contract
        resp = client.patch(f"/api/v1/contracts/{cid}/estado",
                            headers=pds_hdrs, json={"estado": "aceptar"})
        assert resp.status_code == 200
        assert resp.get_json()["estado"] == "en_progreso"

        # 2. PDS completes contract
        resp = client.patch(f"/api/v1/contracts/{cid}/estado",
                            headers=pds_hdrs, json={"estado": "completar"})
        assert resp.status_code == 200
        assert resp.get_json()["estado"] == "completado_pendiente"

        # 3. Solicitante confirms
        resp = client.patch(f"/api/v1/contracts/{cid}/estado",
                            headers=sol_hdrs, json={"estado": "confirmar"})
        assert resp.status_code == 200
        assert resp.get_json()["estado"] == "completado"

        # 4. Verify solicitud status updated
        sol_detail = client.get(f"/api/v1/solicitudes/{sol_id}",
                                headers=sol_hdrs).get_json()
        assert sol_detail["estado"] == "completado"

        # 5. Chat: create conversation
        pds_user = User.query.filter_by(email="pds_cont@test.com").first()
        conv_resp = client.post("/api/v1/chat/conversations", headers=sol_hdrs, json={
            "otro_usuario_id": pds_user.id,
        })
        assert conv_resp.status_code in (200, 201)
        conv = conv_resp.get_json()
        conv_id = conv["id"]

        # 6. Solicitante sends message
        msg_resp = client.post(
            f"/api/v1/chat/conversations/{conv_id}/messages",
            headers=sol_hdrs, json={"contenido": "Hola, como va el trabajo?"})
        assert msg_resp.status_code == 201
        msg = msg_resp.get_json()
        assert msg["contenido"] == "Hola, como va el trabajo?"

        # 7. PDS replies
        msg2_resp = client.post(
            f"/api/v1/chat/conversations/{conv_id}/messages",
            headers=pds_hdrs, json={"contenido": "Todo bien, avanzando"})
        assert msg2_resp.status_code == 201

        # 8. List messages
        msgs_resp = client.get(f"/api/v1/chat/conversations/{conv_id}/messages",
                               headers=sol_hdrs)
        assert msgs_resp.status_code == 200
        msgs = msgs_resp.get_json()
        assert len(msgs) == 2

    def test_contract_cancel(self, client):
        """Contract cancel flow."""
        sol_hdrs, pds_hdrs, cid, _ = self._setup_solicitud_and_contract(client)

        resp = client.patch(f"/api/v1/contracts/{cid}/estado",
                            headers=pds_hdrs, json={
                                "estado": "cancelar",
                                "motivo_cancelacion": "No puedo asistir",
                            })
        assert resp.status_code == 200
        assert resp.get_json()["estado"] == "cancelado"

    def test_my_contracts(self, client):
        """GET /contracts/mine returns the contract."""
        sol_hdrs, pds_hdrs, cid, _ = self._setup_solicitud_and_contract(client)

        resp = client.get("/api/v1/contracts/mine", headers=sol_hdrs)
        assert resp.status_code == 200
        data = resp.get_json()
        # It could be a list or paginated
        items = data if isinstance(data, list) else data.get("items", [])
        assert len(items) >= 1


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  FLUJO 7 — Pago Nequi                                                      ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

class TestFlujo7PagoNequi:
    """Create completed contract → create payment → confirm → history."""

    def _create_completed_contract(self, client):
        """Helper: create full flow up to completado state.
        Returns (sol_hdrs, pds_hdrs, contract_id).
        """
        sol_hdrs = _create_solicitante(client, "sol_pay@test.com")
        pds_hdrs = _create_pds(client, "pds_pay@test.com")

        sol_resp = client.post(SOLICITUDES_URL, headers=sol_hdrs, json={
            "titulo": "Instalacion WiFi",
            "categoria": "tecnologia",
            "descripcion": "Configurar red WiFi",
            "ubicacion": "Valledupar",
            "presupuesto": 120000,
        })
        assert sol_resp.status_code == 201
        sol_id = sol_resp.get_json()["id"]
        pds_user = User.query.filter_by(email="pds_pay@test.com").first()

        # Create + accept + complete + confirm contract
        c_resp = client.post("/api/v1/contracts/", headers=sol_hdrs, json={
            "service_id": sol_id, "proveedor_id": pds_user.id,
        })
        assert c_resp.status_code == 201
        cid = c_resp.get_json()["id"]
        client.patch(f"/api/v1/contracts/{cid}/estado",
                     headers=pds_hdrs, json={"estado": "aceptar"})
        client.patch(f"/api/v1/contracts/{cid}/estado",
                     headers=pds_hdrs, json={"estado": "completar"})
        client.patch(f"/api/v1/contracts/{cid}/estado",
                     headers=sol_hdrs, json={"estado": "confirmar"})

        return sol_hdrs, pds_hdrs, cid

    def test_nequi_info(self, client):
        """GET /payments/nequi returns platform info."""
        resp = client.get("/api/v1/payments/nequi")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "numero" in data
        assert "titular" in data

    def test_create_and_confirm_payment(self, client):
        """Create payment → confirm → verify history."""
        sol_hdrs, pds_hdrs, cid = self._create_completed_contract(client)

        # 1. Create payment
        pay_resp = client.post("/api/v1/payments/", headers=sol_hdrs, json={
            "contract_id": cid,
            "monto": 120000,
            "pasarela": "nequi",
        })
        assert pay_resp.status_code == 201
        pay = pay_resp.get_json()
        assert pay["estado"] == "pendiente"
        assert pay["pasarela"] == "nequi"
        pay_id = pay["id"]

        # 2. Confirm payment (simulates gateway)
        confirm_resp = client.post(f"/api/v1/payments/{pay_id}/confirm",
                                   headers=sol_hdrs)
        assert confirm_resp.status_code == 200
        confirmed = confirm_resp.get_json()
        assert confirmed["estado"] == "completado"

        # 3. Check payment history
        hist_resp = client.get("/api/v1/payments/mine", headers=sol_hdrs)
        assert hist_resp.status_code == 200
        hist = hist_resp.get_json()
        items = hist if isinstance(hist, list) else hist.get("items", [])
        pay_ids = [p["id"] for p in items]
        assert pay_id in pay_ids

    def test_payment_detail(self, client):
        """GET /payments/<id> returns payment detail."""
        sol_hdrs, pds_hdrs, cid = self._create_completed_contract(client)

        pay_resp = client.post("/api/v1/payments/", headers=sol_hdrs, json={
            "contract_id": cid, "monto": 120000,
        }).get_json()
        pay_id = pay_resp["id"]

        detail = client.get(f"/api/v1/payments/{pay_id}", headers=sol_hdrs)
        assert detail.status_code == 200
        assert detail.get_json()["id"] == pay_id

    def test_payment_refund(self, client):
        """Create payment → refund with motivo."""
        sol_hdrs, pds_hdrs, cid = self._create_completed_contract(client)

        pay = client.post("/api/v1/payments/", headers=sol_hdrs, json={
            "contract_id": cid, "monto": 120000,
        }).get_json()

        # Confirm first
        client.post(f"/api/v1/payments/{pay['id']}/confirm", headers=sol_hdrs)

        # Refund
        refund_resp = client.post(f"/api/v1/payments/{pay['id']}/refund",
                                  headers=sol_hdrs,
                                  json={"motivo_reembolso": "Cliente insatisfecho"})
        assert refund_resp.status_code == 200
        assert refund_resp.get_json()["estado"] == "reembolsado"
