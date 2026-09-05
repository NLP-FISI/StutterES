#!/usr/bin/env bash
# Pipeline completo. Los pasos 1 y 3 son los largos: descarga ~1 h,
# transcripcion ~7 h en 12 cores. El resto son minutos.
set -euo pipefail
cd "$(dirname "$0")"
PY=".venv/bin/python"
mkdir -p logs outputs/informes

$PY src/oraciones/fetch_data.py       | tee logs/1_fetch.log        # audios y textos
$PY src/oraciones/mapear_textos.py    | tee logs/2_mapear.log       # txt -> oraciones
$PY src/oraciones/asr.py              | tee logs/3_asr.log          # audio -> texto
$PY src/oraciones/reparar_asr.py      | tee logs/4_reparar.log      # lo que el ASR se salto
$PY src/oraciones/emparejar.py        | tee logs/5_emparejar.log    # que audio es que lectura
$PY src/oraciones/depurar.py          | tee logs/6_depurar.log      # quita lo que nadie leyo
$PY src/oraciones/emparejar.py        > /dev/null                   # rehacer con el texto limpio
$PY src/oraciones/segmentar.py        | tee logs/7_segmentar.log    # cortar por oraciones
$PY src/oraciones/organizar_clips.py  | tee logs/8_organizar.log   # clips/<speaker>/<lectura>/
