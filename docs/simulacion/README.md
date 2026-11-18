# Simulacion Valledupar

Datos 100% ficticios generados por `seed_simulacion_valledupar.py`.

## Credenciales

- Todas las cuentas usan la contrasena: `ChambeApp123!`
- PDS: `pds001@sim.chambeapp.co` ... `pds150@sim.chambeapp.co`
- Solicitantes: `sol001@sim.chambeapp.co` ... `sol072@sim.chambeapp.co`
- Merchants: `neg001@sim.chambeapp.co` ... `neg010@sim.chambeapp.co`
- Staff: `staff.*@sim.chambeapp.co`
- Listado completo: `docs/simulacion/credenciales.csv`

## Volumen

- Usuarios: 240
- Solicitudes: 300
- Ofertas: 720
- Contratos: 185
- Chambas: 165
- Pagos: 150

## Comandos

```bash
python seed_simulacion_valledupar.py --reset
python seed_simulacion_valledupar.py --reset --config app.config.TestingConfig --create-all
```

El reset elimina solo cuentas `@sim.chambeapp.co` y sus dependencias.

## Nota de seguridad

Estas credenciales son de simulacion. No usar en produccion.
