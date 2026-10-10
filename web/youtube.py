"""Descarga el audio de un video de YouTube y le calcula la forma de onda.

Se usa desde server.py, en un hilo aparte: bajar y convertir tarda.
Necesita yt-dlp y ffmpeg; yt-dlp se busca primero en bin/, junto al repo.
"""
import array
import base64
import json
import re
import shutil
import subprocess
from pathlib import Path

BITRATE = "24k"
SR_PICOS = 4000          # frecuencia a la que se lee para sacar la envolvente
PICOS_MIN, PICOS_MAX = 400, 2000
SR_MAESTRO = 24000       # el WAV que se usa para clonar voz

# El opus de 24 kbps vale para escuchar y anotar, pero es una referencia mala
# para clonar voz: XTTS reproduciria los artefactos del codec. Asi que de cada
# descarga se guardan dos copias, el opus ligero y este WAV.

URL_VALIDA = re.compile(
    r"^https?://(www\.|m\.|music\.)?(youtube\.com/(watch\?|shorts/|live/)|youtu\.be/)")


class Error(Exception):
    pass


def binario(raiz):
    p = Path(raiz) / "bin" / "yt-dlp"
    if p.is_file():
        return str(p)
    if (s := shutil.which("yt-dlp")):
        return s
    raise Error("falta yt-dlp")


def _correr(cmd, timeout):
    r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if r.returncode:
        raise Error(r.stderr.decode("utf-8", "replace").strip()[-300:] or "fallo")
    return r.stdout


def info(url, raiz):
    """Titulo y duracion, sin descargar nada."""
    if not URL_VALIDA.match(url):
        raise Error("no parece un enlace de YouTube")
    salida = _correr([binario(raiz), "--no-warnings", "--no-playlist",
                      "--skip-download", "--print-json", url], 90)
    d = json.loads(salida.decode("utf-8", "replace").splitlines()[0])
    return {"video_id": d.get("id", ""), "titulo": d.get("title", ""),
            "dur_s": float(d.get("duration") or 0)}


def maestro(opus):
    """El WAV de calidad que acompaña a un opus descargado, si existe."""
    p = Path(opus).with_suffix(".wav")
    return p if p.is_file() and p.stat().st_size > 44 else None


def descargar(url, destino, raiz):
    """Baja el mejor audio: opus mono para la web y WAV de 24 kHz para clonar."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.parent / f".{destino.stem}.bruto"
    for viejo in destino.parent.glob(f".{destino.stem}.bruto*"):
        viejo.unlink(missing_ok=True)

    _correr([binario(raiz), "--no-warnings", "--no-playlist", "-f", "bestaudio",
             "-o", f"{tmp}.%(ext)s", url], 1800)
    bajados = list(destino.parent.glob(f".{destino.stem}.bruto*"))
    if not bajados:
        raise Error("yt-dlp no dejo ningun fichero")
    bruto = bajados[0]
    try:
        parcial = destino.with_suffix(".part.opus")
        _correr(["ffmpeg", "-y", "-loglevel", "error", "-i", str(bruto),
                 "-c:a", "libopus", "-b:a", BITRATE, "-ac", "1",
                 str(parcial)], 1800)
        parcial.replace(destino)
        # el maestro para clonar: si falla, la descarga sigue siendo valida
        try:
            wav = destino.with_suffix(".part.wav")
            _correr(["ffmpeg", "-y", "-loglevel", "error", "-i", str(bruto),
                     "-ac", "1", "-ar", str(SR_MAESTRO), "-c:a", "pcm_s16le",
                     str(wav)], 1800)
            wav.replace(destino.with_suffix(".wav"))
        except Exception as e:  # noqa: BLE001
            print(f"[youtube] sin maestro wav para {destino.name}: {e}", flush=True)
    finally:
        bruto.unlink(missing_ok=True)
    return destino


def duracion(ruta):
    salida = _correr(["ffprobe", "-v", "error", "-show_entries",
                      "format=duration", "-of", "default=nw=1:nk=1", str(ruta)], 60)
    return float(salida.decode().strip() or 0)


def envolvente(ruta, dur_s):
    """La onda resumida en valores 0-255, como la de las oraciones."""
    n = min(PICOS_MAX, max(PICOS_MIN, int(dur_s * 4)))
    crudo = _correr(["ffmpeg", "-v", "error", "-i", str(ruta), "-ac", "1",
                     "-ar", str(SR_PICOS), "-f", "s16le", "pipe:1"], 900)
    x = array.array("h")
    x.frombytes(crudo[:len(crudo) // 2 * 2])
    if not x:
        return "", n
    picos = bytearray(n)
    paso = len(x) / n
    mayor = 1
    for i in range(n):
        a, b = int(i * paso), max(int(i * paso) + 1, int((i + 1) * paso))
        m = 0
        for v in x[a:b]:
            v = -v if v < 0 else v
            if v > m:
                m = v
        picos[i] = min(255, m >> 7)
        mayor = max(mayor, m)
    if mayor < 32768:                      # reescala para que se vea la onda
        f = 32767 / mayor
        for i in range(n):
            picos[i] = min(255, int(picos[i] * f))
    return base64.b64encode(bytes(picos)).decode(), n
