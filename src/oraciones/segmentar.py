"""Corta cada audio en clips de una oracion."""
import json
import sys

import numpy as np
import pandas as pd
import soundfile as sf
from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

from config import AUDIO, ASR_DIR, CLIPS, LECTURAS_DEP, OUT, SR
from texto import tokens_asr, tokens_lectura

PAD = 0.10          # margen minimo a cada lado, en segundos
MAX_PAD = 0.35
GAP_MAX = 2.0       # hueco maximo para unir dos oraciones por el silencio
MIN_ANCLAJE = 0.50    # recall: palabras de la oracion que casan
MIN_PRECISION = 0.60  # de las palabras del ASR en el tramo, cuantas son ancla
MIN_ANCLAS = 2


def dueños(ref, asr, sid, n_or):
    """A que oracion pertenece cada palabra del ASR (-1 si no se sabe).

    Se usa el alineamiento entero, no solo las anclas: si no, una palabra
    mal transcrita o dicha tras un bloqueo se queda fuera del clip.
    """
    d = np.full(len(asr), -1)
    for op in Levenshtein.opcodes(ref, asr):
        if op.tag in ("equal", "replace"):
            n_src = op.src_end - op.src_start
            n_dst = op.dest_end - op.dest_start
            for k in range(n_dst):
                j = op.src_start + min(n_src - 1, k * n_src // max(n_dst, 1))
                d[op.dest_start + k] = sid[j]
    # repeticiones y muletillas van con su vecina
    idx = np.where(d >= 0)[0]
    if len(idx):
        for i in np.where(d < 0)[0]:
            d[i] = d[idx[np.argmin(np.abs(idx - i))]]
    return d


def anclas(ref, asr, sid, n_or, sim_min=80):
    """Indices del ASR que casan con cada oracion.

    Cuentan tambien las sustituciones muy parecidas ("solitos"/"solito"):
    son flexion o error del ASR, no otra palabra.
    """
    out = [[] for _ in range(n_or)]
    for op in Levenshtein.opcodes(ref, asr):
        if op.tag == "equal":
            for k in range(op.src_end - op.src_start):
                out[sid[op.src_start + k]].append(op.dest_start + k)
        elif op.tag == "replace":
            n_src = op.src_end - op.src_start
            n_dst = op.dest_end - op.dest_start
            for k in range(min(n_src, n_dst)):
                a, b = ref[op.src_start + k], asr[op.dest_start + k]
                if fuzz.ratio(a, b) >= sim_min:
                    out[sid[op.src_start + k]].append(op.dest_start + k)
    for lst in out:
        lst.sort()
    return out


def _rms(x, win=400):
    n = len(x) // win * win
    if n == 0:
        return np.array([]), win
    return np.sqrt((x[:n].reshape(-1, win) ** 2).mean(1) + 1e-12), win


def corte_en_silencio(x, t_fin, t_ini):
    a, b = int(t_fin * SR), int(t_ini * SR)
    if b - a < int(0.06 * SR):
        return (a + b) // 2
    e, win = _rms(x[a:b])
    if len(e) == 0:
        return (a + b) // 2
    return a + int((np.argmin(e) + 0.5) * win)


def procesar(sp, ep, lectura, lecturas, cortar=True):
    d = json.load(open(ASR_DIR / sp / f"{ep}.json"))
    oraciones = lecturas[lectura]["oraciones"]
    ref, sid = tokens_lectura(oraciones)
    sid = np.array(sid)
    pal = tokens_asr(d)
    if not pal or not ref:
        return [], 0, len(oraciones)
    asr = [p[0] for p in pal]
    ini = np.array([p[1] for p in pal])
    fin = np.array([p[2] for p in pal])

    anc = anclas(ref, asr, sid, len(oraciones))
    duen = dueños(ref, asr, sid, len(oraciones))
    x, sr = sf.read(AUDIO / sp / f"{ep}.wav", dtype="float32")
    assert sr == SR, f"{sp}/{ep}: sr={sr}"

    tramos, fuera = [], 0
    for k, idx in enumerate(anc):
        n_ref = int((sid == k).sum())
        minimo = 1 if n_ref <= 3 else MIN_ANCLAS
        if n_ref == 0 or len(idx) < minimo:
            fuera += 1
            continue
        recall = len(idx) / n_ref
        # la precision salva los casos en que la referencia es un titular
        # largo del que solo se leyo una parte y el recall se hunde
        precision = len(idx) / max(idx[-1] - idx[0] + 1, 1)
        if recall < MIN_ANCLAJE and not (precision >= MIN_PRECISION
                                         and len(idx) >= 3):
            fuera += 1
            continue
        mios = np.where(duen == k)[0]
        i0 = min(idx[0], mios[0]) if len(mios) else idx[0]
        i1 = max(idx[-1], mios[-1]) if len(mios) else idx[-1]
        tramos.append({"k": k, "t0": float(ini[i0]), "t1": float(fin[i1]),
                       "n_ref": n_ref, "anclaje": recall,
                       "precision": precision, "i0": i0, "i1": i1})
    tramos.sort(key=lambda t: t["t0"])

    # sobra el tramo que otro se traga entero: alineamiento cruzado
    limpio, ultimo_fin = [], -1.0
    for t in tramos:
        if t["t1"] > ultimo_fin:
            limpio.append(t)
            ultimo_fin = t["t1"]
        else:
            fuera += 1
    tramos = limpio

    for i, t in enumerate(tramos):
        prev = tramos[i - 1] if i else None
        nxt = tramos[i + 1] if i + 1 < len(tramos) else None
        if prev and t["t0"] - prev["t1"] <= GAP_MAX:
            a = corte_en_silencio(x, prev["t1"], t["t0"])
        else:
            a = int((t["t0"] - MAX_PAD) * SR)
        if nxt and nxt["t0"] - t["t1"] <= GAP_MAX:
            b = corte_en_silencio(x, t["t1"], nxt["t0"])
        else:
            b = int((t["t1"] + MAX_PAD) * SR)
        # el tope solo aplica si hay hueco grande: con las frases pegadas el
        # corte va al silencio y no se recorta
        pegado_izq = prev and t["t0"] - prev["t1"] <= GAP_MAX
        pegado_der = nxt and nxt["t0"] - t["t1"] <= GAP_MAX
        if not pegado_izq:
            a = int(max(a, (t["t0"] - MAX_PAD) * SR))
        if not pegado_der:
            b = int(min(b, (t["t1"] + MAX_PAD) * SR))
        a = int(min(a, (t["t0"] - PAD) * SR))
        b = int(max(b, (t["t1"] + PAD) * SR))
        t["a"], t["b"] = max(0, a), min(len(x), b)

    for i in range(1, len(tramos)):
        if tramos[i]["a"] < tramos[i - 1]["b"]:
            m = (tramos[i]["a"] + tramos[i - 1]["b"]) // 2
            tramos[i - 1]["b"] = tramos[i]["a"] = m

    filas = []
    for t in tramos:
        k, dur = t["k"], (t["b"] - t["a"]) / SR
        dentro = (ini >= t["a"] / SR) & (ini < t["b"] / SR)
        n_asr = int(dentro.sum())
        texto_asr = " ".join(asr[j] for j in np.where(dentro)[0])
        name = f"{sp}_{ep}_s{k:03d}.wav"
        if cortar:
            (CLIPS / sp).mkdir(parents=True, exist_ok=True)
            sf.write(CLIPS / sp / name, x[t["a"]:t["b"]], SR)
        filas.append({
            "Show": sp, "EpId": ep, "lectura": lectura, "sent_idx": k,
            "clip_name": name,
            "start_sample": int(t["a"]), "stop_sample": int(t["b"]),
            "start_s": round(t["a"] / SR, 3), "stop_s": round(t["b"] / SR, 3),
            "dur_s": round(dur, 3),
            "n_palabras_ref": t["n_ref"], "n_palabras_asr": n_asr,
            "anclaje": round(t["anclaje"], 3),
            "precision": round(t["precision"], 3),
            "pal_por_seg": round(n_asr / max(dur, 1e-6), 2),
            "texto_ref": oraciones[k],
            "texto_asr": texto_asr})
    return filas, len(tramos), fuera


def main():
    cortar = "--no-cut" not in sys.argv
    lecturas = json.load(open(LECTURAS_DEP))
    emp = pd.read_csv(OUT / "emparejamiento.csv")
    filas, acep, fuera = [], 0, 0
    for i, r in enumerate(emp.itertuples(), 1):
        try:
            f, a, x = procesar(r.Show, r.EpId, r.lectura, lecturas, cortar)
            filas += f
            acep += a
            fuera += x
        except Exception as e:
            print(f"  [!] {r.Show}/{r.EpId}: {e!r}", flush=True)
        if i % 100 == 0 or i == len(emp):
            print(f"  {i}/{len(emp)} audios -> {len(filas)} oraciones", flush=True)

    df = pd.DataFrame(filas)
    df.to_csv(OUT / "oraciones.csv", index=False)
    total = sum(lecturas[r.lectura]["n_oraciones"] for r in emp.itertuples())
    print(f"\noraciones disponibles : {total}")
    print(f"ancladas en el audio  : {acep} ({acep / total:.1%})")
    print(f"sin anclaje suficiente: {fuera}")
    print(df.groupby("Show").agg(
        clips=("dur_s", "size"), dur_media=("dur_s", "mean"),
        dur_max=("dur_s", "max"), anclaje=("anclaje", "mean"),
        pal_s=("pal_por_seg", "mean")).round(2).to_string())
    print("\nduraciones (s):")
    print(df.dur_s.describe(percentiles=[.01, .05, .5, .95, .99]).round(2).to_string())


if __name__ == "__main__":
    main()
