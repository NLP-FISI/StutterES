"""Transcribe los audios completos con faster-whisper (CPU, int8).
"""
import argparse
import json
import time
import wave

from config import AUDIO, HILOS, MODELO_ASR, OUT, SPEAKERS


def duracion(p):
    with wave.open(str(p)) as w:
        return w.getnframes() / w.getframerate()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=MODELO_ASR)
    ap.add_argument("--threads", type=int, default=HILOS)
    ap.add_argument("--beam", type=int, default=5)
    a = ap.parse_args()

    from faster_whisper import WhisperModel
    print(f"[asr] cargando {a.model} (int8, {a.threads} hilos)", flush=True)
    model = WhisperModel(a.model, device="cpu", compute_type="int8",
                         cpu_threads=a.threads)

    dst_root = OUT / "asr"
    tareas = [(sp, p) for sp in SPEAKERS
              for p in sorted((AUDIO / sp).glob("*.wav"))]
    print(f"[asr] {len(tareas)} audios", flush=True)

    t_audio = t_proc = 0.0
    for i, (sp, src) in enumerate(tareas, 1):
        dst = dst_root / sp / f"{src.stem}.json"
        if dst.exists() and dst.stat().st_size > 100:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        t1 = time.time()
        # sin VAD y sin condition_on_previous_text: el habla disfluente
        # (bloqueos mudos, repeticiones) los rompe
        segs, _ = model.transcribe(
            str(src), language="es", beam_size=a.beam, word_timestamps=True,
            vad_filter=False, condition_on_previous_text=False,
            temperature=[0.0, 0.2, 0.4])
        d = {"speaker": sp, "ep": src.stem, "modelo": a.model,
             "duracion": duracion(src), "segmentos": []}
        for s in segs:
            d["segmentos"].append({
                "start": s.start, "end": s.end, "text": s.text,
                "words": [{"w": w.word, "s": w.start, "e": w.end,
                           "p": round(w.probability, 3)}
                          for w in (s.words or [])]})
        d["texto"] = " ".join(s["text"].strip() for s in d["segmentos"]).strip()
        d["n_palabras"] = len(d["texto"].split())
        tmp = dst.with_suffix(".part")
        tmp.write_text(json.dumps(d, ensure_ascii=False))
        tmp.replace(dst)

        el = time.time() - t1
        t_audio += d["duracion"]
        t_proc += el
        if i % 5 == 0 or i == len(tareas):
            queda = (len(tareas) - i) * (t_proc / i)
            print(f"  {i}/{len(tareas)} {sp}/{src.stem} {el:5.1f}s "
                  f"| x{t_audio / t_proc:.2f} tiempo real "
                  f"| faltan ~{queda / 60:.0f} min", flush=True)
    print(f"[asr] FIN {t_audio / 60:.0f} min de audio en {t_proc / 60:.0f} min",
          flush=True)


if __name__ == "__main__":
    main()
