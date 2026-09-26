# ChambeApp Backend CHANGELOG

All notable changes to this project will be documented in this file.

## [Unreleased] - 2026-09-26

### Security
- **Registro público restringido**: `POST /auth/register` solo acepta los roles
  públicos `pds|solicitante|merchant`; cualquier rol de administración
  (`verificador|soporte|admin|superadmin`) → **422**. El personal de
  administración lo crea el superadmin vía `/superadmin/admins` (o el admin
  regional crea `verificador|soporte` de su región vía `/admin/staff`); el
  panel admin solo expone login. Tests de regresión en `test_auth.py` (4 casos).
- **2FA efectiva en login**: el toggle ya no es decorativo. Si
  `user.two_factor_enabled`, `/auth/login` NO entrega tokens → responde
  `{ requires_2fa: true, dev_code?, expires_in }` (desafío de 6 dígitos con
  expiración/reintentos en `app/services/two_factor.py`, SMS vía Onurix en prod).
  Nuevo `POST /auth/2fa/verify` valida el código y emite access+refresh.
  Tests 2FA en `test_security.py` (6 casos).

### Security
- **Arreglos de seguridad** sobre el JWT/RBAC existente:
  - Access token 8h→**30 min**; refresh 30d→**7 días**; algoritmo `HS256` fijado.
  - `/auth/refresh` **renueva y emite nuevo refresh_token** y verifica cuenta
    activa + `role_v` (revocación también para refresh).
  - **Sockets con JWT**: nuevo `app/auth/socket_auth.py`; el **chat ya no confía
    en `user_id` del cliente** — la identidad se deriva del token (handshake o
    evento). Ofertas y notificaciones usan el mismo helper.
  - Auditoría de rutas: 182/217 endpoints exigen autenticación; 35 públicos
    explícitos (catálogo/lectura/auth). Tests `tests/test_security.py` (20 casos):
    auditoría de GET públicos, rutas sensibles, RBAC 403, revocación `role_version`,
    refresh, socket auth.
- Test de certificación técnica alineado al diseño (siempre `en_revision` hasta
  verificación por verificador).

### Refactor
- **Arquitectura MVC**: `app/routes/` → **`app/controllers/`** (capa Controller
  HTTP/MVC). Capas: `controllers/` (blueprints), `models/`, `views/schemas`,
  `services/`, `auth/`, `tasks/`. Imports actualizados en factory, controladores
  y tests. Suite completa: **544 passed, 1 skipped**.

## [1.0.0] - 2026-09-01

### Added
- RF-01: User registration endpoint with T&C acceptance
- RF-07: Legal acceptance model and endpoint
- RF-17: Clickwrap T&C public endpoint
- JWT authentication with 8h access / 30d refresh tokens
- User profiles (trabajador, empleador, verificador, soporte, admin, superadmin)
- SQLAlchemy 2.0 models: User, Profile, LegalAcceptance
- Flask-Smorest OpenAPI specification
- Flask-JWT-Extended integration
- Flask-Migrate for database migrations
- pytest test suite

### Changed
- Refactored RolUsuario alignment with PDS/solicitante
- Added guard anti-PDS in POST /solicitudes
- Updated .env.example with JWT secrets

### Fixed
- Various model and schema refinements

## Unreleased

### Added
- Módulo de Gestión de Chamba (ciclo de vida de ejecución): tabla `chambas`
  (1:1 con `contracts`), máquina de estados con 7 estados, geo-validación de
  inicio de obra (PostGIS `ST_DistanceSphere` / Haversine en tests),
  evidencias de entrada/salida, adendas y novedades, confirmación dual de
  pago directo, calificación final con habilidades validadas.
- `POST /chambas/evidencia/upload` — sube evidencias (base64) a MinIO y
  devuelve la URL pública (patrón foto-perfil).
- Flujo de firma: aceptar una propuesta ya NO marca la solicitud como
  asignada (sigue publicada hasta firmar); al firmar el contrato
  (PATCH /contracts/<id>/estado → aceptar) la solicitud pasa a "en curso"
  (asignada) y la chamba se genera automáticamente (hito 1). Notificación
  al PDS "propuesta aceptada" con indicación de firmar.
- Negociación simétrica ("a convenir"): el PDS puede contraofertar
  (contra-contraoferta) y rechazar cuando hay una contraoferta activa del
  solicitante; al aceptar tras una contraoferta, el precio acordado es el
  último `contra_monto`. Notificaciones de contraoferta por autor.
- Oferta concreta los parámetros "a convenir" de la solicitud: `fecha_deseada`
  y `horario` en la oferta y en la contraoferta del chat
  (`contra_fecha_deseada`/`contra_horario`); al aceptar se escriben en la
  solicitud con prioridad a lo negociado. Migración `010_convenir_parametros`.
- Migración `009_add_chamba_module`.
- Hito 4 (solicitud de cierre): se exige al menos una evidencia final
  (foto/360° de la obra entregada) — 400 si no hay `evidencia_salida`.
- **Módulo Maraña (rebusque)**: adendas de otro perfil se lanzan como
  micro solicitudes públicas (`POST /chambas/<id>/marana` las deriva y
  MUEVE el monto_extra fuera de la chamba). Feed `GET /maranas/`,
  postulaciones y negociación tipo ofertas (contraoferta incluida),
  asignación, entrega y pago directo dual (como la chamba).
  Migración `011_marana_module`.
- Adendas mejoradas: `cubierta_por` (pds_actual/otro_pds) +
  `categoria_requerida`; el PDS puede SUGERIR trabajo de otro perfil
  (`sugerida_por_pds`); edición (PATCH) y eliminación (DELETE) de adendas
  no derivadas por el solicitante; validación monto/tiempo >= 0.
- Tiempo extra configurable en minutos/horas/días (`tiempo_extra_unidad`).
- Validación de habilidades en la REVISIÓN (Hito 4): nuevo
  `POST /chambas/<id>/validacion` (solicitante, estado pendiente_validacion)
  guarda `habilidades_validadas` + `fecha_validacion`. La liquidación queda
  solo para la notificación del pago; la calificación final conserva las
  habilidades ya validadas. Migración `012_fecha_validacion`.
- **Anuncios Laborales (no vinculantes)**: los negocios publican ofertas
  de trabajo como banner publicitario visible en el mapa de negocios para
  todos los roles. Postulaciones de PDS con datos de contacto y gestión
  del negocio (contactar/descartar); cerrar/reabrir anuncio.
  Migración `013_anuncios` + tests `test_anuncios.py` (10 casos).
- Tests `tests/test_chambas.py` (40 casos) + `tests/test_maranas.py` (16 casos)
  + `tests/test_ofertas.py` (13 casos).
- **División regional (Fase 4)**: administración por regiones de Colombia.
  Nueva tabla `regions` + `users.region_id` (Migración `014_regiones`,
  catálogo sembrado por `app/data/seed_regions.py`). El personal interno
  (admin/verificador/soporte) se asigna a una región y su operación queda
  acotada a ella:
  - `GET /api/v1/regions` — catálogo de regiones (cualquier rol autenticado).
  - Scope regional en el panel admin: usuarios, verificaciones, solicitudes,
    contratos, disputas, tickets y contenido se filtran por la región del
    actor (el superadmin ve todo).
  - `GET/POST /api/v1/admin/staff` — el admin regional crea y lista su
    propio personal (verificador/soporte) dentro de su región.
  - Superadmin: `POST/PATCH /superadmin/admins` aceptan `region_id` para
    crear/reasignar admins regionales.
  - `GET /kyc/pendientes` y `POST /kyc/documentos/<id>/verificar` se acotan
    a la región del verificador/admin.
  - Soporte puede gestionar tickets (`GET/PATCH /admin/tickets`) acotado a
    su región.
  - `/auth/me` y los listados de users/admins incluyen la `region`.
  - Tests `tests/test_regiones.py` (16 casos).
- **Mitigación división regional**: región derivada de la ubicación
  (`app/services/region.py`): al actualizar `zona` en el perfil o al crear
  una solicitud, la región del usuario se deriva automáticamente desde el
  departamento de su ubicación (también `GET /regions/detectar?ubicacion=`).
  Regla de propiedad anti doble-conteo: un contrato/disputa/pago pertenece a
  la región de su SOLICITANTE, por lo que se lista, modera y contabiliza en
  una sola región (el proveedor de otra región no lo ve). Nuevo
  `POST /superadmin/regions/reindex` reasigna la región de los usuarios
  públicos desde su zona o última solicitud (no toca personal interno).
  Tests ampliados a 24 casos.
- **Onboarding asigna región**: `PATCH /onboarding/step` ahora deriva la región
  del usuario desde su `zona` (`app/services/region.assign_region`), cerrando el
  punto más temprano de identificación por ubicación. Tests regionales a 25 casos.
- Pending: RF-02 to RF-16, payments, chat, IA