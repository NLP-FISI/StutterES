"""Descarga los audios completos (Zenodo) y las lecturas (Drive).
"""
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import AUDIO, LOGS, TEXTOS, ZENODO

# zenodo devuelve 403 a urllib y a "Mozilla/5.0"; el UA de curl si pasa
CURL = ["curl", "-sSL", "--fail", "--retry", "5", "--retry-delay", "2",
        "--max-time", "300"]


def curl_bytes(url):
    return subprocess.run(CURL + [url], capture_output=True, check=True).stdout


def valido(p, magic, minimo=1024):
    try:
        return (os.path.getsize(p) >= minimo and
                (magic is None or open(p, "rb").read(len(magic)) == magic))
    except OSError:
        return False


def baja(url, dst, magic):
    if valido(dst, magic):
        return "skip"
    tmp = str(dst) + ".part"
    try:
        subprocess.run(CURL + ["-o", tmp, url], check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        return f"FAIL curl {e.returncode}"
    if not valido(tmp, magic):
        return "FAIL contenido invalido"
    os.replace(tmp, dst)
    return "ok"


def main():
    tareas = []
    for sp, rec in ZENODO.items():
        (AUDIO / sp).mkdir(parents=True, exist_ok=True)
        meta = json.loads(curl_bytes(f"https://zenodo.org/api/records/{rec}"))
        for f in meta["files"]:
            tareas.append((
                f"https://zenodo.org/records/{rec}/files/{f['key']}?download=1",
                AUDIO / sp / f["key"], b"RIFF"))
        print(f"[zenodo] {sp}: {len(meta['files'])} audios", flush=True)

    TEXTOS.mkdir(parents=True, exist_ok=True)
    for line in open(TEXTOS / "textos_list.tsv"):
        fid, name = line.rstrip("\n").split("\t")
        tareas.append((f"https://drive.google.com/uc?export=download&id={fid}",
                       TEXTOS / name, None))
    print(f"[total] {len(tareas)} ficheros", flush=True)

    res, fallos = {}, []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(baja, u, d, m): d for u, d, m in tareas}
        for i, fut in enumerate(as_completed(futs), 1):
            r = fut.result()
            k = "FAIL" if r.startswith("FAIL") else r
            res[k] = res.get(k, 0) + 1
            if k == "FAIL":
                fallos.append(f"{futs[fut]}\t{r}")
            if i % 50 == 0 or i == len(tareas):
                print(f"  {i}/{len(tareas)} {res}", flush=True)
    if fallos:
        (LOGS / "fetch_fallos.txt").write_text("\n".join(fallos) + "\n")
    print("FIN", res)


if __name__ == "__main__":
    main()
