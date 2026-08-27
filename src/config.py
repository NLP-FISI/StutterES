from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XLSX = ROOT / "data" / "Anotaciones de audio - tesis.xlsx"
CLIPS_DIR = ROOT / "clips"
OUT_DIR = ROOT / "outputs"
LOG_DIR = ROOT / "logs"

SHEETS = ["primera_revision", "segunda_revision"]
SPEAKERS = ["ATMA", "LPJM", "PVM", "RRYR", "SSF"]

# Ordenadas de la clase menos frecuente a la más frecuente. Cuando un clip
# tiene varias anotaciones, se queda con la primera de esta lista.
DISFLUENCIES = [
    "Interjection",
    "WordRep",
    "Block",
    "SoundRep",
    "Prolongation",
    "NoStutteredWords",
]

SPLIT_RATIOS = {"train": 0.70, "val": 0.15, "test": 0.15}
SEED = 42

for d in (CLIPS_DIR, OUT_DIR, LOG_DIR):
    d.mkdir(parents=True, exist_ok=True)
