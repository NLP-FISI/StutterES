"""Empareja cada audio con su lectura.

Cada speaker leyo las 100 una sola vez, asi que es una biyeccion: se
resuelve con el hungaro, no con el argmax de cada fila.
"""
import json

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from sklearn.feature_extraction.text import TfidfVectorizer

from config import ASR_DIR, INF, LECTURAS, OUT, SPEAKERS
from texto import norm_frase

R = []


def A(s=""):
    R.append(s)
    print(s)


def coseno(a, b, **kw):
    v = TfidfVectorizer(sublinear_tf=True, **kw).fit(list(a) + list(b))
    A_, B_ = v.transform(a), v.transform(b)
    A_ = A_.multiply(1 / (np.sqrt(A_.multiply(A_).sum(1)) + 1e-9))
    B_ = B_.multiply(1 / (np.sqrt(B_.multiply(B_).sum(1)) + 1e-9))
    return np.asarray((A_ @ B_.T).todense())


def main():
    lect = json.load(open(LECTURAS))
    nombres = [f"Lectura {i}" for i in range(1, 101)]
    txt_lect = [norm_frase(lect[n]["clean"]) for n in nombres]

    filas, resumen = [], []
    for sp in SPEAKERS:
        eps = sorted(p.stem for p in (ASR_DIR / sp).glob("*.json"))
        asr = [json.load(open(ASR_DIR / sp / f"{e}.json")) for e in eps]
        txt_asr = [norm_frase(a["texto"]) for a in asr]

        # caracteres: aguanta errores de ASR; palabras: aguanta reordenaciones
        s_char = coseno(txt_asr, txt_lect, analyzer="char_wb",
                        ngram_range=(3, 5), min_df=2)
        s_word = coseno(txt_asr, txt_lect, analyzer="word",
                        ngram_range=(1, 2), min_df=1)
        S = (s_char + s_word) / 2

        fi, fj = linear_sum_assignment(-S)
        argmax = S.argmax(1)
        for i, j in zip(fi, fj):
            orden = np.argsort(-S[i])
            filas.append({
                "Show": sp, "EpId": eps[i], "lectura": nombres[j],
                "lectura_n": j + 1,
                "score": round(float(S[i, j]), 4),
                "margen": round(float(S[i, orden[0]] - S[i, orden[1]]), 4),
                "rank_asignado": int(np.where(orden == j)[0][0]) + 1,
                "coincide_argmax": bool(argmax[i] == j),
                "n_palabras_asr": asr[i]["n_palabras"],
                "duracion": round(asr[i]["duracion"], 1)})
        n_ok = sum(1 for f in filas[-len(eps):] if f["coincide_argmax"])
        resumen.append(f"- {sp}: hungaro = argmax en {n_ok}/{len(eps)}")

    df = pd.DataFrame(filas)
    df["fecha"] = df.EpId.str.slice(0, 10)
    df = df.sort_values(["Show", "EpId"]).reset_index(drop=True)
    df.to_csv(OUT / "emparejamiento.csv", index=False)

    A("EMPAREJAMIENTO AUDIO <-> LECTURA")
    A("=" * 60)
    A("")
    A("Coseno TF-IDF (char 3-5 + palabra 1-2) entre la transcripcion y cada")
    A("lectura, resuelto con el algoritmo hungaro.")
    A("")
    A("\n".join(resumen))
    A("\nBIYECCION")
    for sp in SPEAKERS:
        s = df[df.Show == sp]
        estado = "OK" if s.lectura.nunique() == len(s) == 100 else "REVISAR"
        A(f"- {sp}: {s.lectura.nunique()}/100 lecturas distintas sobre "
          f"{len(s)} audios  {estado}")

    A("\nCONFIANZA")
    A(df.groupby("Show")[["score", "margen"]].agg(["min", "median"])
      .round(3).to_string())
    A(f"\n- asignaciones que no son el argmax: {int((~df.coincide_argmax).sum())}/{len(df)}")
    A(f"- margen < 0.05: {int((df.margen < 0.05).sum())}")
    A(f"- rank asignado maximo: {int(df.rank_asignado.max())}")

    A("\nVALIDACION EXTERNA: BLOQUES POR FECHA")
    A("El xlsx agrupa las lecturas en 10 'Dias' de 10. Si la sesion N es el")
    A("Dia N, cada bloque cronologico de 10 audios cae en una decena.")
    A("")
    ok = 0
    for sp in SPEAKERS:
        s = df[df.Show == sp].sort_values("EpId").reset_index(drop=True)
        s["bloque"] = s.index // 10
        for b, g in s.groupby("bloque"):
            dec = sorted({(n - 1) // 10 for n in g.lectura_n})
            ok += len(dec) == 1
    A(f"- bloques que caen en una sola decena: {ok}/50")

    A("\nPEORES 10 POR MARGEN")
    A(df.nsmallest(10, "margen")[
        ["Show", "EpId", "lectura", "score", "margen", "rank_asignado"]
    ].to_string(index=False))

    (INF / "emparejamiento.txt").write_text("\n".join(R) + "\n")


if __name__ == "__main__":
    main()
