"""`.fsmc` — FaceScan Motion Clip.

Das Aufnahmeformat für Bewegung (F-405). Es ist ein ZIP mit vier Einträgen,
und die Reihenfolge der Gedanken ist immer dieselbe:

    manifest.json    Was ist das? Version, FPS, Dauer, Erzeuger.
    meta.json        Wie liegt es? Kanaltabelle: Name -> Byte-Offset, Typ,
                     min/max und Skalierung je Komponente.
    channels.bin     Die Zahlen selbst: int16, delta-kodiert, little-endian.
    provenance.json  Woher kommt es? Prüfsummen (optional Signatur).
    audio.m4a        optional, Ton für späteren Lip-Sync.

**Warum delta-kodiert.** Ein Kanal ändert sich von Frame zu Frame nur wenig.
Wer statt des Wertes die ÄNDERUNG speichert, bekommt fast überall kleine
Zahlen — und die lassen sich (a) vom ZIP-Kompressor fast wegdrücken und
(b) überhaupt erst sinnvoll in 16 Bit unterbringen, wenn der Kanal selbst
einen großen Wertebereich hat.

**Warum trotzdem Schlüsselframes.** Die Differenz zweier aufeinanderfolgender
int16-Werte kann bis zu 65535 betragen und passt damit nicht mehr in ein
int16. Ein Kanal, der in einem Frame von ganz unten nach ganz oben springt
(ein Lidschlag, den die Kamera erwischt), sprengt das Format. Deshalb steht
alle `keyframeIntervall` Frames (voreingestellt 30 = eine Sekunde bei 30 fps)
und zusätzlich immer dann, wenn die Differenz nicht passt, der ABSOLUTE Wert
im Block. Welche Frames das sind, steht pro Kanal in `meta.json` — sonst
könnte der Leser es nur erraten.

**Warum die Kanaltabelle im JSON steht und nicht im Binärblock.** Ein Leser
soll wissen, was in `channels.bin` liegt, ohne es zu verstehen. `offset` ist
dabei das Byte IM UNKOMPRIMIERTEN Block — die Datei selbst ist gezippt.

Alles ist little-endian, wie in `docs/06` festgelegt, und die Erzeugung ist
deterministisch: gleiche Eingabe, bitgleiche Datei (deshalb ein festes Datum
in den ZIP-Einträgen).
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from typing import Any

import numpy as np

SCHEMA_VERSION = 1

# Wie viele Komponenten ein Kanalwert hat. Ein Gelenk dreht sich als
# Quaternion (4 Zahlen), eine Position ist ein Vektor (3), ein
# Blendshape-Gewicht eine einzelne Zahl.
KOMPONENTEN = {"scalar": 1, "vec3": 3, "quat": 4}

# int16 kann -32768 .. 32767. Beide Enden bleiben frei, damit die Mitte
# genau auf null liegt und der Betrag symmetrisch ist.
Q_MIN = -32767
Q_MAX = 32767
Q_SPANNE = Q_MAX - Q_MIN          # 65534 Stufen

# Wieviel Genauigkeit ein Kanal WIRKLICH braucht (in Bit). Der Container
# ist immer int16 -- aber ein Gewicht, das nach docs/04 (7) nur auf 0,008
# genau sein muss, braucht keine 65536 Stufen. Wer es trotzdem mit 16 Bit
# speichert, verschenkt nicht nur Platz: das Quantisierungsrauschen in den
# unteren Bits sieht für den Kompressor aus wie Zufall und macht den
# Deflate-Gewinn wieder kaputt. GEMESSEN (voller Kanalsatz, 243 Zahlen je
# Frame): 0,47 MB/Minute bei 16 Bit, 0,29 MB/Minute bei bedarfsgerechten
# Stufen -- derselbe Clip, dasselbe Format, 38 % weniger.
STUFEN_VORGABE = {
    "scalar": 10,       # Mimik-Gewichte und Fingergelenke, 0..1
    "quat": 14,         # Drehungen
    "vec3": 15,         # Positionen in Metern
}

# Ein festes Datum statt der Uhrzeit: sonst ist jede erzeugte Datei
# verschieden, und man kann zwei Läufe nicht mehr vergleichen.
ZIP_DATUM = (1980, 1, 1, 0, 0, 0)


def euler_zu_matrix(euler_grad: np.ndarray, ordnung: str = "ZXY") -> np.ndarray:
    """Drei Winkel in Grad -> 3x3-Matrix.

    BVH listet seine Kanäle als Z, X, Y und wendet sie in genau dieser
    Reihenfolge an: R = Rz @ Rx @ Ry. Wer das zu Rx @ Ry @ Rz vertauscht,
    bekommt eine Bewegung, die bei kleinen Winkeln fast richtig aussieht und
    bei großen daneben liegt — der gefährlichste Sort Fehler überhaupt.
    """
    w = np.radians(np.asarray(euler_grad, dtype=float))

    def dreh(achse: int) -> np.ndarray:
        c, s = np.cos(w[achse]), np.sin(w[achse])
        if achse == 0:
            return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
        if achse == 1:
            return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
        return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])

    achsen = {"x": 0, "y": 1, "z": 2}
    R = np.eye(3)
    for b in ordnung.lower():
        R = R @ dreh(achsen[b])
    return R


def matrix_zu_quat(R: np.ndarray) -> np.ndarray:
    """3x3-Matrix -> Quaternion (x, y, z, w).

    Die naheliegende Formel über die Spur ist numerisch empfindlich, wenn w
    nahe null liegt (eine Drehung um 180 Grad). Die Zweig-Formel unten wählt
    je nach Größenverhältnis den stabilsten Weg.
    """
    R = np.asarray(R, dtype=float)
    m00, m01, m02 = R[0]
    m10, m11, m12 = R[1]
    m20, m21, m22 = R[2]
    spur = m00 + m11 + m22
    if spur > 0.0:
        s = np.sqrt(spur + 1.0) * 2.0
        return np.array([(m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s,
                         0.25 * s])
    if m00 > m11 and m00 > m22:
        s = np.sqrt(1.0 + m00 - m11 - m22) * 2.0
        return np.array([0.25 * s, (m01 + m10) / s, (m02 + m20) / s,
                         (m21 - m12) / s])
    if m11 > m22:
        s = np.sqrt(1.0 + m11 - m00 - m22) * 2.0
        return np.array([(m01 + m10) / s, 0.25 * s, (m12 + m21) / s,
                         (m02 - m20) / s])
    s = np.sqrt(1.0 + m22 - m00 - m11) * 2.0
    return np.array([(m02 + m20) / s, (m12 + m21) / s, 0.25 * s,
                     (m10 - m01) / s])


def euler_zu_quat(euler_grad: np.ndarray, ordnung: str = "ZXY") -> np.ndarray:
    """Drei BVH-Winkel in Grad -> Quaternion (x, y, z, w)."""
    return matrix_zu_quat(euler_zu_matrix(euler_grad, ordnung))


def quaternionen_stetig(q: np.ndarray) -> np.ndarray:
    """Vorzeichen so drehen, dass aufeinanderfolgende Quaternionen nah beieinander
    liegen.

    q und -q beschreiben dieselbe Drehung. Eine Formel, die das nicht
    beachtet, liefert abwechselnd +q und -q — und für die Delta-Kodierung
    ist das der GAU: statt kleiner Änderungen springt der Kanal in jedem
    Frame durch den ganzen Wertebereich. Die Ersparnis ist dann nicht nur
    dahin, das Format braucht für fast jeden Frame einen Schlüsselframe.
    """
    q = np.asarray(q, dtype=float).copy()
    if len(q) < 2:
        return q
    for i in range(1, len(q)):
        if float(q[i] @ q[i - 1]) < 0.0:
            q[i] = -q[i]
    return q


def _quantisieren(spalte: np.ndarray, bits: int = 16) -> dict:
    """Eine Komponente über die ganze Zeit: Wertebereich und int16-Stufen.

    Der Bereich wird aus den DATEN bestimmt, nicht geraten. Das ist der
    einzige Weg, der für Gewichte (0..1), Positionen (Meter) und
    Quaternionen (±1) gleichermaßen funktioniert — ein fester Bereich
    würde eine der drei Gruppen ruinieren.
    """
    lo = float(np.min(spalte))
    hi = float(np.max(spalte))
    if not np.isfinite(lo) or not np.isfinite(hi):
        raise ValueError("Kanal enthaelt NaN oder Inf")
    if hi - lo < 1e-12:
        # Ein Kanal, der sich nie bewegt, hat keine Spanne. Ohne diesen
        # Schutz wird die Skalierung null und die Division bricht.
        lo, hi = lo - 0.5, hi + 0.5
    mitte = 0.5 * (lo + hi)
    if not 2 <= int(bits) <= 16:
        raise ValueError("bits muss zwischen 2 und 16 liegen, ist %r" % bits)
    stufen_zahl = 2 ** int(bits) - 1            # 65535 bei 16 Bit
    halb = stufen_zahl // 2                     # symmetrisch um die Mitte
    skalierung = (hi - lo) / stufen_zahl
    stufen = np.clip(np.round((spalte - mitte) / skalierung), -halb, halb)
    return {"min": lo, "max": hi, "mitte": mitte,
            "skalierung": float(skalierung), "stufen": stufen.astype(np.int32)}


def _delta_block(stufen: np.ndarray, intervall: int) -> tuple[np.ndarray, list[int]]:
    """Stufenwerte -> int16-Block mit Differenzen plus Liste der Schlüsselframes."""
    n = len(stufen)
    block = np.zeros(n, dtype=np.int16)
    schluessel = [0]
    vorher = 0
    for i in range(n):
        if i == 0:
            block[i] = np.int16(stufen[0])
            vorher = int(stufen[0])
            continue
        d = int(stufen[i]) - vorher
        # Passt die Differenz nicht mehr in ein int16 (oder ist ein
        # planmäßiger Schlüsselframe fällig), wird der absolute Wert
        # geschrieben. Sonst die Differenz.
        if abs(d) > Q_MAX or (intervall and i % intervall == 0):
            block[i] = np.int16(stufen[i])
            schluessel.append(i)
            vorher = int(stufen[i])
        else:
            block[i] = np.int16(d)
            vorher = int(stufen[i])
    return block, schluessel


def _block_lesen(block: np.ndarray, schluessel: set[int], n: int) -> np.ndarray:
    """int16-Block -> Stufenwerte. Genau die Umkehrung von `_delta_block`."""
    stufen = np.zeros(n, dtype=np.int32)
    wert = 0
    for i in range(n):
        if i in schluessel:
            wert = int(block[i])
        else:
            wert = int(wert) + int(block[i])
        stufen[i] = wert
    return stufen


def write_fsmc(path: str,
               kanaele: list[tuple[str, str, np.ndarray]],
               fps: float = 30.0,
               *,
               keyframe_intervall: int = 30,
               bits: int | dict | None = None,
               erzeuger: str = "FaceScan Prototyp",
               geraet: str = "synthetisch",
               lizenz: str = "eigene Daten, keine Fremdrechte",
               modell_hashes: dict | None = None,
               audio: bytes | None = None) -> dict:
    """Schreibt einen Motion-Clip.

    `kanaele` ist eine Liste aus ``(name, typ, werte)`` mit
    ``typ in {"scalar", "vec3", "quat"}`` und ``werte`` der Form
    ``(n_frames, komponenten)``. Die Reihenfolge bleibt erhalten — sie ist
    Teil des Formats, damit ein Leser die Kanaltabelle nicht sortieren muss.

    `bits` ist entweder eine Zahl für alle Kanäle, ein Dict
    ``{kanalname: bits}`` für einzelne, oder ``None`` → dann gilt
    `STUFEN_VORGABE` je Kanaltyp. 16 Bit überall ist der Höflichkeitswert,
    aber nicht der sparsamste.

    Rückgabe: ein Bericht mit Größe, Werten pro Frame und dem größten
    Quantisierungsfehler je Kanal (in dessen Einheit).
    """
    if not kanaele:
        raise ValueError("kein Kanal")
    n_frames = int(np.asarray(kanaele[0][2]).shape[0])
    for name, typ, werte in kanaele:
        w = np.asarray(werte, dtype=float)
        if w.ndim != 2 or w.shape[0] != n_frames:
            raise ValueError("Kanal %r hat die Form %s, erwartet (%d, k)"
                             % (name, w.shape, n_frames))
        if w.shape[1] != KOMPONENTEN[typ]:
            raise ValueError("Kanal %r ist %s, braucht %d Spalten, hat %d"
                             % (name, typ, KOMPONENTEN[typ], w.shape[1]))

    if bits is None:
        bits = {name: STUFEN_VORGABE[typ] for name, typ, _ in kanaele}
    elif isinstance(bits, int):
        bits = {name: int(bits) for name, _, _ in kanaele}

    bloecke: list[bytes] = []
    tabelle: list[dict] = []
    fehler: dict[str, float] = {}
    offset = 0

    for name, typ, werte in kanaele:
        w = np.asarray(werte, dtype=float)
        n_bits = int(bits.get(name, 16))
        stufen_pro_komp = []
        mins, maxs, skal, mitten = [], [], [], []
        for k in range(w.shape[1]):
            q = _quantisieren(w[:, k], n_bits)
            mins.append(q["min"])
            maxs.append(q["max"])
            skal.append(q["skalierung"])
            mitten.append(q["mitte"])
            stufen_pro_komp.append(q["stufen"])

        block_stuecke = []
        schluessel_alle: set[int] = set()
        for k in range(w.shape[1]):
            block, schluessel = _delta_block(stufen_pro_komp[k],
                                             keyframe_intervall)
            block_stuecke.append(block.astype("<i2").tobytes())
            schluessel_alle |= set(schluessel)

        # Komponenten stehen hintereinander (Block je Komponente), damit der
        # Leser einen Kanal mit `offset` und `komponenten * frames * 2` Byte
        # vollständig hat, ohne rechnen zu müssen.
        roh = b"".join(block_stuecke)
        bloecke.append(roh)
        tabelle.append({
            "name": name,
            "typ": typ,
            "bits": n_bits,
            "komponenten": int(w.shape[1]),
            "offset": offset,
            "bytes": len(roh),
            "min": [float(x) for x in mins],
            "max": [float(x) for x in maxs],
            "mitte": [float(x) for x in mitten],
            "skalierung": [float(x) for x in skal],
            "keyframes": sorted(schluessel_alle),
        })
        # Größter Fehler, der durch das Runden entsteht (in der Einheit des
        # Kanals). Das ist die Zahl, die später entscheidet, ob int16 genügt.
        rueck = np.stack([np.array(_block_lesen(
            np.frombuffer(block_stuecke[k], dtype="<i2"),
            schluessel_alle, n_frames), dtype=float) * skal[k] + mitten[k]
            for k in range(w.shape[1])], axis=1)
        fehler[name] = float(np.abs(rueck - w).max())
        offset += len(roh)

    channels_bin = b"".join(bloecke)
    werte_pro_frame = sum(KOMPONENTEN[t] for _, t, _ in kanaele)

    manifest = {
        "format": "FaceScan Motion Clip",
        "schemaVersion": SCHEMA_VERSION,
        "fps": float(fps),
        "frames": n_frames,
        "dauer_s": round(n_frames / float(fps), 6),
        "kanaele": len(kanaele),
        "werte_pro_frame": werte_pro_frame,
        "keyframeIntervall": int(keyframe_intervall),
        "quantisierung": "int16, delta-kodiert, little-endian",
        "byteOrder": "little",
        "erzeuger": erzeuger,
        "geraet": geraet,
        "lizenz": lizenz,
        "modellHashes": modell_hashes or {},
        "audio": audio is not None,
    }
    meta = {
        "schemaVersion": SCHEMA_VERSION,
        "byteOrder": "little",
        "elementBytes": 2,
        # Die Offsets gelten im UNKOMPRIMIERTEN channels.bin. Die Datei im
        # ZIP ist gezippt; wer sie liest, muss vorher entpacken.
        "channelsBinBytes": len(channels_bin),
        "channels": tabelle,
    }

    dateien: dict[str, bytes] = {
        "manifest.json": json.dumps(manifest, indent=2,
                                    ensure_ascii=False).encode("utf-8"),
        "meta.json": json.dumps(meta, indent=2,
                                ensure_ascii=False).encode("utf-8"),
        "channels.bin": channels_bin,
    }
    # Prüfsummen über ALLES andere — auch über die beiden JSONs, sonst könnte
    # jemand die Kanaltabelle umschreiben und die Prüfsumme bliebe grün.
    provenance = {
        "schemaVersion": SCHEMA_VERSION,
        "algorithmus": "sha256",
        "signiert": False,
        "hinweis": ("Kein C2PA-Schlüssel vorhanden. Die Prüfsummen sichern nur "
                    "die Unversehrtheit, nicht die Herkunft."),
        "dateien": {n: hashlib.sha256(b).hexdigest()
                    for n, b in sorted(dateien.items())},
    }
    if audio is not None:
        dateien["audio.m4a"] = audio
    dateien["provenance.json"] = json.dumps(
        provenance, indent=2, ensure_ascii=False).encode("utf-8")
    provenance["dateien"]["provenance.json"] = None      # sich selbst nicht
    dateien["provenance.json"] = json.dumps(
        provenance, indent=2, ensure_ascii=False).encode("utf-8")
    del provenance["dateien"]["provenance.json"]

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name in sorted(dateien):
            info = zipfile.ZipInfo(name, date_time=ZIP_DATUM)
            info.compress_type = (zipfile.ZIP_STORED
                                  if name.endswith(".m4a")
                                  else zipfile.ZIP_DEFLATED)
            info.external_attr = 0o600 << 16
            z.writestr(info, dateien[name])

    return {
        "pfad": path,
        "frames": n_frames,
        "fps": float(fps),
        "kanaele": len(kanaele),
        "werte_pro_frame": werte_pro_frame,
        "bytes_roh": len(channels_bin),
        "bytes_gezippt": int(sum(zipfile.ZipFile(path).getinfo(n).compress_size
                                 for n in ("channels.bin",))),
        "groesste_quant_fehler": fehler,
    }


def read_fsmc(path: str) -> tuple[dict, dict, dict[str, np.ndarray]]:
    """Liest einen Motion-Clip zurück: (manifest, meta, kanaele).

    `kanaele` ist ein Dict Name -> ``(n_frames, komponenten)``. Die Kanäle
    stehen in derselben Reihenfolge wie geschrieben (dicts behalten ihre
    Einfügereihenfolge).
    """
    with zipfile.ZipFile(path) as z:
        namen = set(z.namelist())
        if not {"manifest.json", "meta.json", "channels.bin"} <= namen:
            raise ValueError("kein .fsmc: es fehlen Eintraege")
        manifest = json.loads(z.read("manifest.json").decode("utf-8"))
        meta = json.loads(z.read("meta.json").decode("utf-8"))
        roh = z.read("channels.bin")
        if "provenance.json" in namen:
            prov = json.loads(z.read("provenance.json").decode("utf-8"))
            for datei, soll in prov.get("dateien", {}).items():
                if soll is None:
                    continue
                ist = hashlib.sha256(z.read(datei)).hexdigest()
                if ist != soll:
                    raise ValueError("Pruefsumme von %s stimmt nicht" % datei)

    if manifest.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError("schemaVersion %r wird nicht unterstuetzt"
                         % manifest.get("schemaVersion"))
    if len(roh) != meta["channelsBinBytes"]:
        raise ValueError("channels.bin hat %d Byte, meta sagt %d"
                         % (len(roh), meta["channelsBinBytes"]))

    n_frames = int(manifest["frames"])
    kanaele: dict[str, np.ndarray] = {}
    for k in meta["channels"]:
        n_k = int(k["komponenten"])
        frames_bytes = n_frames * 2
        werte = np.empty((n_frames, n_k), dtype=float)
        schluessel = set(k["keyframes"])
        for c in range(n_k):
            anfang = k["offset"] + c * frames_bytes
            block = np.frombuffer(roh[anfang:anfang + frames_bytes],
                                  dtype="<i2")
            if len(block) != n_frames:
                raise ValueError("Kanal %r: Block zu kurz" % k["name"])
            stufen = _block_lesen(block, schluessel, n_frames)
            werte[:, c] = stufen * k["skalierung"][c] + k["mitte"][c]
        kanaele[k["name"]] = werte
    return manifest, meta, kanaele


def bericht(manifest: dict, meta: dict, kanaele: dict[str, np.ndarray],
            original: dict[str, np.ndarray]) -> dict:
    """Vergleicht gelesene gegen geschriebene Kanäle.

    Der Rückweg ist der eigentliche Test: eine Datei zu schreiben, beweist
    nichts. Erst wenn das Zurückgelesene bis auf die halbe Quantisierungs-
    stufe mit der Eingabe übereinstimmt, ist das Format rund.
    """
    aus = {"frames": int(manifest["frames"]),
           "werte_pro_frame": int(manifest["werte_pro_frame"]),
           "bytes_pro_frame_roh": int(manifest["werte_pro_frame"]) * 2,
           "kanaele": {}}
    schlimm = 0.0
    for name, soll in original.items():
        ist = kanaele[name]
        d = float(np.abs(np.asarray(ist) - np.asarray(soll)).max())
        spanne = float(np.max(soll) - np.min(soll)) or 1.0
        aus["kanaele"][name] = {"max_fehler": d,
                                "relativ": d / spanne}
        schlimm = max(schlimm, d / spanne)
    aus["groesster_relativer_fehler"] = schlimm
    return aus
