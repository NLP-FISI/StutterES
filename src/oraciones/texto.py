"""Normalizacion y tokenizacion compartidas."""
import re
import unicodedata

_LIMPIA = re.compile(r"[^a-z0-9ñ]+")
# letras y digitos van como tokens distintos: el ASR dice "covid" y "19"
# por separado, y "covid19" no casaria nunca
_PARTES = re.compile(r"[a-zñ]+|[0-9]+")


def norm(w):
    w = unicodedata.normalize("NFKD", w.lower())
    w = "".join(c for c in w if not unicodedata.combining(c))
    return _LIMPIA.sub("", w)


def norm_frase(t):
    return " ".join(x for x in (norm(w) for w in t.split()) if x)


def partes(w):
    """Una palabra -> uno o varios tokens, separando letras de digitos.

    Se parte sobre la forma sin acentos pero con la puntuacion todavia
    puesta, para que "3.2" de ["3", "2"] igual que lo dice el ASR.
    """
    w = unicodedata.normalize("NFKD", w.lower())
    w = "".join(c for c in w if not unicodedata.combining(c))
    return _PARTES.findall(w)


def tokens_lectura(oraciones):
    """Palabras de la lectura + a que oracion pertenece cada una."""
    toks, sid = [], []
    for k, o in enumerate(oraciones):
        for w in o.split():
            for t in partes(w):
                toks.append(t)
                sid.append(k)
    return toks, sid


def tokens_asr(d):
    """Palabras del ASR con sus tiempos, en orden."""
    ws = [w for seg in d["segmentos"] for w in seg["words"]
          if w["s"] is not None and w["e"] is not None]
    ws.sort(key=lambda w: w["s"])
    out = []
    for w in ws:
        for t in partes(w["w"]):
            out.append((t, w["s"], w["e"]))
    return out
