import pandas as pd

from config import OUT_DIR, SPLIT_RATIOS

SPLITS = ["train", "val", "test"]
ORDEN = ["Prolongation", "Block", "SoundRep", "WordRep", "Interjection", "NoStutteredWords"]


def pct(tabla):
    return (tabla / tabla.sum() * 100).round(2)


def bloque(titulo, texto, out):
    out.append(f"\n{'=' * 78}\n{titulo}\n{'=' * 78}\n{texto}")


def main():
    df = pd.read_csv(OUT_DIR / "split.csv")
    df["split"] = pd.Categorical(df.split, SPLITS, ordered=True)
    df["label"] = pd.Categorical(df.label, ORDEN, ordered=True)
    out = []

    tam = df.split.value_counts().reindex(SPLITS)
    bloque("1. TAMAÑO DE CADA PARTICIÓN",
           pd.DataFrame({"clips": tam, "%": pct(tam),
                         "objetivo %": [SPLIT_RATIOS[s] * 100 for s in SPLITS]}).to_string(), out)

    t = pd.crosstab(df.Show, df.split)
    t["TOTAL"] = t.sum(axis=1)
    bloque("2. SPEAKERS — clips por partición", t.to_string(), out)
    bloque("2b. SPEAKERS — distribución dentro de cada partición (%)",
           pd.concat([pct(pd.crosstab(df.Show, df.split)),
                      pct(df.Show.value_counts()).rename("TOTAL")], axis=1).to_string(), out)

    t = pd.crosstab(df.label, df.split)
    t["TOTAL"] = t.sum(axis=1)
    bloque("3. DISFLUENCIAS (etiqueta primaria) — clips por partición", t.to_string(), out)
    bloque("3b. DISFLUENCIAS — distribución dentro de cada partición (%)",
           pd.concat([pct(pd.crosstab(df.label, df.split)),
                      pct(df.label.value_counts()).rename("TOTAL")], axis=1).to_string(), out)

    # Aquí un clip con varias anotaciones cuenta en cada una de sus clases.
    filas = []
    for c in ORDEN:
        m = df[df[c] > 0]
        fila = m.split.value_counts().reindex(SPLITS).to_dict()
        fila.update(clase=c, TOTAL=len(m))
        filas.append(fila)
    ml = pd.DataFrame(filas).set_index("clase")[SPLITS + ["TOTAL"]]
    bloque("4. DISFLUENCIAS (multi-etiqueta: todas las anotaciones del clip)", ml.to_string(), out)

    bloque("5. CRUCE SPEAKER x DISFLUENCIA — general",
           pd.crosstab(df.Show, df.label, margins=True, margins_name="TOTAL").to_string(), out)
    for n, s in enumerate(SPLITS, 1):
        sub = df[df.split == s]
        bloque(f"5.{n} CRUCE SPEAKER x DISFLUENCIA — {s.upper()}",
               pd.crosstab(sub.Show, sub.label, margins=True, margins_name="TOTAL").to_string(), out)

    ver = []
    for eje, col in [("speaker", "Show"), ("disfluencia", "label")]:
        g = pct(pd.crosstab(df[col], df.split))
        ref = pct(df[col].value_counts()).reindex(g.index)
        ver.append(f"  {eje:12s}: desviación máx. vs. distribución global = "
                   f"{g.sub(ref, axis=0).abs().max().max():.2f} pp")
    cruce = df.Show.astype(str) + " | " + df.label.astype(str)
    g = pct(pd.crosstab(cruce, df.split))
    ref = pct(cruce.value_counts()).reindex(g.index)
    ver.append(f"  {'conjunto':12s}: desviación máx. vs. distribución global = "
               f"{g.sub(ref, axis=0).abs().max().max():.2f} pp")
    bloque("6. VERIFICACIÓN DE LA ESTRATIFICACIÓN", "\n".join(ver), out)

    texto = "\n".join(out)
    print(texto)
    (OUT_DIR / "estadisticas.txt").write_text(texto, encoding="utf-8")


if __name__ == "__main__":
    main()
