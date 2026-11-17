"""Liest eine Aufnahme aus dem Browser-Assistenten (`prototype/capture/`).

Der Assistent schreibt JSON, in dem die eigentlichen Zahlen als base64 in
einem Binärblock stecken. Diese Datei ist der Schlüssel dazu: ohne sie wäre
die Aufnahme nur eine Datei, die man anschauen kann.

Layout je Bild (little-endian, feste Schrittweite je Block):

    float32   t        Zeit in Sekunden seit Beginn des Schritts
    float32   mat[16]  4x4-Kopfmatrix, zeilenweise
    float32   imu[3]   Telefonlage alpha/beta/gamma in Grad, NaN = unbekannt
    uint8[n]  bs       Mimik-Werte, 0..255 steht für 0..1
    –         0..1 Byte Füllung, damit die Punkte an einer geraden Adresse
                   beginnen (eine int16-Sicht verlangt das)
    int16[3m] punkte   Messpunkte x,y,z je MENGE (16384 Einheiten auf 1.0)

Warum die Messpunkte als int16: 478 Punkte × 3 Zahlen × 30 Bilder je Sekunde
sind als Text in einer Minute zweistellig megabytegroß und bestehen fast nur
aus Ziffern. Als int16 sind es 2,9 kB je Bild — und die Auflösung von 6e-5
der Bildbreite liegt weit unter einem Pixel, kostet also nichts.

Start:
    /tmp/qrenv/bin/python tools/lese_capture.py pfad/zur/aufnahme.json
"""

import base64
import json
import struct
import sys

import numpy as np


def lade_pfad(pfad: str) -> dict:
    with open(pfad, encoding="utf-8") as fh:
        return json.load(fh)


def block_lesen(block: dict, n_kanaele: int) -> dict:
    """Ein Block (= ein Aufnahme-Schritt) -> Zahlen.

    Gelesen wird BILDWEISE, genau wie der Assistent schreibt: alle Felder
    eines Bildes hintereinander, dann das nächste. Spaltenweise zu lesen
    (erst alle Zeiten, dann alle Matrizen …) wäre der naheliegende Fehler —
    er fällt nicht auf, solange man nur die Länge prüft, und liefert
    vollständigen Unsinn, sobald man die Zahlen ansieht.
    """
    roh = base64.b64decode(block["daten"])
    n = block["bilder"]
    m = block["punkte"]                       # Zahl der Messpunkte, 0 = keine
    n_pad = n_kanaele + (n_kanaele % 2)       # Füllbyte wie im Schreiber
    schritt = 4 + 64 + 12 + n_pad + 6 * m
    if len(roh) != n * schritt:
        raise ValueError("Block %r: %d Byte, erwartet %d x %d = %d"
                         % (block.get("schritt"), len(roh), n, schritt,
                            n * schritt))

    # Ein strukturierter dtype liest gemischte Typen an beliebigen Offsets
    # in EINEM Durchgang -- ohne ihn müßte man jedes Feld einzeln mit
    # frombuffer und eigener Schrittweite holen.
    felder = [("t", "<f4", 0), ("mat", "<f4", (16,), 4),
              ("imu", "<f4", (3,), 68), ("bs", "u1", (n_kanaele,), 80)]
    if m:
        felder.append(("punkte", "<i2", (m, 3), 80 + n_pad))
    dt = np.dtype({"names": [f[0] for f in felder],
                   "formats": [f[1] if len(f) == 3 else (f[1], f[2])
                               for f in felder],
                   "offsets": [f[-1] for f in felder],
                   "itemsize": schritt})
    a = np.frombuffer(roh, dtype=dt, count=n)
    menge = float(block.get("menge", 16384))
    return {
        "t": a["t"].astype(np.float64),
        "bs": a["bs"].astype(np.float64) / 255.0,
        "mat": a["mat"].astype(np.float64),
        "imu": a["imu"].astype(np.float64),
        "punkte": (a["punkte"].astype(np.float64) / menge
                   if m else np.zeros((n, 0, 3))),
    }


def bericht(paket: dict) -> None:
    namen = paket["kanaele"]["namen"]
    n = len(namen)
    print("Format %s, Schema %d, erzeugt %s"
          % (paket.get("format"), paket.get("schemaVersion"),
             paket.get("zeitstempel")))
    print("%d Kanaele, %d Bilder gesamt, %d Bloecke"
          % (n, paket.get("bilder_gesamt", 0), len(paket.get("bloecke", []))))
    print()

    for block in paket.get("bloecke", []):
        d = block_lesen(block, n)
        print("Schritt %-14s %4d Bilder, %4d Punkte, %.1f s"
              % (block["schritt"], block["bilder"], block["punkte"],
                 float(d["t"][-1]) if len(d["t"]) else 0.0))
        if block["art"] == "neutral" and len(d["bs"]):
            streuung = d["bs"].std(axis=0)
            print("            Ruhe-Zittern: groesste Streuung %.4f "
                  "(Ziel <= 0,008 nach docs/04 7)"
                  % float(streuung.max()))

    print("\nKalibrierung (Ruhe -> Max, Abstand):")
    schwach = []
    for k in paket.get("kalibrierung", []):
        ab = k.get("abstand")
        if ab is None:
            continue
        if k.get("schwach_messbar"):
            schwach.append(k["kanal"])
    gut = [k for k in paket.get("kalibrierung", [])
           if not k.get("schwach_messbar") and k.get("abstand") is not None]
    print("  %d Kanaele messbar (Abstand >= 0,15), %d schwach"
          % (len(gut), len(schwach)))
    if gut:
        beste = sorted(gut, key=lambda k: -k["abstand"])[:8]
        print("  staerkste: " + ", ".join(
            "%s %.2f" % (k["kanal"], k["abstand"]) for k in beste))
    if schwach:
        print("  schwach:   " + ", ".join(schwach[:16])
              + (" …" if len(schwach) > 16 else ""))

    if paket.get("einzelbilder"):
        print("\n%d Einzelbilder (JPEG, base64)" % len(paket["einzelbilder"]))


def haupt(argv) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    paket = lade_pfad(argv[1])
    bericht(paket)
    return 0


if __name__ == "__main__":
    sys.exit(haupt(sys.argv))
