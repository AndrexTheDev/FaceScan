"""`.fscan` — das Projektformat (docs/06, Abschnitt 2).

Ein ZIP, in dem ein ganzer Scan liegt: Geometrie, Rig, Texturen, Clips,
Prüfbericht. Verlustfrei und wiederöffnbar — das ist der Unterschied zu
einem Export. Ein Export ist eine Ansicht für ein anderes Programm; das
Projekt ist das, wovon alle Exporte gemacht werden.

**Warum jede Datei eine Prüfsumme bekommt.** Der Container ist ein ZIP, und
ein ZIP übersteht eine teilweise Beschädigung erstaunlich gut: ein Byte
kippt, das Archiv öffnet sich trotzdem, und man merkt es erst, wenn die
Nase auf dem Kopf sitzt. `manifest.json` hält deshalb den SHA-256 über
JEDE Datei — auch über sich selbst nicht, aber über alle anderen.

**Warum die Binärdateien ihren Kopf selbst mitbringen.** docs/06 sagt
„int16 mit Scale im JSON". Stünde die Skalierung in einer zweiten Datei,
wäre das Netz ohne sie wertlos — und genau die Datei geht verloren, wenn
jemand „nur die Geometrie" weitergeben will. Deshalb steht ein kurzer
JSON-Kopf VOR den Zahlen, in derselben Datei.

**Warum pro Achse skaliert wird.** docs/06 sagt „Scale", Einzahl. Ein Kopf
ist 220 mm breit, 213 hoch, 230 tief — da fällt es nicht auf. Ein Körper
ist 1,80 m × 0,50 m × 0,30 m: mit einem gemeinsamen Faktor für alle Achsen
verschenkt man auf Y und Z je gut zwei Bit und bekommt dafür auf X eine
Genauigkeit, die niemand braucht. Drei Faktoren kosten nichts.

**Was absichtlich fehlt.** Nicht jede Zeile des Baums in docs/06 kann der
Prototyp füllen: `base_head.bin` braucht eine registrierte Basistopologie
(NRICP), `blendshape_calib.json` eine echte Nutzer-Kalibrierung (F-402),
`c2pa_manifest.c2pa` einen Signaturschlüssel, `license.json` ein Entitlement,
und `hair_cards`/`hair_strands` setzen Haar-Stufe L2/L3 voraus. Der Schreiber
läßt diese Einträge WEG und `inventar()` sagt, welche das sind. Eine leere
Platzhaltter-Datei wäre schlimmer als keine: sie behauptet einen Inhalt, den
es nicht gibt.
"""

from __future__ import annotations

import hashlib
import json
import struct
import zipfile

import numpy as np

SCHEMA_VERSION = 1

# Feste Zeit: sonst ist kein Lauf mit dem nächsten vergleichbar. Wer die
# echte Erzeugungszeit will, gibt `zeitstempel` mit.
ZIP_DATUM = (1980, 1, 1, 0, 0, 0)
ZEITSTEMPEL = "1980-01-01T00:00:00Z"

# Der Baum, wie ihn docs/06 (2) beschreibt. `pflicht` heißt nicht "die Datei
# muss da sein", sondern "die Spec führt sie auf" — `inventar()` trennt
# danach, was gefüllt ist und was fehlt.
INHALT_VERZEICHNIS = [
    ("manifest.json", True),
    ("meta.json", True),
    ("capture/calibration.json", True),
    ("capture/perception.bin", True),
    ("capture/frames/", False),
    ("geometry/mesh_skin_hi.bin", True),
    ("geometry/mesh_skin_lod0.bin", True),
    ("geometry/mesh_skin_lod1.bin", True),
    ("geometry/mesh_skin_lod2.bin", True),
    ("geometry/mesh_skin_lod3.bin", True),
    ("geometry/hair_cap.bin", True),
    ("geometry/hair_cards.bin", False),
    ("geometry/hair_strands.bin", False),
    ("geometry/scalp_uv.bin", True),
    ("geometry/tsdf_meta.json", True),
    ("rig/base_head.bin", False),
    ("rig/skeleton.json", True),
    ("rig/weights.bin", True),
    ("rig/blendshapes/", True),
    ("rig/blendshape_calib.json", False),
    ("rig/morph_names.json", True),
    ("textures/basecolor.png", True),
    ("textures/uv_meta.json", True),
    ("animation/clips/", True),
    ("animation/library.json", True),
    ("qa/report.json", True),
    ("qa/thumb.png", False),
    ("provenance/third_party.json", True),
    ("provenance/c2pa_manifest.c2pa", False),
    ("license.json", False),
]

MAGIE = b"FSMB"          # FaceScan Mesh Binary


# ------------------------------------------------------------ Geometrie ---

def quantisieren(v: np.ndarray, bits: int = 16) -> tuple[np.ndarray, list, list]:
    """Punkte -> int16 je Achse, mit Skalierung und Versatz.

    Der Wertebereich kommt aus den DATEN. Rückgabe: gestufte Punkte,
    drei Skalierungen, drei Versätze. Der größte Fehler ist eine halbe
    Stufe — bei 16 Bit und 280 mm Ausdehnung sind das 0,002 mm, also
    weit unter dem, was der Scan selbst kann (~0,3 mm).
    """
    v = np.asarray(v, dtype=float)
    lo, hi = v.min(axis=0), v.max(axis=0)
    mitte = 0.5 * (lo + hi)
    stufen_zahl = 2 ** int(bits) - 1
    spanne = np.maximum(hi - lo, 1e-9)
    skalierung = spanne / stufen_zahl
    halb = stufen_zahl // 2
    q = np.clip(np.round((v - mitte) / skalierung), -halb, halb).astype(np.int16)
    return q, [float(x) for x in skalierung], [float(x) for x in mitte]


def mesh_bin(v: np.ndarray, f: np.ndarray, uv: np.ndarray | None = None) -> bytes:
    """Netz als Binärblock: JSON-Kopf, dann int16-Punkte, uint32-Dreiecke,
    optional uint16-UV.

    Die Dreiecke bleiben UNVERÄNDERT: eine Zahl, die nur zählt, gewinnt
    durch Quantisieren nichts und verliert durch Runden alles.
    """
    v = np.asarray(v, dtype=float)
    f = np.asarray(f, dtype=np.int64).reshape(-1, 3)
    # Eine Punktwolke hat keine Dreiecke. Das ist kein Fehler, sondern das,
    # was `scalp_uv.bin` ist: Punkte mit UV, ohne Fläche.
    if len(f) and f.max() >= len(v):
        raise ValueError("Dreieck zeigt auf Punkt %d, es gibt nur %d"
                         % (int(f.max()), len(v)))
    q, skal, mitte = quantisieren(v)
    kopf = {
        "schemaVersion": SCHEMA_VERSION,
        "vertices": int(len(v)),
        "faces": int(len(f)),
        "vertex": {"dtype": "int16", "komponenten": 3,
                   "skalierung": skal, "versatz": mitte,
                   "einheit": "mm"},
        "index": {"dtype": "uint32", "komponenten": 3},
        "uv": uv is not None,
    }
    if uv is not None:
        uv = np.clip(np.asarray(uv, dtype=float), 0.0, 1.0)
        kopf["uv_quant"] = {"dtype": "uint16", "komponenten": 2,
                            "skalierung": 1.0 / 65535.0, "versatz": [0.0, 0.0]}
    roh = json.dumps(kopf, separators=(",", ":")).encode("utf-8")
    teile = [MAGIE, struct.pack("<I", len(roh)), roh,
             q.astype("<i2").tobytes(), f.astype("<u4").tobytes()]
    if uv is not None:
        teile.append(np.round(uv * 65535.0).astype("<u2").tobytes())
    return b"".join(teile)


def lese_mesh_bin(b: bytes) -> dict:
    """Binärblock -> Netz. Gibt Punkte, Dreiecke, UV und den Kopf zurück."""
    if b[:4] != MAGIE:
        raise ValueError("kein FaceScan-Mesh-Block")
    (n_head,) = struct.unpack_from("<I", b, 4)
    kopf = json.loads(b[8:8 + n_head].decode("utf-8"))
    anfang = 8 + n_head
    n, m = kopf["vertices"], kopf["faces"]
    q = np.frombuffer(b[anfang:anfang + n * 6], dtype="<i2").reshape(n, 3)
    anfang += n * 6
    f = np.frombuffer(b[anfang:anfang + m * 12], dtype="<u4").reshape(m, 3)
    anfang += m * 12
    skal = np.array(kopf["vertex"]["skalierung"])
    vers = np.array(kopf["vertex"]["versatz"])
    v = q.astype(float) * skal + vers
    uv = None
    if kopf.get("uv"):
        uv = np.frombuffer(b[anfang:anfang + n * 4],
                           dtype="<u2").reshape(n, 2) / 65535.0
    return {"v": v, "f": f.astype(np.int64), "uv": uv, "kopf": kopf,
            "stufen": int(np.abs(skal).max() * 0.5 / 2 ** 15 * 2 ** 15)}


def weights_bin(idx: np.ndarray, w: np.ndarray, n_gelenke: int) -> bytes:
    """Hautgewichte: uint16-Gelenknummern plus uint8-Gewichte, je Punkt vier.

    Die GEWICHTE sind uint8 (0..255 steht für 0..1) — docs/06 sagt das so,
    und es genügt: ein Gewicht auf 1/255 genau zu kennen ist 40-mal genauer
    als die Glättung, die es erzeugt hat. Die Gelenknummern sind uint16,
    weil uint8 bei mehr als 255 Gelenken stillschweigend umläuft — und ein
    Ganzkörper-Rig mit Fingern kommt darüber.
    """
    idx = np.asarray(idx, dtype=np.int64)
    w = np.asarray(w, dtype=float)
    if idx.shape != w.shape:
        raise ValueError("Gelenknummern %s und Gewichte %s passen nicht"
                         % (idx.shape, w.shape))
    if idx.max() >= n_gelenke:
        raise ValueError("Gelenknummer %d, es gibt nur %d"
                         % (int(idx.max()), n_gelenke))
    if idx.max() > 65535:
        raise ValueError("mehr als 65536 Gelenke sind nicht darstellbar")
    kopf = {
        "schemaVersion": SCHEMA_VERSION,
        "punkte": int(idx.shape[0]),
        "einfluesse": int(idx.shape[1]),
        "gelenke": int(n_gelenke),
        "index": {"dtype": "uint16"},
        "gewicht": {"dtype": "uint8", "skalierung": 1.0 / 255.0},
    }
    roh = json.dumps(kopf, separators=(",", ":")).encode("utf-8")
    g = np.round(w * 255.0).astype(np.int32)

    # Vier gerundete Achtel zusammengezählt ergeben nicht mehr 255, sondern
    # bis zu zwei daneben. Ließe man das stehen, summieren die Gewichte
    # eines Punktes nicht mehr auf 1 -- und dann WANDERT das Netz beim
    # Abspielen, obwohl es stillstehen soll: die Gelenke ziehen mit leicht
    # zu viel Gesamtkraft. Der Rest kommt deshalb auf den größten Einfluß;
    # der ist mindestens 255/4 = 64, der Rest höchstens 2, es kann also
    # nichts überlaufen.
    rest = 255 - g.sum(axis=1)
    groesstes = g.argmax(axis=1)
    g[np.arange(g.shape[0]), groesstes] += rest
    if g.min() < 0 or g.max() > 255:
        raise ValueError("Gewichte lassen sich nicht auf 255 normieren")
    g = g.astype(np.uint8)
    return (MAGIE + struct.pack("<I", len(roh)) + roh
            + idx.astype("<u2").tobytes() + g.tobytes())


def lese_weights_bin(b: bytes) -> dict:
    """Binärblock -> Gelenknummern und Gewichte."""
    if b[:4] != MAGIE:
        raise ValueError("kein FaceScan-Block")
    (n_head,) = struct.unpack_from("<I", b, 4)
    kopf = json.loads(b[8:8 + n_head].decode("utf-8"))
    anfang = 8 + n_head
    n, k = kopf["punkte"], kopf["einfluesse"]
    idx = np.frombuffer(b[anfang:anfang + n * k * 2],
                        dtype="<u2").reshape(n, k)
    anfang += n * k * 2
    w = np.frombuffer(b[anfang:anfang + n * k],
                      dtype=np.uint8).reshape(n, k).astype(float) / 255.0
    return {"idx": idx.astype(np.int64), "w": w, "kopf": kopf}


def deltas_bin(deltas: np.ndarray) -> bytes:
    """Blendshape-Verschiebungen: int16 je Achse, eine gemeinsame Skalierung.

    Eine gemeinsame Skalierung für alle drei Achsen ist hier RICHTIG — im
    Gegensatz zu den Punkten. Würde jede Achse ihren eigenen Faktor
    bekommen, hinge die Stärke einer Mimik davon ab, in welche Richtung sie
    zeigt. Ein Lächeln nach links wäre dann stärker als eines nach rechts.
    """
    d = np.asarray(deltas, dtype=float)
    groesstes = float(np.abs(d).max()) or 1.0
    skalierung = groesstes / 32767.0
    kopf = {
        "schemaVersion": SCHEMA_VERSION,
        "punkte": int(d.shape[0]),
        "komponenten": 3,
        "dtype": "int16",
        "skalierung": float(skalierung),
        "einheit": "mm",
    }
    roh = json.dumps(kopf, separators=(",", ":")).encode("utf-8")
    q = np.clip(np.round(d / skalierung), -32767, 32767).astype(np.int16)
    return MAGIE + struct.pack("<I", len(roh)) + roh + q.astype("<i2").tobytes()


def lese_deltas_bin(b: bytes) -> np.ndarray:
    """Binärblock -> Verschiebungen."""
    if b[:4] != MAGIE:
        raise ValueError("kein FaceScan-Block")
    (n_head,) = struct.unpack_from("<I", b, 4)
    kopf = json.loads(b[8:8 + n_head].decode("utf-8"))
    anfang = 8 + n_head
    n = kopf["punkte"]
    q = np.frombuffer(b[anfang:anfang + n * 6], dtype="<i2").reshape(n, 3)
    return q.astype(float) * kopf["skalierung"]


# ------------------------------------------------------------ Container ---

def write_fscan(path: str, dateien: dict[str, bytes], *,
                name: str = "FaceScan", notizen: str = "",
                erzeuger: str = "FaceScan Prototyp (Referenz-Python)",
                zeitstempel: str = ZEITSTEMPEL,
                person: str = "", tags: list | None = None) -> dict:
    """Schreibt ein `.fscan`-Projekt.

    `dateien` ist ein Dict `Name im Container -> Inhalt`. Was nicht drin
    steht, fehlt — es werden keine Platzhalter erzeugt.
    """
    if "manifest.json" in dateien or "meta.json" in dateien:
        raise ValueError("manifest.json und meta.json entstehen hier selbst")

    meta = {
        "schemaVersion": SCHEMA_VERSION,
        "name": name,
        "notizen": notizen,
        "personKennung": person,        # lokal, keine Cloud, keine Übertragung
        "tags": list(tags or []),
        "favorit": False,
    }
    dateien = dict(dateien)
    dateien["meta.json"] = json.dumps(meta, indent=2,
                                      ensure_ascii=False).encode("utf-8")

    pruefsummen = {n: hashlib.sha256(b).hexdigest()
                   for n, b in sorted(dateien.items())}
    manifest = {
        "format": "FaceScan Project",
        "schemaVersion": SCHEMA_VERSION,
        "erzeuger": erzeuger,
        "zeitstempel": zeitstempel,
        "algorithmus": "sha256",
        "dateien": pruefsummen,
        "eintraege": len(pruefsummen),
        "bytes": int(sum(len(b) for b in dateien.values())),
    }
    dateien["manifest.json"] = json.dumps(manifest, indent=2,
                                          ensure_ascii=False).encode("utf-8")

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for n in sorted(dateien):
            info = zipfile.ZipInfo(n, date_time=ZIP_DATUM)
            # PNGs und JPEGs sind schon komprimiert; ein zweiter Versuch
            # kostet Zeit und bringt nichts.
            info.compress_type = (zipfile.ZIP_STORED
                                  if n.rsplit(".", 1)[-1].lower()
                                  in ("png", "jpg", "jpeg", "m4a")
                                  else zipfile.ZIP_DEFLATED)
            info.external_attr = 0o600 << 16
            z.writestr(info, dateien[n])
    return manifest


def read_fscan(path: str, pruefe: bool = True) -> tuple[dict, dict[str, bytes]]:
    """Liest ein `.fscan` und prüft jede Prüfsumme.

    Der Prüfschritt ist nicht kosmetisch: ein ZIP öffnet sich auch dann
    noch, wenn ein Byte gekippt ist. Ohne Prüfsumme merkt man das erst,
    wenn das Netz im Programm daneben liegt.
    """
    with zipfile.ZipFile(path) as z:
        if "manifest.json" not in z.namelist():
            raise ValueError("kein .fscan: manifest.json fehlt")
        manifest = json.loads(z.read("manifest.json").decode("utf-8"))
        if manifest.get("schemaVersion") != SCHEMA_VERSION:
            raise ValueError("schemaVersion %r wird nicht unterstuetzt"
                             % manifest.get("schemaVersion"))
        dateien = {n: z.read(n) for n in z.namelist()
                   if n != "manifest.json"}
        if pruefe:
            for n, soll in manifest["dateien"].items():
                if n not in dateien:
                    raise ValueError("%s steht im Manifest, fehlt aber im ZIP"
                                     % n)
                ist = hashlib.sha256(dateien[n]).hexdigest()
                if ist != soll:
                    raise ValueError("Pruefsumme von %s stimmt nicht" % n)
    return manifest, dateien


def inventar(dateien: dict[str, bytes]) -> dict:
    """Was liegt im Container, was fehlt — gegen den Baum aus docs/06.

    Rückgabe: `vorhanden`, `fehlend` und `fehlt_pflicht` (Einträge, die die
    Spec aufführt und die ein vollständiger Scan haben sollte). Diese
    Unterscheidung ist der ganze Witz: ein Prototyp, der 25 von 30
    Einträgen füllt, ist ehrlicher als einer, der 30 Einträge füllt und
    fünf davon erfindet.
    """
    namen = set(dateien)
    vorhanden, fehlend, fehlt_pflicht = [], [], []
    for eintrag, pflicht in INHALT_VERZEICHNIS:
        if eintrag.endswith("/"):
            treffer = any(n.startswith(eintrag) for n in namen)
        else:
            treffer = eintrag in namen
        (vorhanden if treffer else fehlend).append(eintrag)
        if not treffer and pflicht:
            fehlt_pflicht.append(eintrag)
    return {"vorhanden": vorhanden, "fehlend": fehlend,
            "fehlt_pflicht": fehlt_pflicht,
            "anteil": round(len(vorhanden) / len(INHALT_VERZEICHNIS), 3)}
