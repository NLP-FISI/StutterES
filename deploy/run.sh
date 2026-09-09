#!/usr/bin/env bash
# Anotador StutterES en phantom.
#
#   ./run.sh start | stop | status | log
#
# Levanta dos cosas y las vigila: el servidor (python, solo biblioteca
# estandar) y el tunel de Cloudflare que le da la URL publica. Si alguno se
# cae, el vigilante lo vuelve a levantar solo.
#
# El servidor escucha SOLO en 127.0.0.1: desde el resto de la universidad no
# se ve, unicamente a traves del tunel.
set -uo pipefail
cd "$(dirname "$0")"
BASE="$PWD"
PUERTO=${PUERTO:-8765}
LOGS="$BASE/logs"
mkdir -p "$LOGS"

pid_de() { pgrep -u "$USER" -f "$1" | head -1; }

arranca_web() {
  HOST=127.0.0.1 PUERTO=$PUERTO \
  DB_PATH="$BASE/web/anotador.db" AUDIO_DIR="$BASE/web_audio" AUDIO_EXT=opus \
  setsid nohup python3 "$BASE/web/server.py" >>"$LOGS/web.log" 2>&1 &
}

arranca_tunel() {
  setsid nohup "$BASE/bin/cloudflared" tunnel --no-autoupdate \
    --url "http://127.0.0.1:$PUERTO" >>"$LOGS/tunel.log" 2>&1 &
}

respalda() {
  # Copia consistente con la base en uso; se guardan las 48 ultimas.
  mkdir -p "$BASE/respaldos"
  local n; n=$(date +%Y%m%d-%H%M%S)
  python3 -c "import sqlite3;sqlite3.connect('$BASE/web/anotador.db').execute(\"VACUUM INTO '$BASE/respaldos/anotador-$n.db'\")"     >>"$LOGS/respaldo.log" 2>&1     && echo "[$(date +%F' '%T)] respaldo anotador-$n.db" >>"$LOGS/respaldo.log"
  ls -1t "$BASE"/respaldos/anotador-*.db 2>/dev/null | tail -n +49 | xargs -r rm -f
}

vigila() {
  local i=0
  while true; do
    pid_de "server.py" >/dev/null || { echo "[$(date +%F' '%T)] web caida, relevanto" >>"$LOGS/vigilante.log"; arranca_web; }
    pid_de "cloudflared tunnel" >/dev/null || { echo "[$(date +%F' '%T)] tunel caido, relevanto" >>"$LOGS/tunel.log"; arranca_tunel; }
    i=$((i+1))
    [ $((i % 180)) -eq 0 ] && respalda      # cada hora
    sleep 20
  done
}

url() { grep -ho 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOGS/tunel.log" 2>/dev/null | tail -1; }

case "${1:-start}" in
  start)
    pid_de "server.py"        >/dev/null || arranca_web
    pid_de "cloudflared tunnel" >/dev/null || arranca_tunel
    pid_de "run.sh vigila"    >/dev/null || setsid nohup "$0" vigila >/dev/null 2>&1 &
    sleep 12
    echo "web:    $(pid_de 'server.py'        || echo NO)"
    echo "tunel:  $(pid_de 'cloudflared tunnel' || echo NO)"
    echo "url:    $(url)"
    ;;
  vigila) vigila ;;
  stop)
    pkill -u "$USER" -f "run.sh vigila"
    pkill -u "$USER" -f "$BASE/web/server.py"
    pkill -u "$USER" -f "cloudflared tunnel --no-autoupdate --url http://127.0.0.1:$PUERTO"
    echo parado ;;
  status)
    echo "web:    $(pid_de 'server.py'        || echo NO)"
    echo "tunel:  $(pid_de 'cloudflared tunnel' || echo NO)"
    echo "vigila: $(pid_de 'run.sh vigila'    || echo NO)"
    echo "url:    $(url)"
    echo "marcas: $(python3 -c "import sqlite3;print(sqlite3.connect('$BASE/web/anotador.db').execute('select count(*) from disfluencia').fetchone()[0])" 2>/dev/null)" ;;
  url) url ;;
  respaldo) respalda; ls -1t "$BASE"/respaldos/*.db 2>/dev/null | head -3 ;;
  log) tail -n "${2:-30}" "$LOGS/web.log" ;;
  *) echo "uso: $0 {start|stop|status|url|log|respaldo}"; exit 1 ;;
esac
