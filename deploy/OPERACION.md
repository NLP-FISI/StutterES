# Anotador StutterES en phantom

Corriendo en `/data/msobrevilla/stutterES`. Nada fuera de esta carpeta se toca.

    ./run.sh status      # procesos, URL publica y cuantas marcas hay
    ./run.sh url         # solo la URL
    ./run.sh start       # arranca lo que falte
    ./run.sh stop        # para todo
    ./run.sh log 50      # ultimas lineas del servidor

## Que corre

| proceso | que hace |
|---|---|
| `web/server.py` | web, API, SQLite y audio. Python 3, solo biblioteca estandar |
| `bin/yt-dlp` | lo usa la vista de YouTube para bajar audio |
| `bin/cloudflared` | el tunel que da la URL publica |
| `run.sh vigila` | cada 20 s revisa los dos y relevanta el que se haya caido |

El servidor escucha **solo en 127.0.0.1:8765**: desde el resto de la red de la
universidad no se ve, unicamente por el tunel. No usa docker (haria falta
sudo), ni instala nada en el sistema: `cloudflared` vive en `bin/`.

## Cuidado con la URL

El tunel es de los gratuitos (`trycloudflare.com`), asi que **la URL cambia
cada vez que el tunel se reinicia**. Si el vigilante lo relevanta, sale una
nueva; consultala con `./run.sh url`.

Para una URL fija hace falta una cuenta de Cloudflare y un tunel con nombre.

## El trabajo de la gente

Todo va a `web/anotador.db` (SQLite, modo WAL). Es lo unico que hay que
respaldar:

    python3 -c "import sqlite3;sqlite3.connect('web/anotador.db').execute(\"VACUUM INTO 'copia.db'\")"

## Cortar los audios cuando termine la ronda

Los WAV originales no estan aqui, solo la copia comprimida para escuchar. El
corte se hace donde esten los WAV (2,4 GB):

    # llevarse la base
    scp .../anotador.db .
    .venv/bin/python src/web/exportar.py anotador.db

Saca `clips_web/*.wav` de 3 s exactos y `outputs_web/*.csv`.
