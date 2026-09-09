# Desplegar el anotador en un solo servidor

Web, API, base de datos y audio en un contenedor, sin dependencias de Python:
todo es biblioteca estandar.

## 1. Preparar los datos (en tu PC, una vez)

```bash
.venv/bin/python src/web/build_web.py         # web/public/data/, 8,5 MB
.venv/bin/python src/web/preparar_audio.py    # web_audio/, ~227 MB en opus
```

`build_web.py` saca las formas de onda y la lista de oraciones.
`preparar_audio.py` comprime los 500 WAV: **2,4 GB pasan a 227 MB**. El
dataset no pierde nada, porque **los cortes finales se sacan siempre de los
WAV originales** con `src/web/exportar.py`; esta copia es solo para escuchar.

## 2. Construir y arrancar

```bash
docker build -f deploy/Dockerfile -t stutteres-anotador .
docker run -d -p 8080:80 -v anotador:/data --name anotador stutteres-anotador
```

O `docker compose -f deploy/docker-compose.yml up -d --build`.

En **Dokploy**: aplicacion tipo *Dockerfile*, contexto en la raiz del repo,
ruta `deploy/Dockerfile`, puerto 80, un volumen persistente montado en `/data`
y el dominio que quieras. Dokploy pone el HTTPS por delante.

## 3. Recoger el trabajo y cortar el audio

La web guarda **donde** corta cada anotador, no el audio. Cuando la ronda
termine, se trae la base y se cortan los WAV de verdad:

```bash
docker cp anotador:/data/anotador.db ./anotador.db      # o copia el volumen
.venv/bin/python src/web/exportar.py --sqlite anotador.db
```

Salidas:

- `clips_web/<hablante>/<hablante>_<epid>_w<id>.wav` — un WAV de **3 s exactos**
  por marca, cortado del original.
- `outputs_web/anotaciones.csv` — cada marca con tipo, autor, nota y tiempos.
- `outputs_web/index.csv` — mismo formato que `outputs/index.csv`.
- `outputs_web/estado.csv` — como quedo la revision de cada oracion.

## Respaldos

Todo el estado es `/data/anotador.db` (SQLite en modo WAL). Copiarlo es el
respaldo completo:

```bash
docker exec anotador python -c \
  "import sqlite3,shutil;\
   c=sqlite3.connect('/data/anotador.db');c.execute('VACUUM INTO \"/data/copia.db\"')"
docker cp anotador:/data/copia.db ./copia-$(date +%F).db
```

## Ajustes

| variable | por defecto | para que |
|---|---|---|
| `PUERTO` / `HOST` | `80` / `0.0.0.0` | donde escucha |
| `DB_PATH` | `/data/anotador.db` | la base |
| `AUDIO_DIR` | `/app/web_audio` | los audios |
| `AUDIO_EXT` | `opus` | `mp3` si prefieres maxima compatibilidad |

Si no quieres 227 MB dentro de la imagen, quita el `COPY web_audio` del
Dockerfile y monta un volumen en `/app/web_audio`.

## Probar antes en local

```bash
.venv/bin/python web/server.py     # http://127.0.0.1:8765
```

Es exactamente el mismo servidor que corre en el contenedor.
