"""Rellena los trozos de audio que la pasada completa del ASR se salto.

Se localizan por energia y se re-transcriben aislados. Se itera porque
rellenar un hueco puede dejar otro mas pequeño al lado.
"""
import json
import shutil

import numpy as np
import pandas as pd
import soundfile as sf

from config import AUDIO, HILOS, INF, MODELO_ASR, OUT, SPEAKERS, SR

PAD = 0.3
MIN_GAP = 3.0
FRAC_HABLA = 0.30
ITER = 4


def rms(x, win=1600):       # ventanas de 100 ms
    n = len(x) // win * win
    return np.sqrt((x[:n].reshape(-1, win) ** 2).mean(1) + 1e-12) if n else \
        np.array([1e-9])


def huecos(d, x):
    ws = sorted([w for s in d["segmentos"] for w in s["words"]
                 if w["s"] is not None], key=lambda w: w["s"])
    if len(ws) < 2:
        return [(0.0, d["duracion"])]
    e = rms(x)
    idx = np.concatenate([np.arange(int(w["s"] * 10), int(w["e"] * 10))
                          for w in ws])
    idx = idx[idx < len(e)]
    ref = float(np.median(e[idx])) if len(idx) else 1e-9
    bordes = ([(0.0, ws[0]["s"])] +
              [(ws[i]["e"], ws[i + 1]["s"]) for i in range(len(ws) - 1)] +
              [(ws[-1]["e"], d["duracion"])])
    out = []
    for a, b in bordes:
        if b - a < MIN_GAP:
            continue
        s0, s1 = int(a * 10), min(int(b * 10), len(e))
        if s1 > s0 and (e[s0:s1] > .25 * ref).mean() > FRAC_HABLA:
            out.append((float(a), float(b)))
    return out


def main():
    from faster_whisper import WhisperModel
    m = WhisperModel(MODELO_ASR, device="cpu", compute_type="int8",
                     cpu_threads=HILOS)
    src, dst = OUT / "asr", OUT / "asr_reparado"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)

    reg = []
    for it in range(1, ITER + 1):
        n_ep = n_pal = 0
        for sp in SPEAKERS:
            for p in sorted((dst / sp).glob("*.json")):
                d = json.loads(p.read_text())
                x, _ = sf.read(AUDIO / sp / f"{p.stem}.wav", dtype="float32")
                hs = huecos(d, x)
                if not hs:
                    continue
                nuevo = False
                for a, b in hs:
                    i0 = max(0, int((a - PAD) * SR))
                    i1 = min(len(x), int((b + PAD) * SR))
                    if i1 - i0 < int(0.5 * SR):
                        continue
                    segs, _ = m.transcribe(
                        x[i0:i1], language="es", beam_size=5,
                        word_timestamps=True, vad_filter=False,
                        condition_on_previous_text=False)
                    off = i0 / SR
                    for s in segs:
                        ws = [{"w": w.word, "s": w.start + off,
                               "e": w.end + off, "p": round(w.probability, 3)}
                              for w in (s.words or []) if w.start is not None]
                        if not ws:
                            continue
                        d["segmentos"].append({
                            "start": s.start + off, "end": s.end + off,
                            "text": s.text, "words": ws, "rescatado": True})
                        n_pal += len(ws)
                        nuevo = True
                        reg.append({"iter": it, "Show": sp, "EpId": p.stem,
                                    "ini": round(a, 2), "fin": round(b, 2),
                                    "n_palabras": len(ws),
                                    "texto": s.text.strip()})
                if nuevo:
                    d["segmentos"].sort(key=lambda s: s["start"])
                    d["texto"] = " ".join(s["text"].strip()
                                          for s in d["segmentos"]).strip()
                    d["n_palabras"] = len(d["texto"].split())
                    p.write_text(json.dumps(d, ensure_ascii=False))
                    n_ep += 1
        print(f"[iter {it}] audios reparados: {n_ep} | palabras: {n_pal}",
              flush=True)
        if n_ep == 0:
            break

    pd.DataFrame(reg).to_csv(INF / "reparaciones_asr.csv", index=False)
    print(f"total de trozos rescatados: {len(reg)}")


if __name__ == "__main__":
    main()
