# StutterES

Toolkit para el estudio del tartamudeo en español: detección de eventos de
tartamudeo, generación de habla disfluente sintética y evaluación de sistemas
de reconocimiento de voz bajo tartamudeo.

Dos conjuntos de datos, construidos sobre el mismo corpus de cinco hablantes
leyendo 100 noticias en voz alta.

## 1. Clips de 3 s — `src/clips_3s/`

Ventanas fijas de 3 segundos con las disfluencias anotadas a mano, repartidas
en train/val/test de forma estratificada por hablante y disfluencia.

    ./run_all.sh

Salidas en `outputs/`.

## 2. Clips por oración — `src/oraciones/`

Los audios completos de lectura, cortados en clips del tamaño de cada oración
del texto leído.

    ./run_oraciones.sh

| script | qué hace |
|---|---|
| `fetch_data.py` | descarga los audios (Zenodo) y los textos (Drive) |
| `mapear_textos.py` | limpia los .txt y los parte en oraciones |
| `asr.py` | transcribe con faster-whisper |
| `reparar_asr.py` | rellena los tramos que el modelo se salta |
| `emparejar.py` | decide qué audio corresponde a qué lectura |
| `depurar.py` | quita las oraciones que ningún hablante leyó |
| `segmentar.py` | corta cada audio por oraciones |
| `organizar_clips.py` | ordena los clips por hablante y lectura |
| `sumar_anotaciones.py` | asigna los clips de 3 s a su oración y suma sus disfluencias |

Salidas:

    clips_oraciones/<hablante>/Lectura NNN/sNNN.wav
    outputs_oraciones/oraciones.csv
    outputs_oraciones/oraciones_con_disfluencias.xlsx
    outputs_oraciones/informes/

100 textos → 1348 oraciones → 6674 clips (99,0 % de los posibles).

Ver `NOTAS_oraciones.txt` para el método y sus límites.

## 3. Anotador web — `web/` y `src/web/`

Interfaz para revisar y corregir a mano las disfluencias, oración por oración.

    ./run_web.sh          # http://127.0.0.1:8765

Hablantes → 100 lecturas → oraciones. De cada oración muestra el número, el
texto, la onda del clip de esa oración, los clips de 3 s que caen dentro con
sus etiquetas, y la lista de disfluencias.

Arrastrando sobre la onda se marca una disfluencia con el tipo activo. Toda
marca dura **exactamente 3 s**, como los clips del otro dataset: el arrastre
solo elige donde empieza la ventana, y el servidor la encaja igual (si la
oracion dura menos de 3 s, la ventana es la oracion entera). Las marcas se
pueden mover y solapar libremente; tambien se les cambia el tipo o se borran. Cada oración lleva
un estado (pendiente / en progreso / completada / dudosa) y una nota, así que
la revisión se puede dejar a medias y retomar.

La primera vez que se abre una lectura, sus disfluencias se siembran con lo
que ya se sabe por los clips de 3 s anotados; a partir de ahí se corrigen.

Las anotaciones van a `anotaciones.db` (SQLite); los CSV originales no se
tocan. `/api/export.csv` vuelca todo a CSV.

| archivo | qué hace |
|---|---|
| `build_dataset.py` | cruza oraciones.csv, index.csv y los textos en `dataset.json` |
| `app.py` | servidor (solo biblioteca estandar) y API de anotacion |
| `static/` | la interfaz |

### Anotador desplegado: `web/` + `deploy/`

Para que varias personas anoten a la vez, `web/server.py` lo sirve todo en un
proceso: la interfaz, la API, el SQLite y los audios comprimidos a Opus
(2,4 GB → 227 MB). La web guarda **dónde** corta cada uno; el corte real se
hace luego aquí con `src/web/exportar.py`, que saca los WAV de 3 s del audio
original y un `index.csv` del mismo formato que el del dataset de clips.

    .venv/bin/python src/web/build_web.py         # datos estáticos
    .venv/bin/python src/web/preparar_audio.py    # audios en opus
    python3 web/server.py                         # http://127.0.0.1:8765

| archivo | qué hace |
|---|---|
| `web/server.py` | web, API, SQLite, audio y recortes |
| `src/web/build_web.py` | formas de onda y lista de oraciones |
| `src/web/preparar_audio.py` | comprime los 500 WAV a Opus |
| `src/web/exportar.py` | recoge las anotaciones y corta los WAV de 3 s |
| `deploy/` | Dockerfile, arranque y guía de despliegue |

Guía de despliegue en `deploy/README.md`; el porqué de cada decisión, en
`web/README.md`.

`./run_web.sh` es la versión local anterior, que sirve los WAV del disco.
