import numpy as np
import pandas as pd

from config import OUT_DIR, DISFLUENCIES, SPLIT_RATIOS, SEED


def reparte(n, ratios):
    """Reparto por resto mayor. Con 3 clips o más, val y test no pueden
    quedarse vacíos: se les cede uno de train."""
    nombres = list(ratios)
    exactos = np.array([n * ratios[s] for s in nombres])
    base = np.floor(exactos).astype(int)
    for i in np.argsort(-(exactos - base))[: n - base.sum()]:
        base[i] += 1
    cuentas = dict(zip(nombres, base))

    if n >= 3:
        for s in ("val", "test"):
            if cuentas[s] == 0 and cuentas["train"] > 1:
                cuentas[s] += 1
                cuentas["train"] -= 1
    return cuentas


def main():
    df = pd.read_csv(OUT_DIR / "index.csv")
    df = df[~df.descartada].drop_duplicates("clip_name").reset_index(drop=True)
    print(f"[split] {len(df)} clips con alguna de las {len(DISFLUENCIES)} clases")

    rng = np.random.default_rng(SEED)
    asignacion = {}
    for _, grupo in df.groupby(["Show", "label"], sort=True):
        idx = grupo.index.to_numpy().copy()
        rng.shuffle(idx)
        pos = 0
        for split, k in reparte(len(idx), SPLIT_RATIOS).items():
            for i in idx[pos:pos + k]:
                asignacion[i] = split
            pos += k

    df["split"] = pd.Series(asignacion)
    assert df.split.notna().all(), "quedaron clips sin asignar"

    df.to_csv(OUT_DIR / "split.csv", index=False)
    for s in SPLIT_RATIOS:
        sub = df[df.split == s]
        sub.to_csv(OUT_DIR / f"{s}.csv", index=False)
        print(f"[split] {s:5s} {len(sub):5d}  ({len(sub) / len(df):.1%})")


if __name__ == "__main__":
    main()
