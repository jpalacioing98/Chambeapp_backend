# Simulacion Valledupar

Datos 100% ficticios generados por `seed_simulacion_valledupar.py`.

## Credenciales

- Todas las cuentas usan la contrasena: `ChambeApp123!`
- PDS: `pds001@sim.chambeapp.co` ... `pds015@sim.chambeapp.co`
- Solicitantes: `sol001@sim.chambeapp.co` ... `sol007@sim.chambeapp.co`
- Merchants: `neg001@sim.chambeapp.co` ... `neg002@sim.chambeapp.co`
- Staff: `staff.*@sim.chambeapp.co`
- Listado completo: `docs/simulacion/credenciales.csv`

## Volumen

- Usuarios: 28
- Solicitudes: 30
- Ofertas: 72
- Contratos: 20
- Chambas: 17
- Pagos: 39

## Comandos

```bash
python seed_simulacion_valledupar.py --reset
python seed_simulacion_valledupar.py --reset --config app.config.TestingConfig --create-all
```

El reset elimina solo cuentas `@sim.chambeapp.co` y sus dependencias.

## Nota de seguridad

Estas credenciales son de simulacion. No usar en produccion.
