import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

from config import CLIPS_DIR, OUT_DIR, LOG_DIR

URL = "https://drive.google.com/uc?export=download&id={}"
PARALELO = 60
LOTE = 600
PASADAS = 4


def pendientes(df):
    faltan = []
    for r in df.itertuples():
        destino = CLIPS_DIR / r.Show / r.clip_name
        if destino.exists() and destino.stat().st_size > 1000 and \
                destino.open("rb").read(4) == b"RIFF":
            continue
        faltan.append(r)
    return faltan


def bajar(lote):
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        for r in lote:
            destino = CLIPS_DIR / r.Show / r.clip_name
            f.write(f'url = "{URL.format(r.file_id)}"\noutput = "{destino}"\n')
        cfg = f.name
    subprocess.run(["curl", "-sL", "--parallel", "--parallel-max", str(PARALELO),
                    "--retry", "2", "--max-time", "120", "-K", cfg], check=False)
    Path(cfg).unlink(missing_ok=True)


def main():
    df = pd.read_csv(OUT_DIR / "index.csv")
    for show in df.Show.unique():
        (CLIPS_DIR / show).mkdir(parents=True, exist_ok=True)

    for pasada in range(1, PASADAS + 1):
        faltan = pendientes(df)
        if not faltan:
            break
        print(f"[download] pasada {pasada}: faltan {len(faltan)} de {len(df)}", flush=True)
        for i in range(0, len(faltan), LOTE):
            bajar(faltan[i:i + LOTE])
            print(f"  lote {i // LOTE + 1}/{-(-len(faltan) // LOTE)} listo", flush=True)

    faltan = pendientes(df)
    (LOG_DIR / "descargas_fallidas.txt").write_text(
        "\n".join(f"{r.clip_name}\t{r.file_id}" for r in faltan))
    print(f"[download] {len(df) - len(faltan)}/{len(df)} clips ({len(faltan)} fallidos)")
    return 1 if faltan else 0


if __name__ == "__main__":
    sys.exit(main())
