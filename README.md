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
- Celery (tareas asíncronas + beat scheduler)
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
  tasks.py         # Celery tasks
tests/             # 35 archivos de test (370 tests)
```

---

## Despliegue en Desarrollo con Docker

### Prerrequisitos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) v4.0+
- Docker Compose v2 (incluido en Docker Desktop)
- ~4 GB de RAM libre (PostgreSQL + Redis + MinIO + Backend + Celery)

### Inicio rápido

```bash
cd Chambeapp_backend

# 1. Copiar variables de entorno (ajusta valores si es necesario)
cp .env.example .env

# 2. Levantar todos los servicios (primera vez incluye build)
docker compose -f docker-compose.dev.yml up -d --build

# 3. Verificar que todo esté corriendo
docker compose -f docker-compose.dev.yml ps
```

La primera vez tarda ~2-5 minutos (build de imagen + seed de datos demo).
En arranques posteriores (~30s):

```bash
docker compose -f docker-compose.dev.yml up -d
```

### Variables de entorno

El archivo `.env` se carga automáticamente en los contenedores.
Si no existe, se usan los valores por defecto indicados entre corchetes.

| Variable | Descripción | Default (dev) |
|----------|-------------|---------------|
| `SECRET_KEY` | Clave secreta de Flask | `dev-secret-change-me` |
| `JWT_SECRET_KEY` | Clave para firmar JWTs | `dev-jwt-secret-change-me` |
| `DB_PASSWORD` | Password de PostgreSQL | `chambeapp_dev` |
| `MINIO_USER` | Usuario de MinIO | `chambeapp` |
| `MINIO_PASSWORD` | Password de MinIO | `chambeapp_dev` |
| `ONURIX_CLIENT` | Client ID de Onurix SMS | *(vacío)* |
| `ONURIX_KEY` | API Key de Onurix SMS | *(vacío)* |
| `SMS_SEND_DEV` | Enviar SMS reales en dev (`0`/`1`) | `0` |

> **Nota:** En desarrollo, `DATABASE_URL` se construye automáticamente
> apuntando al contenedor `db:5432`. No es necesario configurarlo manualmente.

### Servicios

El stack de desarrollo levanta 5 contenedores:

| Servicio | Contenedor | Puerto | Descripción |
|----------|------------|--------|-------------|
| **db** | `chambeapp_db_dev` | `5432` | PostgreSQL 16 + PostGIS 3.4 |
| **redis** | `chambeapp_redis_dev` | `6379` | Redis 7 (cache + cola Celery) |
| **minio** | `chambeapp_minio_dev` | `9000`/`9001` | Almacenamiento S3-compatible |
| **backend** | `chambeapp_backend_dev` | `5000` | API Flask con hot-reload |
| **celery_worker** | `chambeapp_celery_dev` | — | Worker de tareas asíncronas |
| **celery_beat** | `chambeapp_celery_beat_dev` | — | Scheduler de tareas periódicas |

### Acceso a servicios

| Servicio | URL |
|----------|-----|
| API Flask | http://localhost:5000 |
| Swagger UI | http://localhost:5000/api/v1/swagger-ui |
| MinIO Console | http://localhost:9001 |
| PostgreSQL | `localhost:5432` (user: `chambeapp`, pass: `chambeapp_dev`) |
| Redis | `localhost:6379` |

### Hot-reload

En desarrollo, el código fuente se monta como bind mount en el contenedor:

```yaml
volumes:
  - .:/app
```

Cualquier cambio en los archivos `.py` se refleja inmediatamente sin
reconstruir la imagen. El servidor `run.py` detecta cambios y recarga automáticamente.

### Comandos útiles

```bash
# Ver logs de todos los servicios
docker compose -f docker-compose.dev.yml logs -f

# Ver logs de un servicio específico
docker compose -f docker-compose.dev.yml logs -f backend
docker compose -f docker-compose.dev.yml logs -f celery_worker

# Detener todos los servicios
docker compose -f docker-compose.dev.yml down

# Detener y eliminar volúmenes (reset completo de datos)
docker compose -f docker-compose.dev.yml down -v

# Reconstruir imagen (después de cambiar requirements.txt)
docker compose -f docker-compose.dev.yml up -d --build

# Ejecutar seed manualmente
docker compose -f docker-compose.dev.yml exec backend python seed.py

# Ejecutar migraciones
docker compose -f docker-compose.dev.yml exec backend flask db upgrade

# Ejecutar tests
docker compose -f docker-compose.dev.yml exec backend pytest -v

# Entrar al contenedor del backend
docker compose -f docker-compose.dev.yml exec backend bash

# Ver estado de los contenedores
docker compose -f docker-compose.dev.yml ps
```

### Entrypoint de desarrollo

El script `docker-entrypoint-dev.sh` se ejecuta automáticamente al iniciar
el contenedor del backend. Realiza en orden:

1. **Espera a PostgreSQL** — reintenta hasta 60s hasta que la DB esté lista
2. **Seed automático** — si la base está vacía, ejecuta `seed.py` (create_all + datos demo)
3. **Extensiones PostGIS** — crea extensión, columna `geom`, feature flags ML (idempotente)
4. **Stamp de migraciones** — registra migraciones como aplicadas sin re-ejecutar
5. **Arranca Flask** — `python run.py` con hot-reload

### Datos demo (seed)

El seed inicializa:
- 7 usuarios con diferentes roles (pds, solicitante, merchant, verificador, soporte, admin, superadmin)
- 1 negocio merchant con imágenes
- Documentos KYC de ejemplo
- Configuración de la aplicación
- Feature flags ML (ranking, shadow mode, etc.)

Credenciales de demo:
| Usuario | Contraseña | Rol |
|---------|-----------|-----|
| admin@chambeapp.com | `admin123` | superadmin |
| merchant@chambeapp.com | `merchant123` | merchant |
| pds@chambeapp.com | `pds123` | pds |

### Troubleshooting

**El contenedor del backend no arranca / se reinicia:**
```bash
docker compose -f docker-compose.dev.yml logs backend
```
Causa común: PostgreSQL no está listo. El entrypoint reintenta 30 veces
(con 2s de espera = 60s max). Si persiste, verifica que el puerto 5432
no esté ocupado por otra instancia de PostgreSQL.

**Error "port already in use":**
```bash
# Identificar qué proceso usa el puerto
netstat -ano | findstr :5432
# Matar el proceso o cambiar el port en docker-compose.dev.yml
```

**Datos corruptos / quiero empezar de cero:**
```bash
docker compose -f docker-compose.dev.yml down -v
docker compose -f docker-compose.dev.yml up -d --build
```

**El hot-reload no funciona:**
- Verifica que el bind mount `.:/app` esté presente en `docker-compose.dev.yml`
- En Windows, asegúrate de que Docker Desktop tiene permisos para acceder
  a la carpeta del proyecto (Settings > Resources > File Sharing)

**MinIO no accesible:**
- Console: http://localhost:9001 (user: `chambeapp`, pass: `chambeapp_dev`)
- Si el bucket no existe, créalo desde la consola o ejecuta el seed

**Celery worker no procesa tareas:**
```bash
docker compose -f docker-compose.dev.yml logs celery_worker
```
Verifica que Redis esté corriendo: `docker compose -f docker-compose.dev.yml exec redis redis-cli ping`

---

## Puesta en marcha local (sin Docker)

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
