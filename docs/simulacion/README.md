# Simulacion Valledupar

Datos 100% ficticios generados por `seed.py` (10 meses de actividad).

## Credenciales

- Todas las cuentas usan la contrasena: `ChambeApp123!`
- PDS: `pds001@sim.chambeapp.co` ... `pds300@sim.chambeapp.co`
- Solicitantes: `sol001@sim.chambeapp.co` ... `sol180@sim.chambeapp.co`
- Merchants: `neg001@sim.chambeapp.co` ... `neg030@sim.chambeapp.co`
- Staff: `staff.*@sim.chambeapp.co`
- Listado completo: `docs/simulacion/credenciales.csv`

## Volumen

- Usuarios: 522
- Solicitudes: 900
- Ofertas: 2600
- Contratos: 585
- Chambas: 525
- Pagos: 420

## Comandos

```bash
python seed.py --reset
python seed.py --reset --config app.config.TestingConfig --create-all
```

El reset elimina solo cuentas `@sim.chambeapp.co` y sus dependencias.

## Nota de seguridad

Estas credenciales son de simulacion. No usar en produccion.
