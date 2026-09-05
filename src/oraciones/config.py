from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# el arbol sigue el orden del pipeline
AUDIO = ROOT / "audios"
ASR_DIR = ROOT / "transcripciones"
TEXTOS = ROOT / "textos"
CLIPS = ROOT / ".clips_oraciones_planos"   # cortes en bruto
OUT = ROOT / "outputs_oraciones"
INF = OUT / "informes"
LOGS = ROOT / "logs"

LECTURAS = TEXTOS / "lecturas.json"            # todas las oraciones
LECTURAS_DEP = TEXTOS / "lecturas_depuradas.json"  # sin las que nadie leyo

SPEAKERS = ["ATMA", "LPJM", "PVM", "RRYR", "SSF"]
ZENODO = {"ATMA": 11111351, "LPJM": 11111524, "PVM": 11111536,
          "RRYR": 11111545, "SSF": 11111549}
TEXTOS_DIR_ID = "1CDq2e13aZE08bAoBqRnq2UDh6Tj5yLqu"
SR = 16000


MODELO_ASR = "large-v3-turbo"
HILOS = 10

for d in (OUT, INF, CLIPS, LOGS):
    d.mkdir(parents=True, exist_ok=True)
