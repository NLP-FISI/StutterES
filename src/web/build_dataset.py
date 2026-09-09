"""Construye src/web/dataset.json: todo lo que la web necesita, ya cruzado.

Cruza oraciones.csv (fronteras del clip de oracion) con index.csv (clips de 3 s
anotados) y con lecturas_depuradas.json (el texto completo de cada lectura, para
que la numeracion de oraciones no dependa de que ese hablante la leyera).
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SR = 16000
CLASES = ["Prolongation", "Block", "SoundRep", "WordRep", "Interjection",
          "NoStutteredWords"]
OTRAS = ["Unsure", "PoorAudioQuality", "DifficultToUnderstand",
         "NaturalPause", "Music", "NoSpeech"]
SALIDA = ROOT / "src" / "web" / "dataset.json"


def main():
    ora = pd.read_csv(ROOT / "outputs_oraciones" / "oraciones.csv")
    an = pd.read_csv(ROOT / "outputs" / "index.csv").drop_duplicates("clip_name")
    textos = json.load(open(ROOT / "textos" / "lecturas_depuradas.json"))

    por_ep = {k: g for k, g in an.groupby(["Show", "EpId"])}
    speakers = sorted(ora.Show.unique())

    # lectura -> lista de oraciones del texto (la referencia, comun a los 5)
    lecturas = {}
    for nombre, v in textos.items():
        lecturas[int(nombre.split()[1])] = v["oraciones"]

    datos = {sp: {} for sp in speakers}
    for (sp, lec), g in ora.groupby(["Show", "lectura"]):
        num = int(lec.split()[1])
        refs = lecturas[num]
        filas = {int(r.sent_idx): r for r in g.itertuples()}
        epid = g.EpId.iloc[0]
        clips_ep = por_ep.get((sp, epid))

        oraciones = []
        for i, texto in enumerate(refs):
            r = filas.get(i)
            o = {"idx": i, "texto": texto, "audio": None, "clips3s": [],
                 "agg": {c: 0 for c in CLASES + OTRAS}, "cobertura": 0.0}
            if r is None:
                oraciones.append(o)
                continue
            o["audio"] = f"Lectura {num:03d}/s{i:03d}.wav"
            o["start_s"], o["stop_s"], o["dur_s"] = r.start_s, r.stop_s, r.dur_s
            o["texto_asr"] = r.texto_asr if isinstance(r.texto_asr, str) else ""
            if clips_ep is not None:
                medio = (clips_ep.Start + clips_ep.Stop) / 2
                dentro = clips_ep[(medio >= r.start_sample) & (medio < r.stop_sample)]
                for c in dentro.sort_values("Start").itertuples():
                    o["clips3s"].append({
                        "id": int(c.ClipId),
                        "file": c.clip_name,
                        "rel_start": round(c.Start / SR - r.start_s, 3),
                        "rel_stop": round(c.Stop / SR - r.start_s, 3),
                        "descartada": bool(c.descartada),
                        "labels": [k for k in CLASES if getattr(c, k, 0)],
                        "otras": [k for k in OTRAS if getattr(c, k, 0)],
                    })
                for k in CLASES + OTRAS:
                    o["agg"][k] = int(dentro[k].sum()) if k in dentro else 0
                cubierto = 0
                fin = -1
                for s, e in sorted((max(r.start_sample, s), min(r.stop_sample, e))
                                   for s, e in zip(dentro.Start, dentro.Stop)):
                    s = max(s, fin)
                    cubierto += max(0, e - s)
                    fin = max(fin, e)
                o["cobertura"] = round(cubierto / max(r.stop_sample - r.start_sample, 1), 3)
            oraciones.append(o)

        datos[sp][str(num)] = {"lectura": lec, "epid": epid,
                               "n_oraciones": len(refs),
                               "n_con_audio": len(filas),
                               "oraciones": oraciones}

    salida = {"speakers": speakers, "clases": CLASES, "otras": OTRAS,
              "datos": datos}
    SALIDA.write_text(json.dumps(salida, ensure_ascii=False))
    print(f"{SALIDA}  ({SALIDA.stat().st_size/1e6:.1f} MB)")
    for sp in speakers:
        n = sum(len(l["oraciones"]) for l in datos[sp].values())
        print(f"  {sp}: {len(datos[sp])} lecturas, {n} oraciones")


if __name__ == "__main__":
    main()
