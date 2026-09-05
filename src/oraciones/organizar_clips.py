"""Deja los clips en clips/<speaker>/<lectura>/<oracion>.wav.

Usa enlaces duros: no duplica los 2,4 GB.
"""
import csv
import os
import shutil

from config import CLIPS, OUT, ROOT

DST = ROOT / "clips_oraciones"


def main():
    if DST.exists():
        shutil.rmtree(DST)
    filas = list(csv.DictReader(open(OUT / "oraciones.csv")))
    n = 0
    for r in filas:
        num = int(r["lectura"].split()[1])
        d = DST / r["Show"] / f"Lectura {num:03d}"
        d.mkdir(parents=True, exist_ok=True)
        os.link(CLIPS / r["Show"] / r["clip_name"],
                d / f"s{int(r['sent_idx']):03d}.wav")
        n += 1
    # el texto de cada oracion, junto a su audio
    import json
    lect = json.load(open(ROOT / "textos" / "lecturas_depuradas.json"))
    for sp in sorted({r["Show"] for r in filas}):
        for lec in sorted({r["lectura"] for r in filas if r["Show"] == sp}):
            num = int(lec.split()[1])
            mios = sorted((r for r in filas if r["Show"] == sp and r["lectura"] == lec),
                          key=lambda r: int(r["sent_idx"]))
            (DST / sp / f"Lectura {num:03d}" / "oraciones.txt").write_text(
                "\n".join(f"s{int(r['sent_idx']):03d}  ({r['dur_s']}s)  {r['texto_ref']}"
                          for r in mios) + "\n")
    print(f"{n} clips en {DST}")
    print(f"speakers: {len(os.listdir(DST))}")


if __name__ == "__main__":
    main()
