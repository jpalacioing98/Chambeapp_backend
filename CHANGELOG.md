# ChambeApp Backend CHANGELOG

All notable changes to this project will be documented in this file.

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
- Pending: RF-02 to RF-16, payments, chat, IA