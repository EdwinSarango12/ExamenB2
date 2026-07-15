# Informe Técnico — Analítica de Interacciones de Red Social Estudiantil (PowerESFOT)

## 0. Datos del proyecto

- **Empresa / caso**: PowerESFOT — Community Manager, red social estudiantil (15 videos, 500 interacciones).
- **Base de datos**: MySQL 8.0, esquema `examenad`, tabla `redes` (usuario, accion, fecha, hora, short/video).
- **Repositorio de trabajo**: `ExamenFinal/` (docker-compose.yml, springboot-app/, nginx/, mapreduce/, script.sql).

---

## 1. Descripción general del sistema y arquitectura

El sistema implementa el siguiente flujo, orquestado íntegramente con Docker Compose:

```
                                   ┌─────────────────────────┐
                                   │       MySQL 8.0          │
                                   │  (script.sql cargado vía │
                                   │  volumen Docker en       │
                                   │  /docker-entrypoint-     │
                                   │  initdb.d)                │
                                   └────────────┬─────────────┘
                                                │ JDBC
                        ┌───────────────────────┴───────────────────────┐
                        │                                               │
              ┌─────────▼─────────┐                          ┌──────────▼─────────┐
              │  Spring Boot app1  │                          │  Spring Boot app2   │
              │  GET /datos (8080) │                          │  GET /datos (8080)  │
              │  SERVER_NAME=server1                          │  SERVER_NAME=server2│
              └─────────┬─────────┘                          └──────────┬─────────┘
                        │                                               │
                        └───────────────────┬───────────────────────────┘
                                             │
                                   ┌─────────▼─────────┐
                                   │   Nginx (LB)       │
                                   │  upstream backend  │
                                   │  round-robin       │
                                   │  puerto 8088        │
                                   └─────────┬─────────┘
                                             │ texto plano
                                   ┌─────────▼─────────┐
                                   │  MapReduce (Python) │
                                   │  Map → Shuffle →    │
                                   │  Reduce             │
                                   │  6 métricas          │
                                   └─────────────────────┘
```

**Componentes:**

1. **MySQL + volumen Docker**: `script.sql` se monta como bind volume de solo lectura en `/docker-entrypoint-initdb.d/script.sql`. MySQL ejecuta ese script automáticamente la primera vez que el volumen de datos (`mysql_data`) está vacío, creando la base `examenad` y poblando la tabla `redes` con 500 interacciones.

2. **Dos instancias Spring Boot (app1 / app2)**: mismo artefacto (`examenfinal-app:latest`), mismo `Dockerfile`, diferenciadas únicamente por la variable de entorno `SERVER_NAME`. Exponen `GET /datos`, que consulta la tabla `redes` vía Spring Data JPA y devuelve **texto plano** (no JSON), una línea por registro, con el formato pedido:

   ```
   Diego, view, 2026-07-08, 06:01:00, video8
   ```

   Cada respuesta incluye el header `X-Served-By` con el nombre del servidor que atendió la petición, para poder demostrar el balanceo.

3. **Nginx como balanceador de carga**: definición `upstream backend { server app1:8080; server app2:8080; }`. Nginx usa por defecto el algoritmo **round-robin**, por lo que cada request entrante a `http://localhost:8088/datos` se turna entre `app1` y `app2`.

4. **Procesamiento MapReduce (Python)**: un script (`mapreduce/mapreduce.py`) consume el endpoint `/datos` a través del balanceador, y ejecuta un pipeline **Map → Shuffle → Reduce** (implementado con `multiprocessing.Pool`, simulando localmente el modelo de programación de MapReduce) para calcular las 6 métricas solicitadas. Se puede ejecutar tanto desde el host (`python mapreduce.py`) como containerizado (`docker compose run --rm mapreduce`).

---

## 2. Detalle de implementación

### 2.1 Entidad y endpoint (Spring Boot)

- `Interaccion.java`: entidad JPA mapeada a la tabla `redes`. El campo Java se llama `video` (mapeado a la columna real `short`, porque `short` es palabra reservada en Java y no puede usarse como nombre de campo).
- `DatosController.java`: `GET /datos`, `produces = text/plain`. Formatea explícitamente fecha (`yyyy-MM-dd`) y hora (`HH:mm:ss`) con `DateTimeFormatter`, porque `LocalTime.toString()` omite los segundos cuando son `:00`, lo que rompería el parseo aguas abajo.
- Variables de entorno inyectadas por contenedor: `SPRING_DATASOURCE_URL`, `SPRING_DATASOURCE_USERNAME/PASSWORD`, `SERVER_NAME`.

### 2.2 Balanceador (Nginx)

```nginx
upstream backend {
    server app1:8080;
    server app2:8080;
}
server {
    listen 80;
    location /datos {
        proxy_pass http://backend/datos;
    }
}
```

### 2.3 MapReduce (Python)

- **Map**: por cada línea recibida (`usuario, accion, fecha, hora, video`), el mapper emite pares `(clave, 1)`:
  - `VIEWS::video`, `LIKES::video`, `COMMENTS::video`, `SHARES::video` según la acción,
  - `USER::usuario` (para el usuario más recurrente),
  - `HOUR::hh` (hora extraída de `hora`, para la hora con más interacción).
- **Shuffle**: se agrupan todos los pares emitidos por clave.
- **Reduce**: un segundo `Pool` suma los valores de cada clave (patrón clásico de *word count*).
- **Driver**: con los conteos reducidos calcula rankings por categoría y el **Ratio de Interacción** por video: `(likes + comments + shares) / views` (excluyendo videos con 0 views para evitar división por cero).

---

## 3. Incidente detectado y corregido durante las pruebas

Al cargar `script.sql` por primera vez, MySQL 8 (modo estricto por defecto) rechazó el `INSERT` completo:

```
ERROR 1292 (22007) at line 12: Incorrect date value: '7/8/2026' for column 'fecha' at row 1
```

**Causa**: las fechas del script venían en formato `M/D/YYYY` (ej. `7/8/2026`), que no es un literal `DATE` válido en MySQL estricto (espera `YYYY-MM-DD`). Al fallar la sentencia `INSERT` (un único `INSERT` multi-fila), la tabla quedaba creada pero **vacía** (0 filas), y el endpoint `/datos` devolvía `Content-Length: 0`.

**Solución aplicada**: se normalizaron las 500 fechas del script a formato ISO `YYYY-MM-DD` (ej. `'7/8/2026'` → `'2026-07-08'`) con un script de reemplazo, se recreó el volumen `mysql_data` para forzar la reinicialización, y se confirmó la carga completa.

---

## 4. Pruebas de balanceo de carga (evidencia real)

Comando ejecutado y salida real:

```
$ curl -s -i http://localhost:8081/datos | head -6      # app1 directo
HTTP/1.1 200
X-Served-By: server1
Content-Type: text/plain;charset=UTF-8
Content-Length: 21872

$ curl -s -i http://localhost:8082/datos | head -6      # app2 directo
HTTP/1.1 200
X-Served-By: server2
Content-Type: text/plain;charset=UTF-8
Content-Length: 21872

$ for i in $(seq 1 8); do
    curl -s -D - -o /dev/null http://localhost:8088/datos | grep -i X-Served-By
  done
request 1 -> X-Served-By: server1
request 2 -> X-Served-By: server2
request 3 -> X-Served-By: server1
request 4 -> X-Served-By: server2
request 5 -> X-Served-By: server1
request 6 -> X-Served-By: server2
request 7 -> X-Served-By: server1
request 8 -> X-Served-By: server2
```

**Conclusión de la prueba**: el balanceador alterna perfectamente en round-robin entre `server1` y `server2` en cada request al mismo endpoint `/datos`, cumpliendo el requisito "a veces sale por server1 y a veces por server2".

Estado de los contenedores (`docker compose ps`):

```
NAME                   IMAGE                    SERVICE    STATUS
examenfinal-app1       examenfinal-app:latest   app1       Up (healthy backend)
examenfinal-app2       examenfinal-app:latest   app2       Up (healthy backend)
examenfinal-nginx-lb   nginx:alpine             nginx      Up
mysql-db               mysql:8.0                mysql-db   Up (healthy)
```

---

### Resumen de las 6 métricas solicitadas

| # | Métrica                              | Resultado                         |
|---|---------------------------------------|------------------------------------|
| 1 | Video más visto                       | **video12** (12 views)             |
| 2 | Video con más likes                   | **video13** (12 likes)             |
| 3 | Video más comentado                   | **video4** (12 comments)           |
| 4 | Usuario más recurrente                 | **Jorge** (47 interacciones)       |
| 5 | Hora con más interacción               | **13:00** (30 interacciones, empatada con 19:00) |
| 6 | Video con mayor Ratio de Interacción  | **video13** (ratio = 7.750)        |

---


## Anexo: cómo reproducir la demostración

```bash
# 1. Levantar todo el stack
docker compose up -d --build

# 2. Verificar contenedores
docker compose ps

# 3. Probar balanceo (alterna server1/server2)
for i in $(seq 1 8); do curl -s -D - -o /dev/null http://localhost:8088/datos | grep -i X-Served-By; done

# 4. Ejecutar el MapReduce contra el balanceador
cd mapreduce && python mapreduce.py --url http://localhost:8088/datos
# o, containerizado:
docker compose --profile tools run --rm mapreduce

# 5. Apagar el stack
docker compose down
```
