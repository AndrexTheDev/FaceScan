#!/usr/bin/env python3
"""Prueft die Metadatenbloecke des kuenstlichen Mehransichten-GLB unabhaengig.

Der GLB-Writer legt seine Zahlen selbst als Text in `asset.extras` ab. Genau
das ist die Schwachstelle: Ein Textblock kann behaupten, was er will. Dieses
Skript liest die Datei ohne Fremdbibliotheken, vergleicht jeden Block mit einer
Referenz, die der Kotlin-Test unabhaengig geschrieben hat, und rechnet die
inneren Beziehungen nach (Summen, Differenzen, abgeleitete Kennzeichen).

Nicht geprueft wird und kann nicht geprueft werden: ob die Zahlen eine
Genauigkeit belegen. Es sind Rechengroessen des Ablaufs.
"""
import json
import struct
import sys
from pathlib import Path

MAGIC = 0x46546C67
JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942
POINT_LOSS_CATEGORIES = ("tooFewViews", "insufficientParallax", "behindCamera",
                         "unstableGeometry", "noConsensus", "unknown")
POSE_DROP_REASONS = ("invalidInput", "degenerateAnchors", "estimationFailed",
                     "behindCamera", "highResidual")
ZONE_NAMES = ("forehead", "eyes", "nose", "mouth", "chin")
FOCAL_TOLERANCE = 0.15


class Failure(Exception):
    pass


def check(condition, message):
    if not condition:
        raise Failure(message)


def read_glb(path):
    """Liest die Datei und zerlegt sie; siehe [read_glb_bytes]."""
    return read_glb_bytes(Path(path).read_bytes())


def read_glb_bytes(data):
    """Zerlegt einen GLB-Bytestrom in JSON-Dokument und Binaerblock."""
    check(len(data) >= 20, "Datei zu kurz fuer einen GLB-Kopf")
    magic, version, total = struct.unpack_from("<III", data, 0)
    check(magic == MAGIC, "kein GLB (Magic falsch)")
    check(version == 2, "GLB-Version ist nicht 2")
    check(total == len(data), "GLB-Laenge im Kopf passt nicht zur Datei")
    offset = 12
    document = None
    binary = None
    while offset < len(data):
        length, kind = struct.unpack_from("<II", data, offset)
        offset += 8
        check(offset + length <= len(data), "Chunk ragt ueber das Dateiende")
        chunk = data[offset:offset + length]
        offset += length
        if kind == JSON_CHUNK:
            check(document is None, "mehrere JSON-Chunks")
            document = json.loads(chunk.decode("utf-8"))
        elif kind == BIN_CHUNK:
            check(binary is None, "mehrere Binaer-Chunks")
            binary = chunk
    check(document is not None, "kein JSON-Chunk")
    return document, binary


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def verify_zones(text):
    """Zonenabdeckung als Text: fuenf Namen in fester Reihenfolge mit a/b."""
    check(isinstance(text, str) and text != "", "zoneCoverage fehlt")
    parts = text.split(",")
    check(len(parts) == len(ZONE_NAMES), f"zoneCoverage hat {len(parts)} statt 5 Zonen")
    totals = {}
    for name, part in zip(ZONE_NAMES, parts):
        label, _, counts = part.partition("=")
        check(label == name, f"Zone {label!r} steht an der Stelle von {name!r}")
        done, _, total = counts.partition("/")
        check(done.isdigit() and total.isdigit(), f"Zonenzaehler {counts!r} ist keine Zahl")
        done, total = int(done), int(total)
        check(0 <= done <= total, f"Zone {name}: {done} von {total} ist unmoeglich")
        totals[name] = done
    return totals


def verify(document, reference):
    extras = document.get("asset", {}).get("extras")
    check(isinstance(extras, dict), "asset.extras fehlt")

    # Fehlende Punkte: Summe der Kategorien muss die Luecke genau erklaeren.
    loss = extras.get("pointLoss")
    check(isinstance(loss, dict), "pointLoss fehlt")
    for key in ("triangulated", "missing") + POINT_LOSS_CATEGORIES:
        check(is_number(loss.get(key)), f"pointLoss.{key} fehlt oder ist keine Zahl")
        check(loss[key] >= 0, f"pointLoss.{key} ist negativ")
    categorized = sum(loss[key] for key in POINT_LOSS_CATEGORIES)
    check(categorized == loss["missing"],
          f"pointLoss: Kategorien summieren zu {categorized}, missing ist {loss['missing']}")
    check(loss["triangulated"] + loss["missing"] > 0, "pointLoss ohne jede Stelle")

    # Brennweite: das Kennzeichen muss aus der Streuung folgen.
    focal = extras.get("focalConsistency")
    check(isinstance(focal, dict), "focalConsistency fehlt")
    check(is_number(focal.get("views")) and focal["views"] >= 0, "focalConsistency.views fehlt")
    if focal.get("relativeSpread") is not None:
        check(is_number(focal["relativeSpread"]) and focal["relativeSpread"] >= 0,
              "focalConsistency.relativeSpread ist keine nicht-negative Zahl")
        expected = focal["relativeSpread"] <= FOCAL_TOLERANCE
        check(focal.get("consistent") is expected,
              f"focalConsistency.consistent={focal.get('consistent')} folgt nicht aus der Streuung")
    else:
        check(focal.get("consistent") is None,
              "focalConsistency behauptet eine Aussage ohne Streuung")

    # Ansichten: benutzte plus verworfene Grundsummen muessen aufgehen.
    use = extras.get("viewUse")
    check(isinstance(use, dict), "viewUse fehlt")
    reasons = use.get("reasons")
    check(isinstance(reasons, dict), "viewUse.reasons fehlt")
    check(tuple(reasons.keys()) == POSE_DROP_REASONS,
          f"viewUse.reasons hat andere Schluessel: {sorted(reasons)}")
    check(all(is_number(v) and v >= 0 for v in reasons.values()),
          "viewUse.reasons enthaelt keine Zaehlungen")
    for key in ("stored", "used", "notStored", "dropped"):
        check(is_number(use.get(key)) and use[key] >= 0, f"viewUse.{key} fehlt")
    check(use["used"] <= use["stored"], "mehr beigetragene als gespeicherte Ansichten")
    check(use["dropped"] == use["stored"] - use["used"],
          "viewUse.dropped passt nicht zu stored minus used")
    if use.get("complete") is not None:
        check(use["complete"] is (sum(reasons.values()) == use["dropped"]),
              "viewUse.complete folgt nicht aus den Grundsummen")

    zones = verify_zones(extras.get("zoneCoverage"))

    # Selbst deklarierte Topologie gegen die tatsaechlichen Accessoren.
    topology = extras.get("topology")
    check(isinstance(topology, dict), "topology fehlt")
    accessors = document.get("accessors")
    check(isinstance(accessors, list) and len(accessors) >= 3, "accessors fehlen")
    positions = accessors[0].get("count")
    indices = accessors[2].get("count")
    check(is_number(positions) and is_number(indices), "Accessor-Zaehlungen fehlen")
    check(topology.get("vertices") == positions,
          f"topology.vertices={topology.get('vertices')} passt nicht zu {positions} Positionen")
    check(topology.get("triangles") == indices // 3,
          f"topology.triangles={topology.get('triangles')} passt nicht zu {indices} Indizes")

    # Gegen die unabhaengig geschriebene Referenz.
    if reference is not None:
        check(reference["views"] >= 0, "Referenz ohne Ansichten")
        check(loss["triangulated"] == reference["pointLoss"]["triangulated"],
              "pointLoss.triangulated weicht von der Referenz ab")
        check(loss["missing"] == reference["pointLoss"]["missing"],
              "pointLoss.missing weicht von der Referenz ab")
        check(focal["views"] == reference["focalConsistency"]["views"],
              "focalConsistency.views weicht von der Referenz ab")
        check(focal.get("consistent") == reference["focalConsistency"]["consistent"],
              "focalConsistency.consistent weicht von der Referenz ab")
        for key in ("stored", "used", "notStored"):
            check(use[key] == reference["viewUse"][key], f"viewUse.{key} weicht von der Referenz ab")
        for key in POSE_DROP_REASONS:
            check(reasons[key] == reference["viewUse"]["reasons"][key],
                  f"viewUse.reasons.{key} weicht von der Referenz ab")
        check(extras["zoneCoverage"] == reference["zones"],
              "zoneCoverage weicht von der Referenz ab")
        check(sum(zones.values()) <= 30, "mehr triangulierte Anker als vorhanden")
    return loss, focal, use, zones


def main(argv):
    if len(argv) not in (2, 3):
        print(__doc__)
        return 2
    glb_path = Path(argv[1])
    reference = None
    if len(argv) == 3:
        reference = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
    try:
        document, binary = read_glb(glb_path)
        check(binary is not None, "kein Binaerblock")
        loss, focal, use, zones = verify(document, reference)
    except Failure as error:
        print(f"::error title=GLB-Metadaten::{glb_path.name}: {error}")
        return 1
    print(f"::notice title=GLB-Metadaten::{glb_path.name}: {len(document['asset']['extras'])} "
          f"Metadatenbloecke geprueft; Punkte {loss['triangulated']} trianguliert/"
          f"{loss['missing']} fehlend, Zonen {sum(zones.values())}/30 Anker, "
          f"Ansichten {use['used']} von {use['stored']} benutzt")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
