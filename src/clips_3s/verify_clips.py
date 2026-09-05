import collections
import wave

import pandas as pd

from config import CLIPS_DIR, OUT_DIR


def main():
    df = pd.read_csv(OUT_DIR / "split.csv")
    faltan, corruptos, formatos = [], [], collections.Counter()

    for r in df.itertuples():
        p = CLIPS_DIR / r.Show / r.clip_name
        if not p.exists():
            faltan.append(r.clip_name)
            continue
        try:
            with wave.open(str(p)) as w:
                formatos[(w.getframerate(), round(w.getnframes() / w.getframerate(), 2))] += 1
        except Exception as e:
            corruptos.append(f"{r.clip_name}: {e}")

    print(f"[verify] clips del split: {len(df)} | faltantes: {len(faltan)} | corruptos: {len(corruptos)}")
    for (sr, dur), n in formatos.most_common(5):
        print(f"  {n:5d} clips  {sr} Hz  {dur} s")
    cortos = sum(n for (_, dur), n in formatos.items() if dur < 3.0)
    print(f"  {cortos} clips duran menos de 3 s")
    for x in (faltan + corruptos)[:10]:
        print("  [!]", x)


if __name__ == "__main__":
    main()
