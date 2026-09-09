# El anotador entero en una imagen: web, API, base de datos y audio.
#
#   .venv/bin/python src/web/build_web.py       # datos estaticos
#   .venv/bin/python src/web/preparar_audio.py  # web_audio/ (~230 MB)
#   docker build -f deploy/Dockerfile -t stutteres-anotador .
#   docker run -p 8080:80 -v anotador:/data stutteres-anotador
#
# Solo biblioteca estandar: no hay nada que instalar.
FROM python:3.12-slim

WORKDIR /app
COPY web/server.py   /app/web/server.py
COPY web/public      /app/web/public
COPY web_audio       /app/web_audio

ENV HOST=0.0.0.0 \
    PUERTO=80 \
    DB_PATH=/data/anotador.db \
    AUDIO_DIR=/app/web_audio \
    AUDIO_EXT=opus \
    PYTHONUNBUFFERED=1

# Las anotaciones viven aqui: es lo unico que hay que respaldar.
VOLUME /data
EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:80/api/config',timeout=4)"

CMD ["python", "/app/web/server.py"]
