# -*- coding: utf-8 -*-
"""Escribe la disfluencia dentro del texto, para que XTTS la lea.

XTTS-v2 genera habla fluida: la unica palanca que hay es el texto. Aqui se
traduce cada tipo del corpus a la forma escrita que mas se le parece:

    SoundRep      "ma ma magnitud"     repetir la primera silaba
    WordRep       "de de magnitud"     repetir la palabra entera
    Prolongation  "sssismo"            alargar una continuante
    Block         "... magnitud"       parada antes de la palabra
    Interjection  "eh, magnitud"       muletilla intercalada

Hay que saber lo que esto es y lo que no es. Un bloqueo real es una parada
con tension articulatoria; escrito como puntos suspensivos sale una pausa
limpia, que no es lo mismo. Un alargamiento escrito con letras repetidas sale
razonable en vocales y en /s/, y mal en oclusivas. Es decir: esto imita la
forma de la disfluencia, no su mecanismo. Sirve para aumentar datos, no para
pasar por habla disfluente real.
"""
import random
import re
import sys
import unicodedata

TIPOS = ["SoundRep", "WordRep", "Prolongation", "Block", "Interjection"]

MULETILLAS = ["eh", "em", "este", "mmm", "ah"]
VOCALES = set("aeiouáéíóúü")
# se alargan bien las continuantes; una oclusiva (p, t, k, b, d, g) repetida
# se lee como letras sueltas, no como un sonido sostenido
CONTINUANTES = set("aeiouáéíóúümnñlrsfjz")


def _norm(s):
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def primera_silaba(p):
    """Arranque de la palabra hasta la primera vocal incluida.

    Cuidado con "qu" y "gu" ante e/i: ahi la u no suena, asi que la silaba de
    "que" es "que" y no "qu" (si no, SoundRep daba "qu qu que").
    """
    # la rama del digrafo va primero y con el arranque perezoso: si no, el
    # [^vocales]* se come la "q" y la alternativa nunca llega a probarse
    m = re.match(r"^([^aeiouáéíóúüAEIOUÁÉÍÓÚÜ]*?[qQgG][uU][eéiíEÉIÍ]"
                 r"|[^aeiouáéíóúüAEIOUÁÉÍÓÚÜ]*[aeiouáéíóúüAEIOUÁÉÍÓÚÜ])", p)
    return m.group(1) if m else p[:2]


def sound_rep(p, veces=2):
    """'magnitud' -> 'ma ma magnitud'. Separado por espacios: con guion XTTS
    mete una pausa y suena a dos palabras, no a un tartamudeo."""
    s = primera_silaba(p)
    return " ".join([s.lower()] * max(1, veces) + [p])


def word_rep(p, veces=2):
    """veces es cuantas veces se dice en total: 2 -> 'de de'."""
    return " ".join([p.lower()] * max(0, veces - 1) + [p])


def prolongacion(p, n=4):
    """'sismo' -> 'ssssismo'. Alarga la primera continuante que encuentre.

    Las repeticiones van en minuscula aunque la palabra empiece por mayuscula:
    "Sssssismo" se lee como una ese sostenida y "SSSSismo" como siglas.
    """
    for i, c in enumerate(p[:3]):
        # la u de "que" y "gui" no suena: alargarla daba "quuuue"
        if (_norm(c) == "u" and i and _norm(p[i-1]) in "qg"
                and i + 1 < len(p) and _norm(p[i+1]) in "ei"):
            continue
        if _norm(c) in CONTINUANTES:
            return p[:i+1] + p[i].lower() * max(1, n - 1) + p[i+1:]
    return p


def bloqueo(p, puntos=3):
    """Parada antes de la palabra."""
    return "." * max(2, puntos) + " " + p


def interjeccion(p, cual=None, rng=None):
    rng = rng or random
    return f"{cual or rng.choice(MULETILLAS)}, {p}"


APLICA = {"SoundRep": sound_rep, "WordRep": word_rep,
          "Prolongation": prolongacion, "Block": bloqueo,
          "Interjection": interjeccion}

PALABRA = re.compile(r"[\w'ñÑáéíóúüÁÉÍÓÚÜ]+", re.UNICODE)


def aplicar(texto, marcas, intensidad=None, semilla=None):
    """marcas: [(indice_de_palabra, tipo)]. Devuelve el texto ya disfluente.

    El indice cuenta palabras desde 0. Si dos marcas caen en la misma palabra,
    se aplican en el orden en que vienen.
    """
    rng = random.Random(semilla)
    inten = intensidad or {}
    trozos, pos = [], 0
    por_palabra = {}
    for i, t in marcas:
        por_palabra.setdefault(int(i), []).append(t)
    for n, m in enumerate(PALABRA.finditer(texto)):
        if n not in por_palabra:
            continue
        p = m.group(0)
        for t in por_palabra[n]:
            fn = APLICA.get(t)
            if fn is None:
                raise ValueError(f"tipo desconocido: {t}")
            if t == "Interjection":
                p = fn(p, rng=rng)
            elif t in ("SoundRep", "WordRep"):
                p = fn(p, inten.get(t, 2))
            elif t == "Prolongation":
                p = fn(p, inten.get(t, 4))
            else:
                p = fn(p, inten.get(t, 3))
        trozos.append(texto[pos:m.start()]); trozos.append(p)
        pos = m.end()
    trozos.append(texto[pos:])
    return "".join(trozos)


def al_azar(texto, tasa=0.12, tipos=None, semilla=None, saltar_cortas=True):
    """Mete disfluencias al azar en una fraccion de las palabras."""
    rng = random.Random(semilla)
    tipos = tipos or TIPOS
    pals = list(PALABRA.finditer(texto))
    marcas = []
    for n, m in enumerate(pals):
        if saltar_cortas and len(m.group(0)) < 3 and rng.random() < 0.7:
            continue
        if rng.random() < tasa:
            marcas.append((n, rng.choice(tipos)))
    return aplicar(texto, marcas, semilla=semilla), marcas


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Escribe disfluencias en un texto")
    ap.add_argument("texto", nargs="?", help="la frase; si falta, se lee de stdin")
    ap.add_argument("--marcas", default="",
                    help="indice:tipo separados por comas, p.ej. 1:WordRep,3:Prolongation")
    ap.add_argument("--tasa", type=float, default=None,
                    help="en vez de marcas, mete disfluencias al azar en esta fraccion")
    ap.add_argument("--semilla", type=int, default=None)
    a = ap.parse_args()
    txt = a.texto or sys.stdin.read().strip()
    if a.tasa is not None:
        salida, marcas = al_azar(txt, a.tasa, semilla=a.semilla)
        print(salida)
        print("  marcas:", ", ".join(f"{i}:{t}" for i, t in marcas), file=sys.stderr)
    else:
        marcas = []
        for trozo in filter(None, (x.strip() for x in a.marcas.split(","))):
            i, t = trozo.split(":")
            marcas.append((int(i), t))
        print(aplicar(txt, marcas, semilla=a.semilla))
