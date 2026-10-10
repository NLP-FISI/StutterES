# Sintesis de habla disfluente

Tres piezas que encajan: la web baja el audio de un video y lo trocea, de esos
trozos se saca la voz de referencia, y XTTS-v2 la clona para leer un texto al
que previamente se le han escrito las disfluencias.

    YouTube  ->  trozos de N s  ->  referencia de voz  ->  XTTS-v2  ->  wav
                                        texto + disfluencias  ^

## 1. Bajar y trocear (en la web)

En la vista **YouTube** del anotador: se pega el enlace, se le pone nombre y se
descarga. Luego, en la ficha del audio:

- **doble clic** en la onda corta un trozo de la duracion del campo
- **arrastrar** elige el trozo a mano
- **Trocear todo** parte el audio entero en trozos seguidos de esa duracion,
  con el solape que se indique

De cada descarga se guardan **dos copias**: un opus de 24 kbps para escuchar en
la web y un **WAV de 24 kHz** para clonar. El opus vale para anotar, pero como
referencia de voz es malo: XTTS reproduciria los artefactos del codec. Los
trozos se cortan siempre del WAV y se guardan en WAV, en
`recortes/<nombre>/NNNN_<nombre>.wav`.

El trozo que sobra al final se descarta si no llega a la mitad de la duracion
pedida: un resto de dos segundos no sirve como referencia. Con `"resto": true`
en la llamada a la API se guarda igual.

Tambien por API:

```bash
curl -X POST -H 'Content-Type: application/json' \
  -d '{"youtube_id":9,"dur_s":10,"solape_s":0,"nombre_base":"mivoz"}' \
  http://127.0.0.1:8765/rest/v1/trocear
```

## 2. Escribir las disfluencias en el texto

XTTS-v2 genera habla **fluida**. La unica palanca es el texto, asi que cada
tipo del corpus se traduce a su forma escrita:

| tipo | se escribe | ejemplo |
|---|---|---|
| SoundRep | repetir la primera silaba | `ma ma magnitud` |
| WordRep | repetir la palabra | `de de magnitud` |
| Prolongation | alargar una continuante | `ssssismo` |
| Block | parada antes de la palabra | `... magnitud` |
| Interjection | muletilla intercalada | `eh, magnitud` |

```bash
# marcas a mano: indice de palabra (desde 0) y tipo
python src/sintesis/disfluencias.py "Sismo de magnitud cuatro en Piura." \
    --marcas 0:Prolongation,2:WordRep
# -> Ssssismo de magnitud magnitud cuatro en Piura.

# o al azar, en una fraccion de las palabras
python src/sintesis/disfluencias.py "La ministra informo del bono." --tasa 0.3 --semilla 7
```

Dos cosas que se cuidan y no son obvias:

- **Los digrafos.** La silaba de "que" es `que`, no `qu`: la u no suena. Sin
  eso, SoundRep daba `qu qu que` y Prolongation `quuuue`.
- **Las mayusculas.** `Ssssismo` se lee como una ese sostenida; `SSSSismo` se
  lee como siglas. Las letras repetidas van siempre en minuscula.
- **Solo continuantes.** Se alargan vocales y `m n ñ l r s f j z`. Una oclusiva
  repetida (`pppperu`) se lee como letras sueltas, no como un sonido sostenido.

### Lo que funciona de verdad, medido

Se sintetizaron varias notaciones con la misma voz y se midio el audio
resultante (transcripcion literal con CTC, silencio mas largo y tramo sonoro
sostenido mas largo):

| tipo | se pidio | sono | |
|---|---|---|---|
| WordRep | `magnitud magnitud` | `magnitud magnitud` | sale |
| SoundRep | `re re reporto` | `rereporto` | sale |
| Prolongation | `ssssismo` | `esesicismo` | **no sale** |
| Block | `... Piura` | `en piura`, sin pausa | **no sale** |

El tramo sostenido mas largo en las variantes de alargamiento fue de 0,02 a
0,06 s, frente a **0,16 s en la voz real** del corpus: XTTS no sostiene nada.
Se probaron `ssismo`, `sssismo`, `s-s-sismo` y `sssss sismo`, y ninguna
funciona; lo unico que cambia es como destroza la palabra.

Con el bloqueo pasa algo parecido: el silencio mas largo fue de 0,54 a 0,58 s
en **todas** las variantes, incluidas las que no llevaban ninguna marca de
pausa, asi que ese silencio es el del final del fichero. Y con `de,` el modelo
leyo la coma en voz alta: "cuatro punto".

Conclusion practica: **por texto solo se pueden meter las repeticiones.** El
alargamiento y el bloqueo, si se necesitan, hay que ponerlos retocando el
audio despues (insertar silencio en la frontera de palabra, o estirar en el
tiempo un solo fonema), no pidiendoselo a XTTS.

Otro detalle: en frases cortas XTTS añade palabras inventadas al final
("cuatrore", "pinton", "fintas"). Conviene sintetizar frases largas y revisar
el final.

### Lo que esto es y lo que no es

Esto imita la **forma** de la disfluencia, no su mecanismo. Un bloqueo real es
una parada con tension articulatoria; escrito con puntos suspensivos sale una
pausa limpia, que no es lo mismo. Un alargamiento sale razonable en vocales y
en /s/, y mal en el resto. Sirve para aumentar datos de entrenamiento; no pasa
por habla disfluente real, y conviene no evaluar un detector solo con esto.

## 3. Clonar la voz

```bash
.venv-tts/bin/python src/sintesis/clonar.py \
    --ref "recortes/mivoz/0001_mivoz_001.wav" \
    --texto "Ssssismo de magnitud magnitud cuatro en Piura." \
    --salida outputs_sintesis/ --acepto-cpml
```

- `--ref` acepta varios ficheros o una carpeta: XTTS promedia el timbre.
- XTTS quiere entre **6 y 30 s** de voz limpia. El script avisa si te quedas
  corto o te pasas.
- `--fichero` en vez de `--texto` para una frase por linea.

### Entorno aparte

`coqui-tts` se instala en `.venv-tts`, **no** en `.venv`. El venv principal lo
usa el pipeline de anotacion con `transformers` 5.x, y coqui-tts mueve esas
versiones. Separarlos evita romper lo que ya funciona.

```bash
python3 -m venv .venv-tts
.venv-tts/bin/pip install coqui-tts
```

### Licencia

XTTS-v2 va bajo la **Coqui Public Model License**, que es solo para uso **no
comercial**. El script no la acepta por ti: hay que pasar `--acepto-cpml` o
poner `COQUI_TOS_AGREED=1`. Para una tesis no hay problema; para cualquier uso
comercial, no vale.

### Velocidad

Sin GPU, cuenta unos pocos segundos de proceso por segundo de audio generado,
y la primera vez baja ~1,8 GB de modelo. `--hilos` controla los nucleos.
