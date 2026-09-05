"""Quita las oraciones que ningun speaker llego a leer.

La extraccion del PDF cuela anuncios, pie de pagina y enlaces a otros
articulos. Como cada lectura la leyeron los cinco speakers, basta con mirar
el audio: si una oracion no aparece en cuatro o mas de ellos, no es parte de
la lectura.

De paso deja el anclaje de cada pareja (audio, oracion), que es la medida de
cuanto de esa oracion aparece en la transcripcion.
"""
import json

import numpy as np
import pandas as pd
from rapidfuzz.distance import Levenshtein

from config import INF, LECTURAS, LECTURAS_DEP, OUT, SPEAKERS, ASR_DIR
from texto import tokens_asr, tokens_lectura

UMBRAL = 0.5      # anclaje por debajo del cual se da por no leida
MIN_FALLOS = 4    # en cuantos speakers tiene que faltar para descartarla


def anclaje_por_oracion(lect, emp):
    filas = []
    for r in emp.itertuples():
        oraciones = lect[r.lectura]["oraciones"]
        ref, sid = tokens_lectura(oraciones)
        sid = np.array(sid)
        d = json.loads((ASR_DIR / r.Show / f"{r.EpId}.json").read_text())
        asr = [p[0] for p in tokens_asr(d)]
        casan = [0] * len(oraciones)
        for op in Levenshtein.opcodes(ref, asr):
            if op.tag == "equal":
                for k in range(op.src_end - op.src_start):
                    casan[sid[op.src_start + k]] += 1
        for k, o in enumerate(oraciones):
            n = int((sid == k).sum())
            filas.append({"Show": r.Show, "EpId": r.EpId, "lectura": r.lectura,
                          "sent_idx": k, "n_ref": n,
                          "anclaje": casan[k] / n if n else 0.0, "texto": o})
    return pd.DataFrame(filas)


def main():
    lect = json.load(open(LECTURAS))
    emp = pd.read_csv(OUT / "emparejamiento.csv")

    a = anclaje_por_oracion(lect, emp)
    a.to_csv(INF / "anclaje_por_oracion.csv", index=False)

    piv = a.pivot_table(index=["lectura", "sent_idx"], columns="Show",
                        values="anclaje")
    piv["fallan"] = (piv[SPEAKERS] < UMBRAL).sum(axis=1)
    fuera = piv[piv.fallan >= MIN_FALLOS].reset_index()
    quitar = {(r.lectura, r.sent_idx) for r in fuera.itertuples()}

    nuevo = {}
    for nom, d in lect.items():
        ors = [(t, o) for k, (t, o) in
               enumerate(zip(d.get("tipos", [""] * len(d["oraciones"])),
                             d["oraciones"]))
               if (nom, k) not in quitar]
        nuevo[nom] = {**d, "oraciones": [o for _, o in ors],
                      "tipos": [t for t, _ in ors], "n_oraciones": len(ors)}
    LECTURAS_DEP.write_text(json.dumps(nuevo, ensure_ascii=False, indent=1))

    antes = sum(len(d["oraciones"]) for d in lect.values())
    ahora = sum(d["n_oraciones"] for d in nuevo.values())
    txt = ["ORACIONES QUE NADIE LEYO", "=" * 60, "",
           f"anclaje medio: {a.anclaje.mean():.3f}",
           f"oraciones antes : {antes}",
           f"descartadas     : {antes - ahora}",
           f"oraciones ahora : {ahora}", "", "DESCARTADAS", "-" * 60]
    for x in fuera.sort_values(["lectura", "sent_idx"]).itertuples():
        t = a[(a.lectura == x.lectura) & (a.sent_idx == x.sent_idx)].texto.iloc[0]
        txt.append(f"{x.lectura} s{x.sent_idx:03d}  {t[:100]}")
    (INF / "depuracion.txt").write_text("\n".join(txt) + "\n")
    print("\n".join(txt[3:7]))


if __name__ == "__main__":
    main()
