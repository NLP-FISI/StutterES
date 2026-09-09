"""Anotador: web, API, base de datos y audio en un proceso.

    python3 web/server.py     ->  http://127.0.0.1:8765

Entorno: PUERTO, HOST, DB_PATH, AUDIO_DIR, AUDIO_EXT.
"""
import csv
import hashlib
import json
import mimetypes
import os
import re
import signal
import sqlite3
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import youtube

AQUI = Path(__file__).resolve().parent
PUB = AQUI / "public"
ROOT = AQUI.parent
EXT = os.environ.get("AUDIO_EXT", "opus")
DB = Path(os.environ.get("DB_PATH", AQUI / "anotador.db"))
AUDIO_DIR = Path(os.environ.get("AUDIO_DIR", ROOT / "web_audio"))
CACHE = Path(os.environ.get("CACHE_DIR", ROOT / "cache_fragmentos"))
RECORTES = Path(os.environ.get("RECORTES_DIR", ROOT / "recortes"))
FRAG_MAX = 300.0    # tope de segundos por recorte
CACHE_MAX = 20000   # recortes en cache antes de tirar los mas viejos
PUERTO = int(os.environ.get("PUERTO", 8765))
HOST = os.environ.get("HOST", "127.0.0.1")
DUR = 3.0

ESQUEMA = """
CREATE TABLE IF NOT EXISTS oracion (speaker TEXT, lectura INT, sent_idx INT,
  ep_id TEXT, start_sample INT, start_s REAL, stop_s REAL, dur_s REAL, texto TEXT,
  PRIMARY KEY (speaker, lectura, sent_idx));
CREATE TABLE IF NOT EXISTS disfluencia (id INTEGER PRIMARY KEY AUTOINCREMENT,
  speaker TEXT, lectura INT, sent_idx INT, tipo TEXT, start_s REAL, stop_s REAL,
  origen TEXT DEFAULT 'manual', nota TEXT DEFAULT '', clip3s INT,
  autor TEXT DEFAULT '', creado TEXT);
CREATE INDEX IF NOT EXISTS ix_disf ON disfluencia (speaker, lectura, sent_idx);
CREATE TABLE IF NOT EXISTS youtube (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre TEXT NOT NULL, url TEXT NOT NULL, video_id TEXT DEFAULT '',
  titulo TEXT DEFAULT '', dur_s REAL DEFAULT 0, fichero TEXT DEFAULT '',
  picos TEXT DEFAULT '', estado TEXT DEFAULT 'descargando',
  error TEXT DEFAULT '', autor TEXT DEFAULT '', creado TEXT);

CREATE TABLE IF NOT EXISTS recorte (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  youtube_id INTEGER NOT NULL, nombre TEXT DEFAULT '',
  start_s REAL NOT NULL, stop_s REAL NOT NULL, fichero TEXT DEFAULT '',
  autor TEXT DEFAULT '', creado TEXT);
CREATE INDEX IF NOT EXISTS ix_recorte ON recorte (youtube_id);

CREATE TABLE IF NOT EXISTS estado (speaker TEXT, lectura INT, sent_idx INT,
  estado TEXT DEFAULT 'pendiente', nota TEXT DEFAULT '', autor TEXT DEFAULT '',
  actualizado TEXT, PRIMARY KEY (speaker, lectura, sent_idx));
"""

DB.parent.mkdir(parents=True, exist_ok=True)
# Una conexion por hilo: compartir una sola entre los hilos del servidor
# corrompe cursores y transacciones en cuanto hay dos anotando a la vez.
_hilo = threading.local()


def cx():
    c = getattr(_hilo, "cx", None)
    if c is None:
        c = sqlite3.connect(DB, timeout=20)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=20000")
        c.execute("PRAGMA synchronous=NORMAL")
        _hilo.cx = c
    return c


cx().executescript(ESQUEMA)


def migrar():
    """CREATE TABLE IF NOT EXISTS no toca las tablas que ya existen."""
    faltan = {"recorte": [("fichero", "TEXT DEFAULT ''")]}
    for tabla, columnas in faltan.items():
        tiene = {r[1] for r in cx().execute(f"PRAGMA table_info({tabla})")}
        for nombre, tipo in columnas:
            if nombre not in tiene:
                cx().execute(f"ALTER TABLE {tabla} ADD COLUMN {nombre} {tipo}")
                print(f"anadida {tabla}.{nombre}")
    cx().commit()


migrar()


def cargar():
    """Carga oracion.csv y siembra.csv la primera vez."""
    if cx().execute("SELECT 1 FROM oracion LIMIT 1").fetchone():
        return
    with open(PUB / "data" / "oracion.csv", encoding="utf-8") as f:
        cx().executemany(
            "INSERT INTO oracion VALUES (?,?,?,?,?,?,?,?,?)",
            [(r["speaker"], int(r["lectura"]), int(r["sent_idx"]), r["ep_id"],
              int(r["start_sample"]), float(r["start_s"]), float(r["stop_s"]),
              float(r["dur_s"]), r["texto"])
             for r in csv.DictReader(f)])
    with open(PUB / "data" / "siembra.csv", encoding="utf-8") as f:
        cx().executemany(
            "INSERT INTO disfluencia (speaker,lectura,sent_idx,tipo,start_s,stop_s,"
            "origen,clip3s,creado) VALUES (?,?,?,?,?,?,?,?,?)",
            [(r["speaker"], int(r["lectura"]), int(r["sent_idx"]), r["tipo"],
              float(r["start_s"]), float(r["stop_s"]), r["origen"],
              int(r["clip3s"]), time.strftime("%Y-%m-%dT%H:%M:%SZ"))
             for r in csv.DictReader(f)])
    cx().commit()
    print(f"cargadas oracion.csv y siembra.csv en {DB.name}")


def encajar(f):
    """Encaja la marca en 3 s: el usuario solo elige donde empieza."""
    if f.get("start_s") is None:
        f["stop_s"] = None
        return f
    r = cx().execute("SELECT dur_s FROM oracion WHERE speaker=? AND lectura=? AND "
                   "sent_idx=?", (f["speaker"], f["lectura"], f["sent_idx"])).fetchone()
    d = r["dur_s"] if r else DUR
    if d <= DUR:
        f["start_s"], f["stop_s"] = 0.0, round(d, 3)
    else:
        f["start_s"] = round(min(max(float(f["start_s"]), 0.0), d - DUR), 3)
        f["stop_s"] = round(f["start_s"] + DUR, 3)
    return f


COLS = {"disfluencia": ["speaker", "lectura", "sent_idx", "tipo", "start_s",
                        "stop_s", "origen", "nota", "clip3s", "autor", "creado"],
        "estado": ["speaker", "lectura", "sent_idx", "estado", "nota", "autor",
                   "actualizado"],
        "youtube": ["nombre"],
        "recorte": ["nombre", "start_s", "stop_s"]}
EQ = re.compile(r"^eq\.(.*)$")


def filtros(q):
    donde, vals = [], []
    for k, v in q.items():
        if k in ("select", "order", "limit", "offset"):
            continue
        m = EQ.match(v[0])
        if m:
            donde.append(f"{k}=?")
            vals.append(m.group(1))
    return (" WHERE " + " AND ".join(donde)) if donde else "", vals


def recortar(sp, epid, a, dur):
    """Recorta un trozo con ffmpeg y lo cachea.

    Cada marca suena desde su propio fichero, no desde un rango de la lectura
    entera, para que el navegador le ponga su barra.
    """
    src = (AUDIO_DIR / sp / f"{epid}.{EXT}").resolve()
    if not str(src).startswith(str(AUDIO_DIR.resolve())) or not src.is_file():
        return None
    clave = hashlib.sha1(f"{sp}/{epid}/{a:.3f}/{dur:.3f}/{EXT}".encode()).hexdigest()
    dst = CACHE / f"{clave}.{EXT}"
    if dst.is_file() and dst.stat().st_size > 0:
        return dst
    CACHE.mkdir(parents=True, exist_ok=True)
    ficheros = sorted(CACHE.glob(f"*.{EXT}"), key=lambda p: p.stat().st_mtime)
    for viejo in ficheros[:max(0, len(ficheros) - CACHE_MAX)]:
        viejo.unlink(missing_ok=True)
    tmp = CACHE / f".{clave}.part.{EXT}"
    codec = ["-c:a", "libopus", "-b:a", "24k"] if EXT == "opus" else \
            ["-c:a", "libmp3lame", "-b:a", "48k"]
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{a:.3f}",
                        "-t", f"{dur:.3f}", "-i", str(src), *codec, "-ac", "1",
                        str(tmp)], capture_output=True, timeout=60)
    if r.returncode or not tmp.exists():
        tmp.unlink(missing_ok=True)
        return None
    tmp.replace(dst)
    return dst


YT_DIR = AUDIO_DIR / "youtube"


def bajar_video(fila_id, url):
    """Hilo de descarga: deja la fila en 'listo' o en 'error'."""
    try:
        datos = youtube.info(url, ROOT)
        destino = YT_DIR / f"{fila_id}_{datos['video_id'] or 'audio'}.{EXT}"
        cx().execute("UPDATE youtube SET video_id=?, titulo=?, dur_s=? WHERE id=?",
                     (datos["video_id"], datos["titulo"], datos["dur_s"], fila_id))
        cx().commit()
        youtube.descargar(url, destino, ROOT)
        dur = youtube.duracion(destino)
        picos, _ = youtube.envolvente(destino, dur)
        cx().execute("UPDATE youtube SET fichero=?, dur_s=?, picos=?, estado='listo',"
                     " error='' WHERE id=?",
                     (destino.name, dur, picos, fila_id))
        cx().commit()
    except Exception as e:  # noqa: BLE001
        cx().execute("UPDATE youtube SET estado='error', error=? WHERE id=?",
                     (str(e)[:400], fila_id))
        cx().commit()


def nombre_limpio(s, por_defecto):
    s = re.sub(r"[^\w .-]", "_", (s or "").strip(), flags=re.UNICODE)[:60]
    return s or por_defecto


def guardar_recorte(rid):
    """Escribe el recorte como fichero propio, no como cache que se puede tirar."""
    try:
        r = cx().execute("SELECT * FROM recorte WHERE id=?", (rid,)).fetchone()
        if not r:
            return
        v = cx().execute("SELECT nombre, fichero FROM youtube WHERE id=?",
                         (r["youtube_id"],)).fetchone()
        if not v or not v["fichero"]:
            return
        src = YT_DIR / v["fichero"]
        carpeta = RECORTES / nombre_limpio(v["nombre"], f"audio_{r['youtube_id']}")
        carpeta.mkdir(parents=True, exist_ok=True)
        dst = carpeta / f"{r['id']:04d}_{nombre_limpio(r['nombre'], 'recorte')}.{EXT}"
        if r["fichero"] and r["fichero"] != str(dst.relative_to(RECORTES)):
            (RECORTES / r["fichero"]).unlink(missing_ok=True)
        codec = ["-c:a", "libopus", "-b:a", "24k"] if EXT == "opus" else \
                ["-c:a", "libmp3lame", "-b:a", "48k"]
        tmp = dst.with_suffix(f".part.{EXT}")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                        "-ss", f"{r['start_s']:.3f}",
                        "-t", f"{max(0.05, r['stop_s'] - r['start_s']):.3f}",
                        "-i", str(src), *codec, "-ac", "1", str(tmp)],
                       capture_output=True, timeout=600, check=True)
        tmp.replace(dst)
        cx().execute("UPDATE recorte SET fichero=? WHERE id=?",
                     (str(dst.relative_to(RECORTES)), rid))
        cx().commit()
    except Exception as e:  # noqa: BLE001
        print(f"[recorte {rid}] {e}", flush=True)


def borrar_ficheros_recorte(filas):
    for r in filas:
        if r["fichero"]:
            f = RECORTES / r["fichero"]
            f.unlink(missing_ok=True)
            try:
                f.parent.rmdir()
            except OSError:
                pass


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _j(self, obj, code=200):
        # Un 204 no lleva cuerpo: mandarlo descuadra la conexion persistente y
        # la siguiente peticion se queda esperando una respuesta que ya paso.
        if code == 204:
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _cuerpo(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def _estatico(self, ruta):
        p = (PUB / ruta.lstrip("/")).resolve()
        if not str(p).startswith(str(PUB.resolve())) or not p.is_file():
            return self._j({"error": "no existe"}, 404)
        b = p.read_bytes()
        t = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
        if p.suffix == ".js":
            t = "text/javascript"
        self.send_response(200)
        self.send_header("Content-Type", t)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _audio(self, resto):
        """Entrega el audio por rangos, para que el navegador pueda saltar."""
        p = (AUDIO_DIR / resto).resolve()
        if not str(p).startswith(str(AUDIO_DIR.resolve())) or not p.is_file():
            return self._j({"error": "no existe"}, 404)
        tam = p.stat().st_size
        tipo = {"opus": "audio/ogg", "mp3": "audio/mpeg",
                "wav": "audio/wav"}.get(p.suffix[1:], "application/octet-stream")
        m = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range") or "")
        ini, fin, code = 0, tam - 1, 200
        if m:
            if m.group(1):
                ini = int(m.group(1))
                fin = int(m.group(2)) if m.group(2) else tam - 1
            elif m.group(2):
                ini = max(0, tam - int(m.group(2)))
            ini, fin, code = min(ini, tam - 1), min(fin, tam - 1), 206
        self.send_response(code)
        self.send_header("Content-Type", tipo)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(fin - ini + 1))
        if code == 206:
            self.send_header("Content-Range", f"bytes {ini}-{fin}/{tam}")
        self.end_headers()
        with open(p, "rb") as f:
            f.seek(ini)
            quedan = fin - ini + 1
            while quedan > 0:
                b = f.read(min(262144, quedan))
                if not b:
                    break
                self.wfile.write(b)
                quedan -= len(b)

    def _fragmento(self, resto, q):
        """/fragmento/<hablante>/<epid>?a=<inicio>&b=<fin>, en segundos."""
        partes = resto.split("/")
        if len(partes) != 2:
            return self._j({"error": "ruta invalida"}, 400)
        sp, epid = partes
        if not re.fullmatch(r"[A-Za-z0-9_-]+", sp) or \
           not re.fullmatch(r"[A-Za-z0-9_:.-]+", epid.removesuffix(f".{EXT}")):
            return self._j({"error": "nombre invalido"}, 400)
        try:
            a = max(0.0, float(q.get("a", ["0"])[0]))
            b = float(q.get("b", ["3"])[0])
        except ValueError:
            return self._j({"error": "a/b invalidos"}, 400)
        if b <= a:
            return self._j({"error": "b debe ser mayor que a"}, 400)
        dur = min(b - a, FRAG_MAX)
        f = recortar(sp, epid.removesuffix(f".{EXT}"), a, dur)
        if f is None:
            return self._j({"error": "no se pudo recortar"}, 404)
        b_ = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "audio/ogg" if EXT == "opus" else "audio/mpeg")
        if (nombre := q.get("descargar", [""])[0]):
            limpio = re.sub(r"[^A-Za-z0-9 _.-]", "_", nombre)[:80] or "recorte"
            self.send_header("Content-Disposition",
                             f'attachment; filename="{limpio}.{EXT}"')
        self.send_header("Content-Length", str(len(b_)))
        self.send_header("Accept-Ranges", "none")
        self.send_header("Cache-Control", "public, max-age=31536000")
        self.end_headers()
        self.wfile.write(b_)

    def do_GET(self):
        try:
            return self._do_GET()
        except Exception as e:  # noqa: BLE001
            import traceback; traceback.print_exc()
            try:
                return self._j({"error": str(e)}, 500)
            except Exception:
                return

    def _do_GET(self):
        u = urlparse(self.path)
        p, q = unquote(u.path), parse_qs(u.query)
        if p == "/api/config":
            return self._j({"audio": "/audio", "ext": EXT})
        if p.startswith("/audio/"):
            return self._audio(p[len("/audio/"):])
        if p.startswith("/fragmento/"):
            return self._fragmento(p[len("/fragmento/"):], q)
        if p == "/api/youtube":
            return self._j([dict(r) for r in cx().execute(
                "SELECT id,nombre,url,video_id,titulo,dur_s,fichero,estado,error,"
                "autor,creado FROM youtube ORDER BY id DESC")])
        if p.startswith("/api/youtube/"):
            r = cx().execute("SELECT * FROM youtube WHERE id=?",
                             (int(p.split("/")[3]),)).fetchone()
            return self._j(dict(r)) if r else self._j({"error": "no existe"}, 404)
        if p == "/api/recorte":
            w, v = filtros(q)
            return self._j([dict(r) for r in cx().execute(
                f"SELECT * FROM recorte{w} ORDER BY start_s", v)])
        if p.startswith("/rest/v1/"):
            t = p.split("/")[3]
            if t == "progreso":
                w, v = filtros(q)
                filas = cx().execute(
                    "SELECT speaker, lectura,"
                    " SUM(estado='completada') completadas,"
                    " SUM(estado='en_progreso') en_progreso,"
                    " SUM(estado='dudosa') dudosas FROM estado"
                    + w + " GROUP BY speaker, lectura", v).fetchall()
                return self._j([dict(r) for r in filas])
            if t not in COLS and t != "oracion":
                return self._j({"error": "tabla desconocida"}, 404)
            w, v = filtros(q)
            return self._j([dict(r) for r in cx().execute(f"SELECT * FROM {t}{w}", v)])
        return self._estatico("/index.html" if p == "/" else p)

    def do_POST(self):
        try:
            return self._do_POST()
        except Exception as e:  # noqa: BLE001
            import traceback; traceback.print_exc()
            try:
                return self._j({"error": str(e)}, 500)
            except Exception:
                return

    def _do_POST(self):
        u = urlparse(self.path)
        t = u.path.split("/")[3]
        f = self._cuerpo()
        pref = self.headers.get("Prefer", "")
        if t == "disfluencia":
            f = encajar(f)
            f.setdefault("creado", time.strftime("%Y-%m-%dT%H:%M:%SZ"))
            cols = [c for c in COLS[t] if c in f]
            cur = cx().execute(
                f"INSERT INTO disfluencia ({','.join(cols)}) VALUES ({','.join('?'*len(cols))})",
                [f[c] for c in cols])
            cx().commit()
            fila = cx().execute("SELECT * FROM disfluencia WHERE id=?", (cur.lastrowid,)).fetchone()
            return self._j([dict(fila)] if "representation" in pref else [], 201)
        if t == "youtube":
            url = (f.get("url") or "").strip()
            nombre = (f.get("nombre") or "").strip() or "sin nombre"
            if not youtube.URL_VALIDA.match(url):
                return self._j({"error": "no parece un enlace de YouTube"}, 400)
            cur = cx().execute(
                "INSERT INTO youtube (nombre,url,autor,creado) VALUES (?,?,?,?)",
                (nombre, url, f.get("autor", ""), time.strftime("%Y-%m-%dT%H:%M:%SZ")))
            cx().commit()
            fid = cur.lastrowid
            threading.Thread(target=bajar_video, args=(fid, url), daemon=True).start()
            fila = cx().execute("SELECT * FROM youtube WHERE id=?", (fid,)).fetchone()
            return self._j([dict(fila)], 201)
        if t == "recorte":
            cur = cx().execute(
                "INSERT INTO recorte (youtube_id,nombre,start_s,stop_s,autor,creado)"
                " VALUES (?,?,?,?,?,?)",
                (int(f["youtube_id"]), f.get("nombre", ""), float(f["start_s"]),
                 float(f["stop_s"]), f.get("autor", ""),
                 time.strftime("%Y-%m-%dT%H:%M:%SZ")))
            cx().commit()
            fila = cx().execute("SELECT * FROM recorte WHERE id=?",
                                (cur.lastrowid,)).fetchone()
            threading.Thread(target=guardar_recorte, args=(cur.lastrowid,),
                             daemon=True).start()
            return self._j([dict(fila)], 201)
        if t == "estado":
            cols = [c for c in COLS[t] if c in f]
            cx().execute(
                f"INSERT INTO estado ({','.join(cols)}) VALUES ({','.join('?'*len(cols))}) "
                "ON CONFLICT(speaker,lectura,sent_idx) DO UPDATE SET "
                + ",".join(f"{c}=excluded.{c}" for c in cols if c not in
                           ("speaker", "lectura", "sent_idx")),
                [f[c] for c in cols])
            cx().commit()
            return self._j([], 201)
        return self._j({"error": "tabla desconocida"}, 404)

    def do_PATCH(self):
        try:
            return self._do_PATCH()
        except Exception as e:  # noqa: BLE001
            import traceback; traceback.print_exc()
            try:
                return self._j({"error": str(e)}, 500)
            except Exception:
                return

    def _do_PATCH(self):
        u = urlparse(self.path)
        t, q = u.path.split("/")[3], parse_qs(u.query)
        f = self._cuerpo()
        w, v = filtros(q)
        if t == "disfluencia" and "start_s" in f:
            m = EQ.match(q.get("id", [""])[0])
            r = cx().execute("SELECT speaker,lectura,sent_idx FROM disfluencia WHERE id=?",
                           (m.group(1),)).fetchone() if m else None
            if r:
                f = encajar({**f, **dict(r)})
        cols = [c for c in COLS[t] if c in f]
        cx().execute(f"UPDATE {t} SET {','.join(c + '=?' for c in cols)}{w}",
                   [f[c] for c in cols] + v)
        cx().commit()
        if t == "recorte":
            for r in cx().execute(f"SELECT id FROM recorte{w}", v).fetchall():
                threading.Thread(target=guardar_recorte, args=(r["id"],),
                                 daemon=True).start()
        return self._j([], 200)

    def do_DELETE(self):
        try:
            return self._do_DELETE()
        except Exception as e:  # noqa: BLE001
            import traceback; traceback.print_exc()
            try:
                return self._j({"error": str(e)}, 500)
            except Exception:
                return

    def _do_DELETE(self):
        u = urlparse(self.path)
        t, q = u.path.split("/")[3], parse_qs(u.query)
        w, v = filtros(q)
        if t == "youtube":
            for r in cx().execute(f"SELECT id, fichero FROM youtube{w}", v).fetchall():
                if r["fichero"]:
                    (YT_DIR / r["fichero"]).unlink(missing_ok=True)
                borrar_ficheros_recorte(cx().execute(
                    "SELECT fichero FROM recorte WHERE youtube_id=?", (r["id"],)).fetchall())
                cx().execute("DELETE FROM recorte WHERE youtube_id=?", (r["id"],))
        if t == "recorte":
            borrar_ficheros_recorte(
                cx().execute(f"SELECT fichero FROM recorte{w}", v).fetchall())
        cx().execute(f"DELETE FROM {t}{w}", v)
        cx().commit()
        return self._j([], 204)


def apagar(srv):
    """Cierra bien y vuelca el WAL cuando llega SIGTERM."""
    def mano(*_):
        print("parando…", flush=True)
        threading.Thread(target=srv.shutdown, daemon=True).start()
    for s in (signal.SIGTERM, signal.SIGINT):
        signal.signal(s, mano)


if __name__ == "__main__":
    cargar()
    n = len(list(AUDIO_DIR.glob(f"*/*.{EXT}"))) if AUDIO_DIR.is_dir() else 0
    print(f"anotador  ->  http://{HOST}:{PUERTO}")
    print(f"  base:  {DB}")
    print(f"  audio: {AUDIO_DIR}  ({n} ficheros .{EXT})"
          + ("" if n else "   [!] sin audio: corre src/web/preparar_audio.py"))
    srv = ThreadingHTTPServer((HOST, PUERTO), H)
    apagar(srv)
    srv.serve_forever()
    cx().execute("PRAGMA wal_checkpoint(TRUNCATE)")
    cx().close()
    print("adios")
