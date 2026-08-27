import re
import html
import urllib.request

import pandas as pd

from config import XLSX, SHEETS, SPEAKERS, DISFLUENCIES, OUT_DIR

ROOT_FOLDER = "16FekUlZbZ26Q59G_O3I8IJ7k3JNhq1w_"
EFV = "https://drive.google.com/embeddedfolderview?id={}#list"
LINK_RE = re.compile(
    r'href="https://drive\.google\.com/(?:file/d/|drive/folders/)([\w-]+)[^"]*"[^>]*>(?:<[^>]+>)*([^<]*)'
)


def list_folder(folder_id):
    """Devuelve {nombre: id} de un folder compartido de Drive."""
    req = urllib.request.Request(EFV.format(folder_id), headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        page = r.read().decode("utf-8", "replace")
    return {html.unescape(name).strip(): fid for fid, name in LINK_RE.findall(page)}


def load_sheets():
    xl = pd.ExcelFile(XLSX)
    frames = []
    for sheet in SHEETS:
        df = xl.parse(sheet)
        df = df[df["Show"].isin(SPEAKERS)].copy()
        df["sheet"] = sheet
        if "Resources" not in df.columns:
            df["Resources"] = pd.NA
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    df["clip_name"] = df.Show + "_" + df.EpId.astype(str) + "_" + df.ClipId.astype(str) + ".wav"
    return df


def resolve_missing_ids(df):
    """primera_revision no trae la columna Resources, así que sus clips hay
    que localizarlos recorriendo el árbol Show/EpId/clip.wav del Drive."""
    faltan = df[df.file_id.isna()]
    if faltan.empty:
        return df

    print(f"[index] resolviendo {len(faltan)} file_id desde Drive")
    shows = list_folder(ROOT_FOLDER)
    ep_cache, encontrados = {}, {}
    for show, ep in sorted({(r.Show, r.EpId) for r in faltan.itertuples()}):
        if show not in shows:
            continue
        if show not in ep_cache:
            ep_cache[show] = list_folder(shows[show])
        ep_id = ep_cache[show].get(str(ep))
        if not ep_id:
            print(f"  [!] episodio no encontrado: {show}/{ep}")
            continue
        encontrados.update(list_folder(ep_id))

    df["file_id"] = df.file_id.fillna(df.clip_name.map(encontrados))
    return df


def etiqueta_primaria(row):
    for c in DISFLUENCIES:
        if row[c] > 0:
            return c
    return None


def main():
    df = load_sheets()
    df["file_id"] = df.Resources.str.extract(r"/d/([\w-]+)", expand=False)
    df = resolve_missing_ids(df)

    df["label"] = df.apply(etiqueta_primaria, axis=1)
    df["n_labels"] = df[DISFLUENCIES].gt(0).sum(axis=1)
    df["descartada"] = df.label.isna()

    print(f"[index] filas con los 5 speakers: {len(df)}")
    print(f"[index] sin ninguna de las 6 clases: {df.descartada.sum()}")
    print(f"[index] sin file_id: {df.file_id.isna().sum()}")

    cols = ["sheet", "Show", "EpId", "ClipId", "clip_name", "file_id", "label",
            "n_labels", "descartada", *DISFLUENCIES,
            "Start", "Stop", "Unsure", "PoorAudioQuality", "DifficultToUnderstand",
            "NaturalPause", "Music", "NoSpeech"]
    df[cols].to_csv(OUT_DIR / "index.csv", index=False)
    print(f"[index] escrito {OUT_DIR / 'index.csv'}")


if __name__ == "__main__":
    main()
