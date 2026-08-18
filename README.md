# ChambeApp Backend (Fundación — Auth/Usuarios)

API REST Flask para ChambeApp. Esta iteración cubre la **fundación** del
backend: registro de usuario (RF-01), aceptación de T&C clickwrap (RF-17),
login/refresh con JWT (8h) y endpoint `/me`.

## Stack

- Flask + Flask-Smorest (OpenAPI)
- Flask-JWT-Extended (JWT 8h access / 30d refresh)
- SQLAlchemy 2.0 + Flask-Migrate (PostgreSQL; SQLite en dev/test)
- Flask-Caching (Redis; SimpleCache en test)
- Flask-Bcrypt (hash de passwords)
- Marshmallow (validación)
- pytest (tests)

## Estructura

```
app/
  __init__.py      # factory create_app()
  config.py        # Config / Development / Production / Testing
  extensions.py    # db, migrate, jwt, cache, bcrypt
  models/user.py   # User, Profile, LegalAcceptance
  schemas/         # Marshmallow
  routes/auth.py   # /api/v1/auth (register, login, refresh, me)
  services/        # stub (próximas iteraciones)
tests/             # pytest
```

## Puesta en marcha

```bash
cd Chambeapp_backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt

# Variables de entorno
cp .env.example .env          # editar SECRET_KEY / JWT_SECRET_KEY

# Migraciones (opcional; los tests crean tablas en memoria)
flask db init
flask db migrate -m "init auth models"
flask db upgrade

# Correr API
flask run          # o: python run.py

# Tests (usando SQLite en memoria vía TestingConfig)
pytest -v
```

## Endpoints

| Método | Ruta                  | Auth | Descripción |
|--------|-----------------------|------|-------------|
| POST   | `/api/v1/auth/register` | no   | Registro (requiere `acepto_tyc=true`) |
| POST   | `/api/v1/auth/login`    | no   | Login → access+refresh token |
| POST   | `/api/v1/auth/refresh`  | refresh | Renueva access token |
| GET    | `/api/v1/auth/me`       | access  | Perfil del usuario |

Documentación OpenAPI/Swagger disponible en `/api/v1/swagger-ui` (Flask-Smorest).

## Notas

- En dev/test sin PostgreSQL, `DATABASE_URL` cae a SQLite automáticamente.
- Roles soportados: `trabajador`, `empleador`, `verificador`, `soporte`,
  `admin`, `superadmin`.
- No se implementan pagos, chat, IA ni otros RFs en esta iteración.
