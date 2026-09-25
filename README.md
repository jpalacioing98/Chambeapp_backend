# ChambeApp Backend

API REST Flask para ChambeApp. Cubre la fundación (auth/usuarios, RF-01/RF-17)
y los módulos de negocio: solicitudes, ofertas, contratos, pagos, wallet,
chat, KYC, admin, superadmin, IA, negocios y **módulo Comerciante (merchant)**.

## Stack

- Flask 3.1 + Flask-Smorest 0.47 (OpenAPI)
- Flask-JWT-Extended (JWT 8h access / 30d refresh)
- SQLAlchemy 2.0 + Flask-Migrate (PostgreSQL/PostGIS; SQLite en dev/test)
- Flask-Caching (Redis; SimpleCache en test)
- Flask-Bcrypt (hash de passwords)
- Marshmallow (validación)
- MinIO (S3-compatible) para uploads de imágenes/documentos
- pytest (tests)

## Estructura

```
app/
  __init__.py      # factory create_app() — 28 blueprints
  config.py        # Config / Development / Production / Testing
  extensions.py    # db, migrate, jwt, cache, bcrypt, socketio
  models/          # 21 modelos SQLAlchemy
  schemas/         # Marshmallow
  routes/          # 28 blueprints (~158 endpoints)
  services/        # Lógica de negocio (pagination, storage, trust, ...)
tests/             # 35 archivos de test (370 tests)
```

## Puesta en marcha

```bash
cd Chambeapp_backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt

# Variables de entorno
cp .env.example .env          # editar SECRET_KEY / JWT_SECRET_KEY / DATABASE_URL

# Migraciones
flask db upgrade

# Correr API
python run.py                 # o: flask run (puerto 5000)

# Seed de datos demo (7 usuarios, negocio merchant, KYC, config)
python seed.py

# Tests (usando SQLite en memoria vía TestingConfig)
pytest -v
```

## Endpoints principales

| Método | Ruta | Auth | Descripción |
|--------|------|------|-------------|
| POST | `/api/v1/auth/register` | no | Registro (requiere `acepto_tyc=true`) |
| POST | `/api/v1/auth/login` | no | Login → access+refresh token |
| GET | `/api/v1/auth/me` | access | Perfil del usuario |
| GET/POST | `/api/v1/negocios/` | GET public / POST merchant | Listar / crear negocio |
| GET/PUT/DELETE | `/api/v1/negocios/<id>` | GET public / resto owner | Detalle / editar / eliminar |
| GET | `/api/v1/negocios/<id>/stats` | merchant owner | Dashboard de métricas |
| POST | `/api/v1/negocios/<id>/imagenes/upload` | merchant owner | Upload imagen a MinIO |
| GET/POST | `/api/v1/merchant/payment-methods` | merchant | Métodos de pago |
| DELETE | `/api/v1/merchant/payment-methods/<id>` | merchant | Eliminar método de pago |
| GET/PUT | `/api/v1/merchant/preferences` | merchant | Preferencias de notificación |
| GET | `/api/v1/trust/<user_id>` | no | Trust score público |
| GET | `/api/v1/legal/politica-datos` | no | Política de datos (Ley 1581) |
| POST | `/api/v1/kyc/documentos` | pds/solicitante/merchant | Subir documento KYC |

Documentación OpenAPI/Swagger disponible en `/api/v1/swagger-ui` (Flask-Smorest).

## Notas

- En dev/test sin PostgreSQL, `DATABASE_URL` cae a SQLite automáticamente.
- Roles soportados (7): `pds`, `solicitante`, `merchant`, `verificador`,
  `soporte`, `admin`, `superadmin`.
- El enum `users.rol` en PostgreSQL se migra con `005_add_merchant_to_rol_enum`
  (agrega `'merchant'` de forma idempotente vía `autocommit_block`).
- Los tests de negocios mockean el raw SQL de PostGIS (no funciona en SQLite).