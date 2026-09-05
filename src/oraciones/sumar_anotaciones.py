"""Asigna cada clip de 3 s anotado a su oracion y suma las disfluencias.

Un clip pertenece a la oracion en la que cae su punto medio, asi cada clip
cuenta una sola vez. Las columnas de disfluencia se suman tal cual: el
numero dice en cuantos clips de esa oracion aparece cada tipo.

Salida: outputs_oraciones/oraciones_con_disfluencias.{csv,xlsx}
"""
import numpy as np
import pandas as pd

from config import OUT, ROOT, SR

ANOTACIONES = ROOT / "outputs" / "index.csv"
CLASES = ["Prolongation", "Block", "SoundRep", "WordRep", "Interjection",
          "NoStutteredWords"]
OTRAS = ["Unsure", "PoorAudioQuality", "DifficultToUnderstand",
         "NaturalPause", "Music", "NoSpeech"]


def main():
    ora = pd.read_csv(OUT / "oraciones.csv")
    an = pd.read_csv(ANOTACIONES).drop_duplicates("clip_name")
    cols = [c for c in CLASES + OTRAS if c in an.columns]

    por_ep = {k: g for k, g in an.groupby(["Show", "EpId"])}
    filas = []
    for r in ora.itertuples():
        g = por_ep.get((r.Show, r.EpId))
        rec = {"Show": r.Show, "lectura": r.lectura, "sent_idx": r.sent_idx,
               "clip_oracion": r.clip_name, "EpId": r.EpId,
               "start_s": r.start_s, "stop_s": r.stop_s, "dur_s": r.dur_s,
               "oracion": r.texto_ref}
        if g is None:
            rec.update({"n_clips_3s": 0, "clips_3s": "",
                        **{c: 0 for c in cols}, "cobertura": 0.0})
            filas.append(rec)
            continue
        medio = (g.Start + g.Stop) / 2
        dentro = g[(medio >= r.start_sample) & (medio < r.stop_sample)]
        # cuanto de la oracion cubren esos clips
        ov = np.clip(np.minimum(r.stop_sample, g.Stop)
                     - np.maximum(r.start_sample, g.Start), 0, None)
        iv = sorted((max(r.start_sample, s), min(r.stop_sample, e))
                    for s, e, o in zip(g.Start, g.Stop, ov) if o > 0)
        u, fin = 0, -1
        for s, e in iv:
            s = max(s, fin)
            u += max(0, e - s)
            fin = max(fin, e)
        rec.update({"n_clips_3s": len(dentro),
                    "clips_3s": ",".join(str(c) for c in sorted(dentro.ClipId)),
                    **{c: int(dentro[c].sum()) for c in cols},
                    "cobertura": round(u / max(r.stop_sample - r.start_sample, 1), 3)})
        filas.append(rec)

    df = pd.DataFrame(filas)
    orden = (["Show", "lectura", "sent_idx", "oracion", "n_clips_3s", "clips_3s"]
             + cols + ["cobertura", "clip_oracion", "EpId", "start_s", "stop_s",
                       "dur_s"])
    df = df[orden]
    df.to_csv(OUT / "oraciones_con_disfluencias.csv", index=False)
    df.to_excel(OUT / "oraciones_con_disfluencias.xlsx", index=False)

    con = df[df.n_clips_3s > 0]
    print(f"oraciones                 : {len(df)}")
    print(f"  con algun clip de 3 s   : {len(con)} ({len(con)/len(df):.0%})")
    print(f"  clips de 3 s asignados  : {int(df.n_clips_3s.sum())} de {len(an)}")
    print(f"  clips por oracion       : mediana {int(con.n_clips_3s.median())}, "
          f"max {int(df.n_clips_3s.max())}")
    print(f"  cobertura media         : {con.cobertura.mean():.0%}")
    print("\nsuma de disfluencias sobre las oraciones con anotacion:")
    for c in CLASES:
        n_ev = int(con[c].sum())
        n_or = int((con[c] > 0).sum())
        print(f"  {c:18} {n_ev:5d} clips marcados, en {n_or:4d} oraciones")


if __name__ == "__main__":
    main()
