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
