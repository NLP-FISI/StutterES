"""Genera los datos estaticos que consume la web.

La forma de onda de cada oracion se precalcula aqui para que el navegador no
tenga que decodificar audio.

Salidas:
  web/public/data/meta.json          hablantes y lecturas
  web/public/data/<SP>/<NNN>.json    oraciones, picos, clips de 3 s
  web/public/data/oracion.csv        la referencia de cada oracion
  web/public/data/siembra.csv        las disfluencias que ya se conocen
"""
import base64
import csv
import json
import wave
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SALIDA = ROOT / "web" / "public" / "data"
SR = 16000
PICOS = 400          # muestras de la forma de onda por oracion
CLASES = ["Prolongation", "Block", "SoundRep", "WordRep", "Interjection",
          "NoStutteredWords"]
OTRAS = ["Unsure", "PoorAudioQuality", "DifficultToUnderstand",
         "NaturalPause", "Music", "NoSpeech"]
DUR = 3.0


def ventana(ini, total):
    total = total or DUR
    if total <= DUR:
        return 0.0, round(total, 3)
    a = min(max(0.0, ini), total - DUR)
    return round(a, 3), round(a + DUR, 3)


def leer(p):
    with wave.open(str(p), "rb") as w:
        n = w.getnframes()
        x = np.frombuffer(w.readframes(n), dtype=np.int16)
        if w.getnchannels() > 1:
            x = x.reshape(-1, w.getnchannels())[:, 0]
    return x


def envolvente(x):
    """La oracion resumida en PICOS valores 0-255."""
    if x.size == 0:
        return ""
    n = PICOS
    bordes = np.linspace(0, x.size, n + 1).astype(int)
    v = np.zeros(n, dtype=np.float64)
    a = np.abs(x.astype(np.float64))
    for i in range(n):
        s, e = bordes[i], max(bordes[i] + 1, bordes[i + 1])
        v[i] = a[s:e].max() if s < a.size else 0
    m = v.max()
    v = (v / m * 255) if m > 0 else v
    return base64.b64encode(v.astype(np.uint8).tobytes()).decode()


def main():
    ora = pd.read_csv(ROOT / "outputs_oraciones" / "oraciones.csv")
    an = pd.read_csv(ROOT / "outputs" / "index.csv").drop_duplicates("clip_name")
    textos = json.load(open(ROOT / "textos" / "lecturas_depuradas.json"))
    refs = {int(k.split()[1]): v["oraciones"] for k, v in textos.items()}
    por_ep = {k: g for k, g in an.groupby(["Show", "EpId"])}

    SALIDA.mkdir(parents=True, exist_ok=True)
    siembra, oraciones_csv = [], []
    meta = {"speakers": [], "clases": CLASES, "otras": OTRAS, "dur_marca": DUR}

    for sp in sorted(ora.Show.unique()):
        (SALIDA / sp).mkdir(exist_ok=True)
        lecturas = []
        for lec, g in sorted(ora[ora.Show == sp].groupby("lectura"),
                             key=lambda kv: int(kv[0].split()[1])):
            num = int(lec.split()[1])
            epid = g.EpId.iloc[0]
            audio = leer(ROOT / "audios" / sp / f"{epid}.wav")
            filas = {int(r.sent_idx): r for r in g.itertuples()}
            clips_ep = por_ep.get((sp, epid))

            oraciones = []
            for i, texto in enumerate(refs[num]):
                r = filas.get(i)
                o = {"i": i, "txt": texto}
                if r is None:
                    oraciones.append(o)
                    continue
                o.update({"a": round(r.start_s, 3), "b": round(r.stop_s, 3),
                          "dur": round(r.dur_s, 3),
                          "asr": r.texto_asr if isinstance(r.texto_asr, str) else "",
                          "pk": envolvente(audio[int(r.start_sample):int(r.stop_sample)])})
                cl = []
                if clips_ep is not None:
                    medio = (clips_ep.Start + clips_ep.Stop) / 2
                    dentro = clips_ep[(medio >= r.start_sample) & (medio < r.stop_sample)]
                    for c in dentro.sort_values("Start").itertuples():
                        rel = c.Start / SR - r.start_s
                        et = [k for k in CLASES if getattr(c, k, 0)]
                        cl.append({"id": int(c.ClipId),
                                   "a": round(rel, 3),
                                   "b": round(c.Stop / SR - r.start_s, 3),
                                   "desc": bool(c.descartada), "et": et,
                                   "otras": [k for k in OTRAS if getattr(c, k, 0)]})
                        for t in et:
                            if t == "NoStutteredWords":
                                continue
                            x, y = ventana(rel, r.dur_s)
                            siembra.append([sp, num, i, t, x, y, "auto_3s", int(c.ClipId)])
                o["c3"] = cl
                oraciones.append(o)
                oraciones_csv.append([sp, num, i, epid, int(r.start_sample),
                                      round(r.start_s, 3), round(r.stop_s, 3),
                                      round(r.dur_s, 3), texto])

            (SALIDA / sp / f"{num:03d}.json").write_text(json.dumps(
                {"sp": sp, "num": num, "nombre": lec, "epid": epid,
                 "ora": oraciones},
                ensure_ascii=False, separators=(",", ":")))
            lecturas.append({"num": num, "nombre": lec, "n": len(refs[num]),
                             "audio": len(filas)})
        meta["speakers"].append({"id": sp, "lecturas": lecturas,
                                 "n_oraciones": sum(l["n"] for l in lecturas),
                                 "n_audio": sum(l["audio"] for l in lecturas)})
        print(f"  {sp}: {len(lecturas)} lecturas", flush=True)

    (SALIDA / "meta.json").write_text(json.dumps(meta, ensure_ascii=False,
                                                 separators=(",", ":")))
    with open(SALIDA / "siembra.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["speaker", "lectura", "sent_idx", "tipo", "start_s",
                    "stop_s", "origen", "clip3s"])
        w.writerows(siembra)
    with open(SALIDA / "oracion.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["speaker", "lectura", "sent_idx", "ep_id", "start_sample",
                    "start_s", "stop_s", "dur_s", "texto"])
        w.writerows(oraciones_csv)
    tam = sum(p.stat().st_size for p in SALIDA.rglob("*"))
    print(f"{len(siembra)} disfluencias sembradas · {tam/1e6:.1f} MB en {SALIDA}")


if __name__ == "__main__":
    main()
