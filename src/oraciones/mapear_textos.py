"""Parte las 100 lecturas en oraciones."""
import json
import re
from collections import Counter

from wordfreq import zipf_frequency as zf

from config import TEXTOS

LETRA = "A-Za-zÁÉÍÓÚÑÜáéíóúñü"
MAY = "A-ZÁÉÍÓÚÑÜ"
FIN = '.!?'
CIERRA = '"»”\')]'

RE_FECHA = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$")
RE_URL = re.compile(r"https?://|www\.")
RE_PAG = re.compile(r"^\d+\s*/\s*\d+$")
RE_NUM = re.compile(r"^[\d\s.,/-]+$")
RE_SECCION = re.compile(r"^[A-ZÁÉÍÓÚÑÜ][A-ZÁÉÍÓÚÑÜ\s./-]{2,30}$")

# si un bloque acaba en una de estas, la frase sigue
COLGANTES = {"de", "del", "la", "el", "los", "las", "un", "una", "unos",
             "unas", "y", "e", "o", "u", "que", "en", "con", "por", "para",
             "a", "al", "su", "sus", "se", "es", "son", "como", "sin",
             "sobre", "entre", "desde", "hasta", "mas", "pero", "si", "no",
             "lo", "le", "les", "me", "te", "nos", "muy", "ya", "tras"}

ABREV = {"sr", "sra", "srta", "dr", "dra", "ing", "lic", "av", "ee", "uu",
         "ss", "aa", "pdta", "gral", "prof", "art", "n", "no", "num", "pag",
         "vol", "etc", "aprox", "km", "cm", "kg", "hrs", "min", "seg"}

AUDIT = []


def ligaduras(txt, doc):
    for pat in ("COVID-\x00\x00", "COVID-\x00", "Covid-\x00\x00", "Covid-\x00"):
        if pat in txt:
            txt = txt.replace(pat, pat.split("-")[0] + "-19")
            AUDIT.append((doc, pat.replace("\x00", "<NUL>"), "COVID-19", "año perdido"))
    out, i = [], 0
    for m in re.finditer("\x00", txt):
        j = m.start()
        out.append(txt[i:j])
        a = re.search(f"[{LETRA}]*\\Z", txt[:j]).group(0)
        b = re.match(f"[{LETRA}]*", txt[j + 1:]).group(0)
        zfi, zfl = zf((a + "fi" + b).lower(), "es"), zf((a + "fl" + b).lower(), "es")
        lig = "fi" if zfi >= zfl else "fl"
        AUDIT.append((doc, f"{a}<NUL>{b}", a + lig + b, f"fi {zfi:.1f} / fl {zfl:.1f}"))
        out.append(lig)
        i = j + 1
    out.append(txt[i:])
    return "".join(out)


def rota(l):
    """Linea de una pagina cuya extraccion fallo."""
    t = l.split()
    return len(t) >= 5 and sum(len(x) <= 2 for x in t) / len(t) > 0.6


def quita_rastro(txt):
    """Rachas de tokens sueltos incrustadas en mitad de una frase."""
    w = txt.split()
    fuera, i = set(), 0
    while i < len(w):
        j = i
        while j < len(w) and len(w[j]) <= 2:
            j += 1
        if j - i >= 5 and sum(1 for x in w[i:j] if len(x) == 1) >= 3:
            fuera.update(range(i, j))
        i = max(j, i + 1)
    return " ".join(x for k, x in enumerate(w) if k not in fuera)


def bloques(raw, doc):
    """Lineas utiles agrupadas en bloques consecutivos."""
    raw = ligaduras(raw, doc).replace("\x0c", "\n")
    lin = [l.strip() for l in raw.splitlines()]
    rep = {l for l, n in Counter(x for x in lin if x).items()
           if n >= 2 and len(l) >= 40}
    out, act = [], []
    for l in lin:
        util = (l and l not in rep and not rota(l) and not RE_FECHA.match(l)
                and not RE_PAG.match(l) and not RE_NUM.match(l)
                and not RE_URL.search(l) and not RE_SECCION.match(l))
        if util:
            act.append(l)
        elif act:
            out.append(act)
            act = []
    if act:
        out.append(act)
    return out


def une(lineas):
    t = lineas[0]
    for l in lineas[1:]:
        m1 = re.search(f"([{LETRA}]+)\\Z", t)
        m2 = re.match(f"([{LETRA}]+)", l)
        # palabra partida por el corte de linea, sin guion
        if (m1 and m2 and m1.group(1)[-1].islower() and m2.group(1)[0].islower()
                and zf((m1.group(1) + m2.group(1)).lower(), "es") >= 2.5
                and zf(m2.group(1).lower(), "es") < 2.0
                and zf(m1.group(1).lower(), "es") < 2.0):
            t += l
        else:
            t += " " + l
    t = re.sub(f"([{LETRA}])-\\s+([{LETRA}])", r"\1\2", t)
    return quita_rastro(re.sub(r"\s+", " ", t.replace("­", "").replace("…", "...")).strip())


def cierra_oracion(txt, i):
    if txt[i] == ".":
        pre = re.search(f"([{LETRA}]+)\\Z", txt[:i])
        if pre and (pre.group(1).lower() in ABREV or len(pre.group(1)) == 1):
            return False
        if re.match(r"^\.\d", txt[i:]):
            return False
    return bool(re.match(rf'^[{re.escape(FIN)}]+[{re.escape(CIERRA)}]*\s+'
                         rf'["«“¿¡]?[{MAY}0-9]', txt[i:]))


def parte(txt, minp=3):
    fr, ini = [], 0
    for i, ch in enumerate(txt):
        if ch in FIN and cierra_oracion(txt, i):
            j = i
            while j + 1 < len(txt) and txt[j + 1] in FIN + CIERRA:
                j += 1
            fr.append(txt[ini:j + 1].strip())
            ini = j + 1
    if txt[ini:].strip():
        fr.append(txt[ini:].strip())
    return [f for f in fr if len(f.split()) >= minp]


def mapear(raw, doc):
    bl = [une(b) for b in bloques(raw, doc)]
    bl = [b for b in bl if b]
    unidades, buf = [], []
    for i, b in enumerate(bl):
        sig = bl[i + 1] if i + 1 < len(bl) else ""
        # un titular puede acabar en "?" o "!"; se reconoce por ser de los
        # primeros bloques y venir suelto
        if i < 2 and not buf and len(b.split()) <= 25 and b.rstrip().endswith(("?", "!")):
            unidades.append(("titulo", b))
            continue
        acaba = b.rstrip(CIERRA).endswith(tuple(FIN))
        arranca_may = bool(re.match(f'^["«“¿¡]?[{MAY}]', sig))
        ultima = re.findall(f"[{LETRA}]+", b)
        colgante = bool(ultima) and ultima[-1].lower() in COLGANTES
        # un titulo no aparece en mitad de una frase sin cerrar
        abierto = bool(buf) and not " ".join(buf).rstrip(CIERRA).endswith(tuple(FIN))
        if not acaba and not colgante and not abierto and (arranca_may or not sig):
            if buf:
                unidades += [("cuerpo", s) for s in parte(" ".join(buf))]
                buf = []
            unidades.append(("titulo", b))
        else:
            buf.append(b)
    if buf:
        unidades += [("cuerpo", s) for s in parte(" ".join(buf))]
    tit = 0
    salida = []
    for tipo, t in unidades:
        if tipo == "titulo":
            tit += 1
            tipo = "titular" if tit == 1 else "bajada" if tit == 2 else "subtitulo"
        salida.append({"tipo": tipo, "texto": t, "palabras": len(t.split())})
    return salida


def main():
    mapa = {}
    for n in range(1, 101):
        p = TEXTOS / f"Lectura {n}.txt"
        ors = mapear(p.read_text(encoding="utf-8", errors="replace"),
                     f"Lectura {n}")
        mapa[f"Lectura {n}"] = ors
        (TEXTOS / f"Lectura {n:03d}.oraciones.txt").write_text(
            "\n".join(f"s{i:03d}  [{o['tipo']:9}] {o['texto']}"
                      for i, o in enumerate(ors)) + "\n")
    (TEXTOS / "mapa_oraciones.json").write_text(
        json.dumps(mapa, ensure_ascii=False, indent=1))
    # formato que consume el resto del pipeline
    compat = {n: {"n": int(n.split()[1]),
                  "clean": " ".join(o["texto"] for o in v),
                  "oraciones": [o["texto"] for o in v],
                  "tipos": [o["tipo"] for o in v],
                  "n_oraciones": len(v),
                  "palabras": sum(o["palabras"] for o in v)}
              for n, v in mapa.items()}
    (TEXTOS / "lecturas.json").write_text(
        json.dumps(compat, ensure_ascii=False, indent=1))

    ns = [len(v) for v in mapa.values()]
    tipos = Counter(o["tipo"] for v in mapa.values() for o in v)
    largo = [o["palabras"] for v in mapa.values() for o in v]
    print(f"{len(mapa)} lecturas -> {sum(ns)} unidades")
    print(f"  por lectura: min {min(ns)} / mediana {sorted(ns)[len(ns)//2]} / max {max(ns)}")
    print(f"  tipos: {dict(tipos)}")
    largo.sort()
    print(f"  palabras por unidad: mediana {largo[len(largo)//2]}, "
          f"p95 {largo[int(len(largo)*.95)]}, max {largo[-1]}")
    print(f"  reparaciones de ligadura: {len(AUDIT)}")


if __name__ == "__main__":
    main()
