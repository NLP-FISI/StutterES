"""Servidor de anotacion en vivo. Solo biblioteca estandar.

    .venv/bin/python src/web/app.py        ->  http://127.0.0.1:8765

Las anotaciones van a anotaciones.db (SQLite) en la raiz del proyecto; los
CSV originales no se tocan nunca. La primera vez que se abre una lectura se
siembran las disfluencias que ya se conocen por los clips de 3 s, y a partir
de ahi el anotador las corrige.
"""
import json
import mimetypes
import os
import re
import sqlite3
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

AQUI = Path(__file__).resolve().parent
ROOT = AQUI.parents[1]
ESTATICO = AQUI / "static"
CLIPS_ORACIONES = ROOT / "clips_oraciones"
CLIPS_3S = ROOT / "clips"
DB = ROOT / "anotaciones.db"
PUERTO = int(os.environ.get("PUERTO", 8765))
SOLO_LECTURA = os.environ.get("SOLO_LECTURA") == "1"

DATOS = json.loads((AQUI / "dataset.json").read_text())
ESTADOS = {"pendiente", "en_progreso", "completada", "dudosa"}
DUR = 3.0  # toda marca dura exactamente 3 s


def ventana(ini, total):
    """Encaja un inicio suelto en una ventana de 3 s dentro de la oracion.

    Si la oracion dura menos de 3 s, la ventana es la oracion entera.
    """
    total = total or DUR
    if total <= DUR:
        return 0.0, round(total, 3)
    a = min(max(0.0, ini), total - DUR)
    return round(a, 3), round(a + DUR, 3)

ESQUEMA = """
CREATE TABLE IF NOT EXISTS estado (
  speaker TEXT, lectura INTEGER, sent_idx INTEGER,
  estado TEXT NOT NULL DEFAULT 'pendiente', nota TEXT DEFAULT '',
  actualizado REAL,
  PRIMARY KEY (speaker, lectura, sent_idx));

CREATE TABLE IF NOT EXISTS disfluencia (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  speaker TEXT, lectura INTEGER, sent_idx INTEGER,
  tipo TEXT NOT NULL, start_s REAL, stop_s REAL,
  origen TEXT NOT NULL DEFAULT 'manual', nota TEXT DEFAULT '',
  clip3s INTEGER, creado REAL);
CREATE INDEX IF NOT EXISTS ix_disf ON disfluencia (speaker, lectura, sent_idx);

CREATE TABLE IF NOT EXISTS sembrada (
  speaker TEXT, lectura INTEGER, cuando REAL,
  PRIMARY KEY (speaker, lectura));
"""


def conectar():
    cx = sqlite3.connect(DB, check_same_thread=False)
    cx.row_factory = sqlite3.Row
    cx.execute("PRAGMA journal_mode=WAL")
    cx.executescript(ESQUEMA)
    return cx


CX = conectar()


def duraciones():
    d = {}
    for sp, lecs in DATOS["datos"].items():
        for num, lec in lecs.items():
            for o in lec["oraciones"]:
                if o.get("dur_s"):
                    d[(sp, int(num), o["idx"])] = o["dur_s"]
    return d


def normalizar():
    """Reencaja a 3 s las marcas que quedaron cortas de una version anterior."""
    dur = duraciones()
    n = 0
    for r in CX.execute("SELECT id,speaker,lectura,sent_idx,start_s,stop_s FROM "
                        "disfluencia WHERE start_s IS NOT NULL").fetchall():
        total = dur.get((r["speaker"], r["lectura"], r["sent_idx"]))
        a, b = ventana(r["start_s"], total)
        if abs(r["start_s"] - a) > 0.005 or abs(r["stop_s"] - b) > 0.005:
            CX.execute("UPDATE disfluencia SET start_s=?, stop_s=? WHERE id=?",
                       (a, b, r["id"]))
            n += 1
    if n:
        CX.commit()
        print(f"{n} marcas reencajadas a {DUR:.0f} s")


DURACIONES = duraciones()
normalizar()


def sembrar(sp, num):
    """Copia a la BD las disfluencias que ya conocemos por los clips de 3 s."""
    if CX.execute("SELECT 1 FROM sembrada WHERE speaker=? AND lectura=?",
                  (sp, num)).fetchone():
        return
    lec = DATOS["datos"][sp].get(str(num))
    ahora = time.time()
    if lec:
        for o in lec["oraciones"]:
            for c in o["clips3s"]:
                for t in c["labels"]:
                    if t == "NoStutteredWords":
                        continue
                    a, b = ventana(c["rel_start"], o.get("dur_s"))
                    CX.execute(
                        "INSERT INTO disfluencia (speaker,lectura,sent_idx,tipo,"
                        "start_s,stop_s,origen,clip3s,creado) VALUES (?,?,?,?,?,?,?,?,?)",
                        (sp, num, o["idx"], t, a, b, "auto_3s", c["id"], ahora))
    CX.execute("INSERT INTO sembrada VALUES (?,?,?)", (sp, num, ahora))
    CX.commit()


def progreso_speaker(sp):
    filas = CX.execute(
        "SELECT lectura, estado, COUNT(*) n FROM estado WHERE speaker=? "
        "GROUP BY lectura, estado", (sp,)).fetchall()
    por_lec = {}
    for f in filas:
        por_lec.setdefault(f["lectura"], {})[f["estado"]] = f["n"]
    return por_lec


# --------------------------------------------------------------------- API

def api_meta():
    salida = []
    for sp in DATOS["speakers"]:
        por_lec = progreso_speaker(sp)
        total = sum(len(l["oraciones"]) for l in DATOS["datos"][sp].values())
        hechas = sum(v.get("completada", 0) for v in por_lec.values())
        con_audio = sum(l["n_con_audio"] for l in DATOS["datos"][sp].values())
        salida.append({"id": sp, "n_lecturas": len(DATOS["datos"][sp]),
                       "n_oraciones": total, "n_con_audio": con_audio,
                       "completadas": hechas})
    return {"speakers": salida, "clases": DATOS["clases"], "otras": DATOS["otras"]}


def api_lecturas(sp):
    por_lec = progreso_speaker(sp)
    salida = []
    for num, lec in sorted(DATOS["datos"][sp].items(), key=lambda kv: int(kv[0])):
        p = por_lec.get(int(num), {})
        salida.append({"num": int(num), "nombre": lec["lectura"],
                       "n_oraciones": lec["n_oraciones"],
                       "n_con_audio": lec["n_con_audio"],
                       "completadas": p.get("completada", 0),
                       "en_progreso": p.get("en_progreso", 0),
                       "dudosas": p.get("dudosa", 0)})
    return {"speaker": sp, "lecturas": salida}


def api_lectura(sp, num):
    lec = DATOS["datos"][sp].get(str(num))
    if lec is None:
        return None
    sembrar(sp, num)
    estados = {r["sent_idx"]: dict(r) for r in CX.execute(
        "SELECT * FROM estado WHERE speaker=? AND lectura=?", (sp, num))}
    disf = {}
    for r in CX.execute("SELECT * FROM disfluencia WHERE speaker=? AND lectura=? "
                        "ORDER BY start_s", (sp, num)):
        disf.setdefault(r["sent_idx"], []).append(dict(r))

    oraciones = []
    for o in lec["oraciones"]:
        d = dict(o)
        e = estados.get(o["idx"], {})
        d["estado"] = e.get("estado", "pendiente")
        d["nota"] = e.get("nota", "") or ""
        d["disfluencias"] = disf.get(o["idx"], [])
        if o["audio"]:
            d["audio_url"] = f"/audio/oracion/{sp}/{o['audio']}"
        for c in d["clips3s"]:
            c["url"] = f"/audio/clip/{sp}/{c['file']}"
        oraciones.append(d)
    return {"speaker": sp, "num": num, "nombre": lec["lectura"],
            "epid": lec["epid"], "oraciones": oraciones}


def api_guardar_estado(b):
    if b["estado"] not in ESTADOS:
        raise ValueError("estado invalido")
    CX.execute(
        "INSERT INTO estado (speaker,lectura,sent_idx,estado,nota,actualizado) "
        "VALUES (?,?,?,?,?,?) ON CONFLICT(speaker,lectura,sent_idx) DO UPDATE SET "
        "estado=excluded.estado, nota=excluded.nota, actualizado=excluded.actualizado",
        (b["speaker"], int(b["lectura"]), int(b["sent_idx"]), b["estado"],
         b.get("nota", ""), time.time()))
    CX.commit()
    return {"ok": True}


def api_crear_disf(b):
    if b.get("start_s") is not None:
        b["start_s"], b["stop_s"] = ventana(
            float(b["start_s"]), DURACIONES.get(
                (b["speaker"], int(b["lectura"]), int(b["sent_idx"]))))
    cur = CX.execute(
        "INSERT INTO disfluencia (speaker,lectura,sent_idx,tipo,start_s,stop_s,"
        "origen,nota,clip3s,creado) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (b["speaker"], int(b["lectura"]), int(b["sent_idx"]), b["tipo"],
         b.get("start_s"), b.get("stop_s"), b.get("origen", "manual"),
         b.get("nota", ""), b.get("clip3s"), time.time()))
    CX.commit()
    return {"ok": True, "id": cur.lastrowid}


def api_editar_disf(b):
    if b.get("start_s") is not None:
        f = CX.execute("SELECT speaker,lectura,sent_idx FROM disfluencia WHERE id=?",
                       (int(b["id"]),)).fetchone()
        if f:
            b["start_s"], b["stop_s"] = ventana(
                float(b["start_s"]),
                DURACIONES.get((f["speaker"], f["lectura"], f["sent_idx"])))
    campos, vals = [], []
    for k in ("tipo", "start_s", "stop_s", "nota"):
        if k in b:
            campos.append(f"{k}=?")
            vals.append(b[k])
    if not campos:
        return {"ok": True}
    vals.append(int(b["id"]))
    CX.execute(f"UPDATE disfluencia SET {','.join(campos)} WHERE id=?", vals)
    CX.commit()
    return {"ok": True}


def api_borrar_disf(b):
    CX.execute("DELETE FROM disfluencia WHERE id=?", (int(b["id"]),))
    CX.commit()
    return {"ok": True}


def api_exportar():
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["speaker", "lectura", "sent_idx", "texto", "estado", "nota_oracion",
                "disf_id", "tipo", "start_s", "stop_s", "origen", "nota_disf"])
    for sp in DATOS["speakers"]:
        for num, lec in sorted(DATOS["datos"][sp].items(), key=lambda kv: int(kv[0])):
            n = int(num)
            est = {r["sent_idx"]: r for r in CX.execute(
                "SELECT * FROM estado WHERE speaker=? AND lectura=?", (sp, n))}
            disf = {}
            for r in CX.execute("SELECT * FROM disfluencia WHERE speaker=? AND "
                                "lectura=? ORDER BY start_s", (sp, n)):
                disf.setdefault(r["sent_idx"], []).append(r)
            for o in lec["oraciones"]:
                e = est.get(o["idx"])
                base = [sp, n, o["idx"], o["texto"],
                        e["estado"] if e else "pendiente",
                        (e["nota"] if e else "") or ""]
                ds = disf.get(o["idx"], [])
                if not ds:
                    w.writerow(base + ["", "", "", "", "", ""])
                for d in ds:
                    w.writerow(base + [d["id"], d["tipo"], d["start_s"],
                                       d["stop_s"], d["origen"], d["nota"] or ""])
    return buf.getvalue()


# ------------------------------------------------------------------ HTTP

RANGO = re.compile(r"bytes=(\d*)-(\d*)")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        cuerpo = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _texto(self, s, tipo="text/plain; charset=utf-8", code=200, nombre=None):
        cuerpo = s.encode()
        self.send_response(code)
        self.send_header("Content-Type", tipo)
        if nombre:
            self.send_header("Content-Disposition", f'attachment; filename="{nombre}"')
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _archivo(self, ruta: Path, base: Path):
        try:
            ruta = ruta.resolve()
            ruta.relative_to(base.resolve())
        except (ValueError, OSError):
            return self._texto("prohibido", code=403)
        if not ruta.is_file():
            return self._texto("no existe", code=404)
        tipo = mimetypes.guess_type(str(ruta))[0] or "application/octet-stream"
        if ruta.suffix == ".js":
            tipo = "text/javascript"
        tam = ruta.stat().st_size
        rango = self.headers.get("Range")
        ini, fin = 0, tam - 1
        code = 200
        if rango and (m := RANGO.match(rango)):
            a, b = m.group(1), m.group(2)
            if a:
                ini = int(a)
                fin = int(b) if b else tam - 1
            elif b:
                ini = max(0, tam - int(b))
            ini = min(ini, tam - 1)
            fin = min(fin, tam - 1)
            code = 206
        self.send_response(code)
        self.send_header("Content-Type", tipo)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(fin - ini + 1))
        if code == 206:
            self.send_header("Content-Range", f"bytes {ini}-{fin}/{tam}")
        self.end_headers()
        with open(ruta, "rb") as f:
            f.seek(ini)
            quedan = fin - ini + 1
            while quedan > 0:
                trozo = f.read(min(262144, quedan))
                if not trozo:
                    break
                self.wfile.write(trozo)
                quedan -= len(trozo)

    def do_GET(self):
        p = unquote(urlparse(self.path).path)
        try:
            if p in ("/", "/index.html"):
                return self._archivo(ESTATICO / "index.html", ESTATICO)
            if p.startswith("/static/"):
                return self._archivo(ESTATICO / p[len("/static/"):], ESTATICO)
            if p == "/api/meta":
                return self._json(api_meta())
            if p.startswith("/api/lecturas/"):
                return self._json(api_lecturas(p.split("/")[3]))
            if p.startswith("/api/lectura/"):
                _, _, _, sp, num = p.split("/", 4)
                r = api_lectura(sp, int(num))
                return self._json(r) if r else self._json({"error": "no existe"}, 404)
            if p == "/api/export.csv":
                return self._texto(api_exportar(), "text/csv; charset=utf-8",
                                   nombre="anotaciones.csv")
            if p.startswith("/audio/oracion/"):
                resto = p[len("/audio/oracion/"):]
                return self._archivo(CLIPS_ORACIONES / resto, CLIPS_ORACIONES)
            if p.startswith("/audio/clip/"):
                resto = p[len("/audio/clip/"):]
                return self._archivo(CLIPS_3S / resto, CLIPS_3S)
            return self._texto("no existe", code=404)
        except Exception as e:  # noqa: BLE001
            return self._json({"error": str(e)}, 500)

    def do_POST(self):
        p = urlparse(self.path).path
        n = int(self.headers.get("Content-Length") or 0)
        try:
            b = json.loads(self.rfile.read(n) or b"{}")
            rutas = {"/api/estado": api_guardar_estado,
                     "/api/disfluencia": api_crear_disf,
                     "/api/disfluencia/editar": api_editar_disf,
                     "/api/disfluencia/borrar": api_borrar_disf}
            if p in rutas:
                if SOLO_LECTURA:
                    return self._json({"error": "servidor en solo lectura"}, 403)
                return self._json(rutas[p](b))
            return self._json({"error": "no existe"}, 404)
        except Exception as e:  # noqa: BLE001
            return self._json({"error": str(e)}, 500)


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PUERTO), Handler)
    print(f"StutterES anotador  ->  http://127.0.0.1:{PUERTO}")
    print(f"base de datos: {DB}"  + ("  (SOLO LECTURA)" if SOLO_LECTURA else ""))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nadios")
        sys.exit(0)


if __name__ == "__main__":
    main()
