"""Recoge las anotaciones de la web y corta los WAV de 3 s.

La web solo guarda donde corta cada quien; el audio original se queda aqui,
asi que el corte de verdad se hace al terminar la ronda.

    .venv/bin/python src/web/exportar.py anotador.db
    .venv/bin/python src/web/exportar.py anotador.db --solo-csv

Salidas:
    outputs_web/anotaciones.csv   una fila por marca, con su texto y su tiempo
    outputs_web/index.csv         mismo formato que outputs/index.csv
    outputs_web/estado.csv        como quedo la revision de cada oracion
    clips_web/<hablante>/<hablante>_<epid>_w<id>.wav
"""
import argparse
import csv
import sqlite3
import sys
import wave
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ORACIONES = ROOT / "web" / "public" / "data" / "oracion.csv"
AUDIO = ROOT / "audios"
OUT = ROOT / "outputs_web"
CLIPS = ROOT / "clips_web"
SR = 16000
DUR = 3.0
CLASES = ["Prolongation", "Block", "SoundRep", "WordRep", "Interjection"]


def leer_tabla(ruta, tabla):
    cx = sqlite3.connect(ruta)
    cx.row_factory = sqlite3.Row
    return [dict(r) for r in cx.execute(f"SELECT * FROM {tabla}")]


def oraciones():
    d = {}
    with open(ORACIONES, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            d[(r["speaker"], int(r["lectura"]), int(r["sent_idx"]))] = r
    return d


def cortar(marcas, ora):
    """Un WAV de 3 s por marca, leyendo cada episodio una sola vez."""
    por_ep = defaultdict(list)
    for m in marcas:
        o = ora.get((m["speaker"], m["lectura"], m["sent_idx"]))
        if o and m.get("start_s") is not None:
            por_ep[(m["speaker"], o["ep_id"])].append((m, o))

    hechos, faltan = 0, []
    for (sp, ep), lote in sorted(por_ep.items()):
        src = AUDIO / sp / f"{ep}.wav"
        if not src.exists():
            faltan.append(str(src))
            continue
        with wave.open(str(src), "rb") as w:
            par = w.getparams()
            crudo = w.readframes(w.getnframes())
        ancho = par.sampwidth * par.nchannels
        total = len(crudo) // ancho
        (CLIPS / sp).mkdir(parents=True, exist_ok=True)
        for m, o in lote:
            base = int(o["start_sample"]) if o.get("start_sample") else \
                int(round(float(o["start_s"]) * SR))
            ini = base + int(round(float(m["start_s"]) * SR))
            n = int(round(DUR * SR))
            ini = max(0, min(ini, total - n)) if total >= n else 0
            trozo = crudo[ini * ancho:(ini + n) * ancho]
            dst = CLIPS / sp / f"{sp}_{ep}_w{m['id']}.wav"
            with wave.open(str(dst), "wb") as o2:
                o2.setparams(par)
                o2.writeframes(trozo)
            m["_clip"] = dst.name
            m["_ini"] = ini
            m["_fin"] = ini + n
            hechos += 1
        print(f"  {sp}/{ep}: {len(lote)} clips", flush=True)
    if faltan:
        print(f"[!] {len(faltan)} episodios sin WAV local; corre fetch_data.py")
    return hechos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base", nargs="?", default=str(ROOT / "web" / "anotador.db"),
                    help="SQLite del anotador")
    ap.add_argument("--solo-csv", action="store_true", help="no cortar audio")
    args = ap.parse_args()

    if not Path(args.base).is_file():
        sys.exit(f"no existe {args.base}")
    ora = oraciones()
    marcas = leer_tabla(args.base, "disfluencia")
    estados = leer_tabla(args.base, "estado")
    print(f"{len(marcas)} marcas y {len(estados)} oraciones revisadas")

    OUT.mkdir(exist_ok=True)
    if not args.solo_csv:
        print(f"cortando en {CLIPS}/")
        print(f"{cortar(marcas, ora)} clips escritos")

    with open(OUT / "anotaciones.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "speaker", "lectura", "sent_idx", "tipo", "origen",
                    "autor", "nota", "start_s_oracion", "stop_s_oracion",
                    "ep_id", "start_s_audio", "stop_s_audio", "clip", "texto"])
        for m in marcas:
            o = ora.get((m["speaker"], m["lectura"], m["sent_idx"]), {})
            base = float(o.get("start_s", 0) or 0)
            a = m.get("start_s")
            w.writerow([m["id"], m["speaker"], m["lectura"], m["sent_idx"],
                        m["tipo"], m["origen"], m.get("autor", ""), m.get("nota", ""),
                        a, m.get("stop_s"), o.get("ep_id", ""),
                        None if a is None else round(base + a, 3),
                        None if a is None else round(base + a + DUR, 3),
                        m.get("_clip", ""), o.get("texto", "")])

    # mismo formato que outputs/index.csv, para que encaje con el pipeline de 3 s
    por_clip = defaultdict(lambda: defaultdict(int))
    meta = {}
    for m in marcas:
        if "_clip" not in m:
            continue
        k = m["_clip"]
        por_clip[k][m["tipo"]] += 1
        meta[k] = m
    with open(OUT / "index.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sheet", "Show", "EpId", "clip_name", "label", "n_labels",
                    "Start", "Stop"] + CLASES)
        for k, cuenta in sorted(por_clip.items()):
            m = meta[k]
            o = ora[(m["speaker"], m["lectura"], m["sent_idx"])]
            ets = [c for c in CLASES if cuenta[c]]
            w.writerow(["web", m["speaker"], o["ep_id"], k,
                        ets[0] if len(ets) == 1 else "Multiple", len(ets),
                        m["_ini"], m["_fin"]] + [cuenta[c] for c in CLASES])

    with open(OUT / "estado.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["speaker", "lectura", "sent_idx", "estado", "autor", "nota",
                    "actualizado", "texto"])
        for e in estados:
            o = ora.get((e["speaker"], e["lectura"], e["sent_idx"]), {})
            w.writerow([e["speaker"], e["lectura"], e["sent_idx"], e["estado"],
                        e.get("autor", ""), e.get("nota", ""),
                        e.get("actualizado", ""), o.get("texto", "")])
    print(f"csv en {OUT}/")


if __name__ == "__main__":
    main()
