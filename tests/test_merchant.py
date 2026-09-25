"""pytest suite — Merchant module: payment methods, preferences, stats, trust, legal.

Tests de integración para los nuevos endpoints del módulo Comerciante.

Run: py -m pytest tests/test_merchant.py -v
"""

import pytest
from unittest.mock import patch

from app import create_app
from app.extensions import db
from app.models.user import User, RolUsuario


# ── Fixtures ────────────────────────────────────────────────────────────

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


# ── Helpers ─────────────────────────────────────────────────────────────

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


def _create_merchant(client, email="merchant@test.com"):
    _register(client, email, rol="merchant")
    return _headers(client, email)


def _create_pds(client, email="pds@test.com"):
    _register(client, email, rol="pds")
    return _headers(client, email)


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Payment Methods — GET/POST/DELETE                                         ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

@pytest.mark.integration
class TestPaymentMethods:

    def test_list_empty(self, client):
        """Sin métodos → lista vacía."""
        h = _create_merchant(client)
        r = client.get("/api/v1/merchant/payment-methods", headers=h)
        assert r.status_code == 200
        assert r.get_json()["metodos"] == []

    def test_add_nequi(self, client):
        """Merchant agrega método Nequi."""
        h = _create_merchant(client)
        r = client.post("/api/v1/merchant/payment-methods", json={
            "tipo": "nequi",
            "detalle": {"numero": "3001234567", "titular": "Juan Pérez"},
            "principal": True,
        }, headers=h)
        assert r.status_code == 201
        data = r.get_json()
        assert data["tipo"] == "nequi"
        assert data["principal"] is True
        assert data["activo"] is True

    def test_add_multiple_methods(self, client):
        """Merchant agrega múltiples métodos."""
        h = _create_merchant(client, "m1@test.com")
        for tipo in ["nequi", "bancolombia", "efectivo"]:
            r = client.post("/api/v1/merchant/payment-methods", json={
                "tipo": tipo,
                "detalle": {"numero": "3001234567", "titular": "Test"},
            }, headers=h)
            assert r.status_code == 201

        r = client.get("/api/v1/merchant/payment-methods", headers=h)
        assert len(r.get_json()["metodos"]) == 3

    def test_principal_switches(self, client):
        """Marcar uno como principal desmarca los demás."""
        h = _create_merchant(client, "m2@test.com")
        r1 = client.post("/api/v1/merchant/payment-methods", json={
            "tipo": "nequi", "detalle": {"numero": "1"}, "principal": True,
        }, headers=h)
        id1 = r1.get_json()["id"]

        r2 = client.post("/api/v1/merchant/payment-methods", json={
            "tipo": "bancolombia", "detalle": {"numero": "2"}, "principal": True,
        }, headers=h)
        id2 = r2.get_json()["id"]

        r = client.get("/api/v1/merchant/payment-methods", headers=h)
        metodos = r.get_json()["metodos"]
        principals = [m for m in metodos if m["principal"]]
        assert len(principals) == 1
        assert principals[0]["id"] == id2

    def test_delete_method(self, client):
        """Eliminar método → 204 + desactivado."""
        h = _create_merchant(client, "m3@test.com")
        r = client.post("/api/v1/merchant/payment-methods", json={
            "tipo": "nequi", "detalle": {"numero": "1"},
        }, headers=h)
        mid = r.get_json()["id"]

        r = client.delete(f"/api/v1/merchant/payment-methods/{mid}", headers=h)
        assert r.status_code == 204

        r = client.get("/api/v1/merchant/payment-methods", headers=h)
        assert r.get_json()["metodos"] == []

    def test_delete_not_owner(self, client):
        """Otro usuario no puede eliminar → 404."""
        h1 = _create_merchant(client, "own_pm@test.com")
        h2 = _create_merchant(client, "other_pm@test.com")
        r = client.post("/api/v1/merchant/payment-methods", json={
            "tipo": "nequi", "detalle": {"numero": "1"},
        }, headers=h1)
        mid = r.get_json()["id"]

        r = client.delete(f"/api/v1/merchant/payment-methods/{mid}", headers=h2)
        assert r.status_code == 404

    def test_requires_merchant_role(self, client):
        """PDS no puede acceder → 403."""
        h = _create_pds(client, "pds_pm@test.com")
        r = client.get("/api/v1/merchant/payment-methods", headers=h)
        assert r.status_code == 403

    def test_requires_auth(self, client):
        """Sin token → 401."""
        r = client.get("/api/v1/merchant/payment-methods")
        assert r.status_code == 401


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Preferences — GET/PUT                                                     ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

@pytest.mark.integration
class TestPreferences:

    def test_get_defaults(self, client):
        """Preferences nuevas tienen defaults."""
        h = _create_merchant(client)
        r = client.get("/api/v1/merchant/preferences", headers=h)
        assert r.status_code == 200
        data = r.get_json()
        assert data["notif_nueva_solicitud"] is True
        assert data["notif_nueva_resena"] is True
        assert data["notif_estado_kyc"] is True
        assert data["notif_pago_recibido"] is True
        assert data["push_enabled"] is True
        assert data["email_digest"] == "daily"

    def test_update_preferences(self, client):
        """Actualizar preferencias."""
        h = _create_merchant(client, "m_pref@test.com")
        r = client.put("/api/v1/merchant/preferences", json={
            "notif_nueva_solicitud": False,
            "email_digest": "weekly",
        }, headers=h)
        assert r.status_code == 200
        data = r.get_json()
        assert data["notif_nueva_solicitud"] is False
        assert data["email_digest"] == "weekly"
        # Los que no se tocaron mantienen default
        assert data["notif_nueva_resena"] is True

    def test_idempotent_get(self, client):
        """Segundo GET retorna las mismas preferencias."""
        h = _create_merchant(client, "m_pref2@test.com")
        r1 = client.get("/api/v1/merchant/preferences", headers=h)
        r2 = client.get("/api/v1/merchant/preferences", headers=h)
        assert r1.get_json()["email_digest"] == r2.get_json()["email_digest"]

    def test_requires_merchant_role(self, client):
        """PDS no puede acceder → 403."""
        h = _create_pds(client, "pds_pref@test.com")
        r = client.get("/api/v1/merchant/preferences", headers=h)
        assert r.status_code == 403


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Stats — GET /negocios/<id>/stats                                          ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

@pytest.mark.integration
class TestNegocioStats:

    def _crear_negocio(self, client, headers):
        with patch("app.routes.negocios.text", side_effect=lambda sql: None):
            return client.post("/api/v1/negocios/", json={
                "nombre": "Negocio Stats",
                "latitud": 10.4806,
                "longitud": -73.2495,
                "direccion": "Calle 10 #5-20, Valledupar",
                "categoria_principal": "gastronomia",
            }, headers=headers)

    def test_stats_ok(self, client):
        """Owner puede ver stats de su negocio."""
        h = _create_merchant(client, "stats_owner@test.com")
        r = self._crear_negocio(client, h)
        nid = r.get_json()["id"]
        r = client.get(f"/api/v1/negocios/{nid}/stats", headers=h)
        assert r.status_code == 200
        data = r.get_json()
        assert data["negocio_id"] == nid
        assert data["periodo"] == "total"
        assert data["calificacion_promedio"] == 0.0
        assert data["total_calificaciones"] == 0
        assert data["contratos_completados"] == 0
        assert data["ingresos_totales"] == 0

    def test_stats_not_owner(self, client):
        """Otro merchant no puede ver stats → 403."""
        h1 = _create_merchant(client, "owner_s@test.com")
        h2 = _create_merchant(client, "other_s@test.com")
        r = self._crear_negocio(client, h1)
        nid = r.get_json()["id"]
        r = client.get(f"/api/v1/negocios/{nid}/stats", headers=h2)
        assert r.status_code == 403

    def test_stats_404(self, client):
        """Negocio inexistente → 404."""
        h = _create_merchant(client, "stats_404@test.com")
        r = client.get("/api/v1/negocios/99999/stats", headers=h)
        assert r.status_code == 404

    def test_stats_with_ratings(self, client):
        """Stats refleja ratings existentes."""
        from app.models.negocio import NegocioRating
        h_own = _create_merchant(client, "s_own@test.com")
        r = self._crear_negocio(client, h_own)
        nid = r.get_json()["id"]

        # Crear 2 ratings
        h_u1 = _create_pds(client, "s_u1@test.com")
        h_u2 = _create_pds(client, "s_u2@test.com")
        client.post(f"/api/v1/negocios/{nid}/rating", json={"puntaje": 5}, headers=h_u1)
        client.post(f"/api/v1/negocios/{nid}/rating", json={"puntaje": 3}, headers=h_u2)

        r = client.get(f"/api/v1/negocios/{nid}/stats", headers=h_own)
        data = r.get_json()
        assert data["total_calificaciones"] == 2
        assert data["calificacion_promedio"] == 4.0
        assert data["distribucion_estrellas"]["5"] == 1
        assert data["distribucion_estrellas"]["3"] == 1


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Trust Score Público — GET /trust/<user_id>                                ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

@pytest.mark.integration
class TestTrustPublic:

    def test_trust_no_score(self, client):
        """Sin trust score → retorna defaults."""
        h = _create_pds(client, "trust_pds@test.com")
        # Obtener user_id
        me = client.get("/api/v1/auth/me", headers=h).get_json()
        uid = me["id"]

        r = client.get(f"/api/v1/trust/{uid}")
        assert r.status_code == 200
        data = r.get_json()
        assert data["puntuacion"] == 0.0
        assert data["nivel"] == "nuevo"

    def test_trust_with_score(self, client):
        """Con trust score → retorna datos."""
        h = _create_pds(client, "trust_calc@test.com")
        me = client.get("/api/v1/auth/me", headers=h).get_json()
        uid = me["id"]

        # Crear trust score y calcular
        from app.models.trust import TrustScore
        trust = TrustScore.get_or_create(pds_id=uid)
        trust.calcular()

        r = client.get(f"/api/v1/trust/{uid}")
        assert r.status_code == 200
        data = r.get_json()
        assert data["user_id"] == uid
        assert "puntuacion" in data
        assert "nivel" in data

    def test_trust_user_not_found(self, client):
        """Usuario inexistente → 404."""
        r = client.get("/api/v1/trust/99999")
        assert r.status_code == 404

    def test_trust_no_auth_required(self, client):
        """Endpoint público: no requiere JWT."""
        h = _create_pds(client, "trust_pub@test.com")
        me = client.get("/api/v1/auth/me", headers=h).get_json()
        uid = me["id"]

        # Sin headers
        r = client.get(f"/api/v1/trust/{uid}")
        assert r.status_code == 200


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Legal — Politica de Datos                                                 ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

@pytest.mark.integration
class TestLegalPoliticaDatos:

    def test_politica_datos_ok(self, client):
        """GET /legal/politica-datos retorna 200."""
        r = client.get("/api/v1/legal/politica-datos")
        assert r.status_code == 200
        data = r.get_json()
        assert "content" in data
        assert "Ley 1581" in data["ley_aplicable"]
        assert data["version"] == "1.1"

    def test_politica_datos_no_auth(self, client):
        """Endpoint público: sin JWT."""
        r = client.get("/api/v1/legal/politica-datos")
        assert r.status_code == 200


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  KYC Merchant — POST /kyc/documentos + catálogo por rol                     ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

@pytest.mark.integration
class TestKycMerchant:

    def _seed_catalogo(self):
        """Siembra el catálogo KYC de pds/solicitante/merchant."""
        from app.models.kyc import DocumentoRequerido
        from app.data.seed_kyc_merchant import DOCUMENTOS_MERCHANT
        # Catálogo pds/solicitante (mínimo para probar aislamiento)
        base = [
            ("pds", "doc_identidad", "Doc Identidad PDS", "d", True, "identidad", False, 1),
            ("pds", "prueba_vida", "Prueba de Vida", "d", True, "identidad", False, 2),
            ("solicitante", "doc_identidad", "Doc Identidad Sol", "d", True, "identidad", False, 1),
            ("solicitante", "verificacion_contacto", "Verif Contacto", "d", True, "identidad", False, 2),
        ]
        for rol, clave, nombre, desc, oblig, grupo, multi, orden in base:
            if not DocumentoRequerido.query.filter_by(rol=rol, clave=clave).first():
                db.session.add(DocumentoRequerido(
                    rol=rol, clave=clave, nombre=nombre, descripcion=desc,
                    obligatorio=oblig, grupo=grupo, multi_instancia=multi, orden=orden,
                ))
        for rol, clave, nombre, desc, oblig, grupo, multi, orden in DOCUMENTOS_MERCHANT:
            if not DocumentoRequerido.query.filter_by(rol=rol, clave=clave).first():
                db.session.add(DocumentoRequerido(
                    rol=rol, clave=clave, nombre=nombre, descripcion=desc,
                    obligatorio=oblig, grupo=grupo, multi_instancia=multi, orden=orden,
                ))
        db.session.commit()

    def test_merchant_puede_subir_doc_catalogo(self, client):
        """Merchant sube doc_identidad de su catálogo → 200."""
        self._seed_catalogo()
        h = _create_merchant(client, "kyc_m1@test.com")
        r = client.post("/api/v1/kyc/documentos", json={
            "clave": "doc_identidad", "url": "http://x/cc.jpg",
        }, headers=h)
        assert r.status_code == 200
        assert r.get_json()["estado"] == "enviado"
        assert r.get_json()["rol"] == "merchant"

    def test_merchant_puede_subir_rut(self, client):
        """Merchant sube rut (obligatorio) → 200."""
        self._seed_catalogo()
        h = _create_merchant(client, "kyc_m2@test.com")
        r = client.post("/api/v1/kyc/documentos", json={
            "clave": "rut", "url": "http://x/rut.pdf",
        }, headers=h)
        assert r.status_code == 200

    def test_merchant_no_puede_subir_doc_pds(self, client):
        """Merchant NO puede subir prueba_vida (catálogo pds) → 400."""
        self._seed_catalogo()
        h = _create_merchant(client, "kyc_m3@test.com")
        r = client.post("/api/v1/kyc/documentos", json={
            "clave": "prueba_vida", "url": "http://x/selfie.jpg",
        }, headers=h)
        assert r.status_code == 400

    def test_merchant_no_puede_subir_doc_solicitante(self, client):
        """Merchant NO puede subir verificacion_contacto (catálogo solicitante) → 400."""
        self._seed_catalogo()
        h = _create_merchant(client, "kyc_m4@test.com")
        r = client.post("/api/v1/kyc/documentos", json={
            "clave": "verificacion_contacto", "url": "http://x/contacto",
        }, headers=h)
        assert r.status_code == 400

    def test_documentos_requeridos_merchant(self, client):
        """GET /kyc/documentos-requeridos devuelve catálogo merchant (4 docs)."""
        self._seed_catalogo()
        h = _create_merchant(client, "kyc_m5@test.com")
        r = client.get("/api/v1/kyc/documentos-requeridos", headers=h)
        assert r.status_code == 200
        data = r.get_json()
        assert data["rol"] == "merchant"
        claves = {d["clave"] for d in data["documentos"]}
        assert claves == {"doc_identidad", "rut", "certificado_comercial", "foto_local"}

    def test_mis_documentos_merchant(self, client):
        """GET /kyc/mis-documentos refleja envíos del merchant."""
        self._seed_catalogo()
        h = _create_merchant(client, "kyc_m6@test.com")
        client.post("/api/v1/kyc/documentos", json={
            "clave": "rut", "url": "http://x/rut.pdf",
        }, headers=h)
        r = client.get("/api/v1/kyc/mis-documentos", headers=h)
        assert r.status_code == 200
        docs = {d["clave"]: d["estado"] for d in r.get_json()["documentos"]}
        assert docs["rut"] == "enviado"
        assert docs["doc_identidad"] == "no_enviado"


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Upload imagen negocio — POST /negocios/<id>/imagenes/upload                ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

@pytest.mark.integration
class TestNegocioImagenUpload:

    def _crear_negocio(self, client, headers):
        with patch("app.routes.negocios.text", side_effect=lambda sql: None):
            return client.post("/api/v1/negocios/", json={
                "nombre": "Negocio Upload",
                "latitud": 10.4806,
                "longitud": -73.2495,
                "direccion": "Calle 10 #5-20, Valledupar",
                "categoria_principal": "gastronomia",
            }, headers=headers)

    def _upload(self, client, nid, headers, filename="foto.jpg", content_type="image/jpeg"):
        import io
        return client.post(
            f"/api/v1/negocios/{nid}/imagenes/upload",
            data={"file": (io.BytesIO(b"\xff\xd8\xff\xe0fakejpeg"), filename, content_type)},
            headers=headers,
            content_type="multipart/form-data",
        )

    def test_upload_imagen_ok(self, client):
        """Owner sube imagen → 201 + URL + agregada a imagenes."""
        h = _create_merchant(client, "up_own@test.com")
        r = self._crear_negocio(client, h)
        nid = r.get_json()["id"]

        with patch("app.services.storage.storage") as mock_storage:
            mock_storage.upload_image.return_value = "https://minio/negocios/1/foto.webp"
            resp = self._upload(client, nid, h)
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["url"] == "https://minio/negocios/1/foto.webp"
        assert data["negocio_id"] == nid

        # La URL quedó en el array imagenes del negocio
        detalle = client.get(f"/api/v1/negocios/{nid}").get_json()
        assert "https://minio/negocios/1/foto.webp" in detalle["imagenes"]

    def test_upload_imagen_no_owner(self, client):
        """Otro merchant no puede subir → 403."""
        h1 = _create_merchant(client, "up_o1@test.com")
        h2 = _create_merchant(client, "up_o2@test.com")
        r = self._crear_negocio(client, h1)
        nid = r.get_json()["id"]
        resp = self._upload(client, nid, h2)
        assert resp.status_code == 403

    def test_upload_imagen_sin_archivo(self, client):
        """Sin campo file → 400."""
        h = _create_merchant(client, "up_nf@test.com")
        r = self._crear_negocio(client, h)
        nid = r.get_json()["id"]
        resp = client.post(f"/api/v1/negocios/{nid}/imagenes/upload", headers=h)
        assert resp.status_code == 400

    def test_upload_imagen_formato_invalido(self, client):
        """Formato no permitido (gif) → 400."""
        h = _create_merchant(client, "up_fmt@test.com")
        r = self._crear_negocio(client, h)
        nid = r.get_json()["id"]
        resp = self._upload(client, nid, h, filename="anim.gif", content_type="image/gif")
        assert resp.status_code == 400

    def test_upload_imagen_negocio_404(self, client):
        """Negocio inexistente → 404."""
        h = _create_merchant(client, "up_404@test.com")
        resp = self._upload(client, 99999, h)
        assert resp.status_code == 404

    def test_upload_imagen_requiere_auth(self, client):
        """Sin token → 401."""
        h = _create_merchant(client, "up_auth@test.com")
        r = self._crear_negocio(client, h)
        nid = r.get_json()["id"]
        resp = self._upload(client, nid, {})
        assert resp.status_code == 401
