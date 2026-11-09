# Operaciones Docker y Seed de Simulación

Este documento reúne los comandos necesarios para **detener, eliminar, reconstruir** el contenedor del backend y **poblar** la base de datos con datos de simulación.

---

## 1️⃣ Detener y eliminar el contenedor del backend
```bash
# Detener únicamente el servicio *backend*
# (el resto de los servicios permanece activo)

docker compose -f docker-compose.dev.yml stop backend

# Eliminar el contenedor (y sus volúmenes temporales) de forma forzada

docker compose -f docker-compose.dev.yml rm -f backend
```
> **Nota:** `stop` solo pausa el contenedor; `rm -f` lo borra del motor Docker. Otros servicios como `db`, `redis` o `minio` quedan intactos.

---

## 2️⃣ Reconstruir y levantar el backend
```bash
# Reconstruir la imagen y levantar el contenedor en modo "detached"

docker compose -f docker-compose.dev.yml up -d --build backend
```
> Con `--build` Docker vuelve a crear la imagen del backend (incluye cambios en el código y en el Dockerfile). El flag `-d` lo ejecuta en segundo plano.

### ⚡ Opción rápida: volver a crear **todos** los servicios
Si necesita un entorno completamente limpio (por ejemplo, al cambiar versiones de dependencias o volúmenes), puede usar:
```bash
# Borrar contenedores, redes y volúmenes de *todos* los servicios
docker compose -f docker-compose.dev.yml down -v

# Levantar todo de nuevo creando imágenes frescas
docker compose -f docker-compose.dev.yml up -d --build
```
> `down -v` elimina también los volúmenes persistentes (bases de datos, MinIO, Redis). Use esta opción con precaución si necesita conservar datos.

---

## 3️⃣ Ejecutar el *seed* de simulación
Una vez que el backend está activo y la base de datos (`chambeapp_db_dev`) está corriendo, ejecute el script de seed que genera usuarios de prueba, ofertas, solicitudes, etc.
```bash
# Ejecutar el seed dentro del propio contenedor backend
docker compose -f docker-compose.dev.yml exec backend python seed_simulacion_valledupar.py
```
> El script `seed_simulacion_valledupar.py` está en la raíz del proyecto y pobla la DB con datos consistentes para pruebas locales.

---

## 4️⃣ Resumen de pasos en una sola línea (para scripts CI)
```bash
# Detener → eliminar → reconstruir → seed (todo de una vez)

docker compose -f docker-compose.dev.yml stop backend && \
  docker compose -f docker-compose.dev.yml rm -f backend && \
  docker compose -f docker-compose.dev.yml up -d --build backend && \
  docker compose -f docker-compose.dev.yml exec backend python seed_simulacion_valledupar.py
```
> Este comando encadena los pasos con `&&` para abortar en caso de error.

---

### 📌 Consejos
- **Revisar logs**: `docker compose -f docker-compose.dev.yml logs -f backend` para observar la salida del seed y detectar posibles conflictos.
- **Persistencia**: Si desea conservar la BD entre reinicios, NO use `down -v`. Simplemente haga `stop` + `rm -f` para el backend y la DB mantendrá sus datos.
- **Entorno de producción**: Los mismos comandos pueden adaptarse cambiando `docker-compose.dev.yml` por el archivo de producción correspondiente.

---

¡Listo! Con este archivo la documentación del backend contiene los comandos esenciales para gestionar el contenedor y cargar datos de simulación.
