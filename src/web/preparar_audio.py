"""Convierte los 500 WAV completos a audio comprimido para servirlos online.

El corte final NUNCA sale de aqui: se hace con los WAV originales en
src/web/exportar.py. Esta copia es solo para que la gente escuche por la web,
asi que se puede comprimir fuerte sin perder precision en el dataset.

    .venv/bin/python src/web/preparar_audio.py              # opus 24k, ~230 MB
    .venv/bin/python src/web/preparar_audio.py --formato mp3 # ~450 MB, mas compatible

Salida: web_audio/<hablante>/<epid>.<ext>, la misma ruta que espera la web.
"""
import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIO = ROOT / "audios"
DST = ROOT / "web_audio"
CODEC = {"opus": (["-c:a", "libopus", "-b:a", "24k"], "opus"),
         "mp3": (["-c:a", "libmp3lame", "-b:a", "48k"], "mp3")}


def convertir(args):
    src, dst, flags = args
    if dst.exists() and dst.stat().st_size > 1024:
        return "skip"
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f".{dst.stem}.part{dst.suffix}")
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
                        *flags, "-ac", "1", str(tmp)], capture_output=True)
    if r.returncode or not tmp.exists():
        return f"FAIL {src.name}: {r.stderr.decode()[:120]}"
    tmp.replace(dst)
    return "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--formato", choices=list(CODEC), default="opus")
    ap.add_argument("--hilos", type=int, default=8)
    a = ap.parse_args()
    if subprocess.run(["which", "ffmpeg"], capture_output=True).returncode:
        sys.exit("hace falta ffmpeg")

    flags, ext = CODEC[a.formato]
    tareas = [(p, DST / p.parent.name / f"{p.stem}.{ext}", flags)
              for p in sorted(AUDIO.glob("*/*.wav"))]
    if not tareas:
        sys.exit(f"no hay WAV en {AUDIO}; corre src/oraciones/fetch_data.py")
    print(f"{len(tareas)} audios -> {a.formato}")

    res = {}
    with ThreadPoolExecutor(max_workers=a.hilos) as ex:
        for i, r in enumerate(ex.map(convertir, tareas), 1):
            k = "FAIL" if r.startswith("FAIL") else r
            res[k] = res.get(k, 0) + 1
            if k == "FAIL":
                print(" ", r)
            if i % 50 == 0 or i == len(tareas):
                print(f"  {i}/{len(tareas)} {res}", flush=True)

    tam = sum(p.stat().st_size for p in DST.rglob(f"*.{ext}"))
    print(f"FIN {res} · {tam/1e6:.0f} MB en {DST}")


if __name__ == "__main__":
    main()
