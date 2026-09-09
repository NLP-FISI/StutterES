# Arquitectura del anotador

Todo corre en un solo servidor. Para desplegarlo, ver `../deploy/README.md`.

```
navegador ──▶ /            web (html, css, js, sin dependencias)
              /data/*.json oraciones y formas de onda   (8 MB)
              /audio/*     lecturas en opus             (227 MB)
              /fragmento/* recortes con ffmpeg
              /rest/v1/*   API sobre SQLite
```

Hace falta `ffmpeg` para los recortes y `yt-dlp` para bajar audio de YouTube;
yt-dlp se busca primero en `bin/`, junto al repo.

## Audio comprimido

Las lecturas se sirven en Opus 24 kbps mono: 2,4 GB pasan a 227 MB y una
lectura son 349 KB en vez de 3,6 MB. El dataset no pierde nada, porque los
cortes finales salen siempre de los WAV originales con `src/web/exportar.py`,
a partir de la muestra exacta de cada oracion. La copia comprimida es solo
para escuchar.

## Forma de onda precalculada

Decodificar audio desde JS obliga a descargar la lectura entera y a cargar una
libreria de ondas. En su lugar `build_web.py` deja la envolvente de cada
oracion en `public/data/` (400 valores, base64) y la web la dibuja en un
canvas propio.

## Ficheros

| archivo | que hace |
|---|---|
| `server.py` | web, API, SQLite, audio y recortes |
| `youtube.py` | baja el audio de un video y le calcula la onda |
| `public/` | la interfaz |
| `public/data/` | lo que genera `src/web/build_web.py` |

## Probar en local

```bash
python3 web/server.py      # http://127.0.0.1:8765
```

Es el mismo proceso que corre en el servidor. La base queda en
`web/anotador.db`; borrala para empezar de cero.

## Como se anota

- **clic** en la onda suena desde ahi, como una nota de voz; **arrastrando**
  el fondo se mueve el cursor.
- **doble clic** pone una marca de 3 s del tipo activo, o el boton
  *marcar en el cursor*.
- **clic** en una marca la selecciona y la oye entera; **arrastrandola** se
  mueve. Se pueden solapar las que haga falta.
- Cada marca y cada clip de 3 s llevan su reproductor: el servidor recorta ese
  trozo con ffmpeg y lo cachea.
- Teclado: `espacio` reproducir, `1`-`5` tipo, `c`/`p`/`d` estado, `j`/`k`
  navegar, `supr` borrar la marca seleccionada.

La duracion nunca se teclea: el usuario elige donde empieza y el servidor
fuerza los 3 s. Si una oracion dura menos de 3 s, la marca es la oracion
entera.

## Audios de YouTube

El boton *YouTube* de la cabecera abre una vista aparte del anotador: se pega
un enlace, se le pone nombre y el servidor baja el audio en un hilo, lo pasa a
opus mono y le calcula la onda. La descarga queda en el historial con su
estado, y la web lo consulta cada pocos segundos hasta que termina.

Sobre la onda del video los cortes son libres, sin tipos ni disfluencias:

- **doble clic** corta los segundos que diga la casilla de duracion.
- **arrastrar** elige el trozo a mano.
- cada recorte se renombra, se ajusta por inicio y duracion, se escucha en su
  reproductor y se descarga con el boton `↓`.

Borrar un video se lleva su fichero y sus recortes.
