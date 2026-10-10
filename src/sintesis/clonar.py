# -*- coding: utf-8 -*-
"""Clona una voz con XTTS-v2 y le hace leer un texto.

    python src/sintesis/clonar.py --ref recortes/mi_audio/0001_recorte.wav \\
        --texto "Un sismo de magnitud cuatro se reporto en Piura." \\
        --salida outputs_sintesis/

La referencia sale del troceador de la web: cada recorte se guarda en WAV de
24 kHz justo para esto. XTTS quiere entre 6 y 30 segundos de voz limpia; se
pueden pasar varias referencias del mismo hablante y promedia el timbre.

Licencia: XTTS-v2 va bajo la Coqui Public Model License, que es solo para uso
no comercial. El paquete pide aceptarla; aqui no se acepta por ti, hay que
pasar --acepto-cpml o poner COQUI_TOS_AGREED=1.

En CPU tarda: cuenta unos pocos segundos de proceso por segundo de audio.
"""
import argparse
import os
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
MODELO = "tts_models/multilingual/multi-dataset/xtts_v2"
REF_MIN, REF_MAX = 6.0, 30.0


def duracion(p):
    import soundfile as sf
    try:
        i = sf.info(str(p))
        return i.frames / float(i.samplerate)
    except Exception:  # noqa: BLE001
        return 0.0


def refs(valores):
    """Acepta ficheros y carpetas; devuelve la lista de WAV a usar."""
    out = []
    for v in valores:
        p = Path(v)
        if p.is_dir():
            out += sorted([q for q in p.rglob("*") if q.suffix.lower() in (".wav", ".flac")])
        elif p.is_file():
            out.append(p)
        else:
            sys.exit(f"no existe: {v}")
    if not out:
        sys.exit("ninguna referencia valida")
    return out


def avisos(rs):
    total = 0.0
    for p in rs:
        d = duracion(p)
        total += d
        if p.suffix.lower() not in (".wav", ".flac"):
            print(f"  ojo: {p.name} no es WAV; el codec se oye en la voz clonada")
    print(f"  {len(rs)} referencia(s), {total:.1f} s en total")
    if total < REF_MIN:
        print(f"  ojo: menos de {REF_MIN:g} s de referencia; el timbre saldra pobre")
    if total > REF_MAX * 2:
        print(f"  ojo: mas de {REF_MAX*2:g} s; XTTS no aprovecha tanto y tarda mas")


def frases(a):
    if a.texto:
        return [a.texto]
    p = Path(a.fichero)
    if not p.is_file():
        sys.exit(f"no existe: {a.fichero}")
    return [l.strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def main():
    ap = argparse.ArgumentParser(description="Clonar voz con XTTS-v2")
    ap.add_argument("--ref", nargs="+", required=True,
                    help="WAV de referencia, o carpeta con varios")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--texto", help="una sola frase")
    g.add_argument("--fichero", help="fichero con una frase por linea")
    ap.add_argument("--salida", default=str(RAIZ/"outputs_sintesis"))
    ap.add_argument("--idioma", default="es")
    ap.add_argument("--hilos", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--velocidad", type=float, default=1.0)
    ap.add_argument("--prefijo", default="voz")
    ap.add_argument("--acepto-cpml", action="store_true",
                    help="acepta la Coqui Public Model License (no comercial)")
    a = ap.parse_args()

    if not (a.acepto_cpml or os.environ.get("COQUI_TOS_AGREED") == "1"):
        sys.exit("XTTS-v2 va bajo la Coqui Public Model License, solo uso no\n"
                 "comercial. Si la aceptas, vuelve a lanzarlo con --acepto-cpml.")
    os.environ["COQUI_TOS_AGREED"] = "1"

    rs = refs(a.ref)
    avisos(rs)
    textos = frases(a)
    sal = Path(a.salida); sal.mkdir(parents=True, exist_ok=True)

    import torch
    torch.set_num_threads(max(1, a.hilos))

    try:
        from TTS.api import TTS
    except ImportError as e:
        sys.exit(f"no se puede importar TTS: {e}\n\n"
                 "Monta el entorno aparte tal cual (el orden importa):\n"
                 "  python3 -m venv .venv-tts\n"
                 "  .venv-tts/bin/pip install 'coqui-tts[codec]' 'transformers<5'\n"
                 "  .venv-tts/bin/pip install torch torchaudio "
                 "--index-url https://download.pytorch.org/whl/cpu\n\n"
                 "coqui-tts 0.27 usa isin_mps_friendly, que desaparecio en\n"
                 "transformers 5.x, y desde torch 2.9 hace falta torchcodec\n"
                 "para leer audio: de ahi el extra [codec].")

    print(f"  cargando {MODELO} (la primera vez baja ~1,8 GB)...")
    t0 = time.time()
    tts = TTS(MODELO).to("cpu")
    print(f"  modelo listo en {time.time()-t0:.0f} s")

    for i, txt in enumerate(textos, 1):
        dst = sal / f"{a.prefijo}_{i:03d}.wav"
        t0 = time.time()
        tts.tts_to_file(text=txt, file_path=str(dst),
                        speaker_wav=[str(p) for p in rs],
                        language=a.idioma, speed=a.velocidad)
        print(f"  [{i}/{len(textos)}] {dst.name}  {duracion(dst):.1f} s de audio "
              f"en {time.time()-t0:.0f} s  <- {txt[:60]}")
    print(f"listo: {len(textos)} ficheros en {sal}")


if __name__ == "__main__":
    main()
