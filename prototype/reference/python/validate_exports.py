#!/usr/bin/env python3
"""Unabhaengige Gegenprobe unserer Exporter -- mit FREMDEN Lesern.

Warum gibt es dieses Skript zusaetzlich zu den Ruecklese-Tests in run_m1.py?
Weil ein selbst geschriebener Leser denselben Denkfehler haben kann wie der
selbst geschriebene Schreiber: verstehen sich beide auf denselben falschen
Ogawa-Offset, gilt der Test trotzdem "bestanden". Wirklich unabhaengig wird
es erst, wenn ein Programm, das wir nicht geschrieben haben, die Datei
erfolgreich einliest.

Deshalb prueft dieses Skript gegen:
  * trimesh   -- liest OBJ, PLY, STL, GLB
  * pxr/USD   -- liest USDA und USDZ (das ist die Referenzimplementierung
                 von Pixar, nicht irgendein Nachbau)
  * Alembic   -- liest ABC. Es gibt KEIN Python-Binding dafuer, deshalb
                 liegt in tools/abc_check.cpp ein 60-Zeilen-Pruefer, der
                 gegen die echte Alembic-Bibliothek gelinkt wird.
  * assimp    -- liest u. a. FBX. Auch das ist C++, deshalb der Umweg ueber
                 das Kommandozeilenwerkzeug "assimp info".

Alle vier sind OPTIONAL: fehlt eines, wird nur gemeldet, dass es fehlt. So
bleibt das Skript auch auf einem Rechner ohne C++-Toolchain lauffaehig.

Aufruf:
    pip install trimesh usd-core
    python validate_exports.py [Verzeichnis mit den Meshes]

Fuer Alembic:
    # Imath und Alembic bauen (cmake + ninja), dann:
    g++ -std=c++14 -I<prefix>/include -o abc_check tools/abc_check.cpp \
        -L<prefix>/lib -lAlembic -lImath-3_2 -Wl,-rpath,<prefix>/lib
    ABC_CHECK=./abc_check python validate_exports.py
Fuer FBX:
    ASSIMP=assimp python validate_exports.py
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DIR = os.path.join(os.path.dirname(HERE), "meshes")


def _flat(loaded):
    """trimesh liefert mal ein Mesh, mal eine Szene -- hier vereinheitlichen."""
    if hasattr(loaded, "geometry"):                 # trimesh.Scene
        geos = list(loaded.geometry.values())
        if not geos:
            return None
        loaded = geos[0]
    return loaded


def check_trimesh(path, n_v, n_f, bounds):
    """Liest mit trimesh und vergleicht Anzahl und Bounding Box."""
    import trimesh
    m = _flat(trimesh.load(path, process=False))
    if m is None:
        return False, "keine Geometrie gefunden"
    ok_v = len(m.vertices) >= n_v          # STL speichert Punkte pro Dreieck
    ok_f = len(m.faces) == n_f
    got = np.vstack([m.vertices.min(axis=0), m.vertices.max(axis=0)])
    err = float(np.abs(got - bounds).max())
    ok_b = err < 0.05                      # float32-Rundung bei 100 mm ~ 1e-5
    ok = ok_v and ok_f and ok_b
    return ok, (f"{len(m.vertices):,} Punkte / {len(m.faces):,} Dreiecke, "
                f"Bounding-Box weicht {err:.1e} mm ab")


def check_usd(path, n_v, n_f, bounds):
    """Liest mit Pixars USD-Referenzbibliothek.

    Bei .usdz zusaetzlich: die fuenf Apple-Verpackungsregeln nachmessen,
    denn die stehen nicht im USD-Baum, sondern im ZIP-Container.
    """
    import struct
    import zipfile
    from pxr import Usd, UsdGeom

    if path.lower().endswith(".usdz"):
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
            first = infos[0].filename
            stored = all(i.compress_type == zipfile.ZIP_STORED for i in infos)
            offsets = {}
            for i in infos:
                with open(path, "rb") as fh:
                    fh.seek(i.header_offset)
                    head = fh.read(30)
                nlen, elen = struct.unpack("<H H", head[26:30])
                offsets[i.filename] = i.header_offset + 30 + nlen + elen
        aligned = all(o % 64 == 0 for o in offsets.values())
        if not (stored and aligned):
            return False, ("USDZ-Verpackung verletzt Apple-Regeln: "
                           "STORED=%s, 64-Byte-ausgerichtet=%s"
                           % (stored, aligned))

    stage = Usd.Stage.Open(path)
    if stage is None:
        return False, "Stage liess sich nicht oeffnen"
    meshes = [p for p in stage.Traverse() if p.GetTypeName() == "Mesh"]
    if not meshes:
        return False, "kein Mesh-Prim gefunden"
    m = UsdGeom.Mesh(meshes[0])
    pts = np.asarray(m.GetPointsAttr().Get(), dtype=np.float64)
    counts = np.asarray(m.GetFaceVertexCountsAttr().Get(), dtype=np.int64)
    idx = np.asarray(m.GetFaceVertexIndicesAttr().Get(), dtype=np.int64)
    mpu = UsdGeom.GetStageMetersPerUnit(stage)
    up = UsdGeom.GetStageUpAxis(stage)
    got = np.vstack([pts.min(axis=0), pts.max(axis=0)])
    err = float(np.abs(got - bounds).max())
    ok = (len(pts) == n_v and len(counts) == n_f and len(idx) == 3 * n_f
          and abs(mpu - 0.001) < 1e-12 and up == "Y" and err < 1e-3)
    note = (f"{len(pts):,} Punkte / {len(counts):,} Flaechen, "
            f"metersPerUnit={mpu}, upAxis={up}, Box weicht {err:.1e} mm ab")
    if path.lower().endswith(".usdz"):
        note += f" | ZIP: {first}, STORED, Datenanfang bei {offsets[first]} B"
    return ok, note


def check_abc(path, n_v, n_f, bounds):
    """Liest mit der echten Alembic-Bibliothek ueber tools/abc_check.cpp."""
    tool = os.environ.get("ABC_CHECK", "").strip()
    if not tool:
        tool = "./abc_check"
    if not (os.path.exists(tool) or _which(tool)):
        return None, ("nicht geprueft -- abc_check fehlt (siehe Kopf des "
                      "Skripts, Umgebungsvariable ABC_CHECK)")
    out = subprocess.run([tool, path], capture_output=True, text=True)
    text = out.stdout + out.stderr
    if out.returncode != 0:
        return False, text.strip().replace("\n", " | ")[:200]
    np_ = int(re.search(r"P=(\d+)", text).group(1))
    ni = int(re.search(r"faceIndices=(\d+)", text).group(1))
    nc = int(re.search(r"faceCounts=(\d+)", text).group(1))
    ok = (np_ == n_v and ni == 3 * n_f and nc == n_f
          and "AbcGeom_PolyMesh_v1" in text)
    return ok, ("Alembic %s: PolyMesh_v1, P=%d, faceIndices=%d, faceCounts=%d"
                % (re.search(r"Alembic-Version der Datei: (\d+)",
                             text).group(1), np_, ni, nc))


def check_assimp(path, n_v, n_f, bounds):
    """Liest mit assimp (C++), gesteuert ueber die Kommandozeile."""
    tool = os.environ.get("ASSIMP", "").strip() or "assimp"
    if not _which(tool):
        return None, ("nicht geprueft -- assimp fehlt (siehe Kopf des "
                      "Skripts, Umgebungsvariable ASSIMP)")
    out = subprocess.run([tool, "info", path], capture_output=True, text=True)
    text = out.stdout + out.stderr
    # Die Fortschrittsanzeige schreibt \r ohne \n -- erst wegraeumen.
    clean = text.replace("\r", "\n")
    nums = [int(x.replace(",", "")) for x in
            re.findall(r"Vertices:\s+([\d,]+)", clean)]
    faces = [int(x.replace(",", "")) for x in
             re.findall(r"Faces:\s+([\d,]+)", clean)]
    if not nums:
        first = next((l for l in clean.splitlines() if "ERROR" in l),
                     clean[:160])
        return False, "assimp hat keine Geometrie gemeldet: " + first[:160]
    n = max(nums)
    ok = n >= n_v and bool(faces) and max(faces) >= n_f
    return ok, ("assimp: %d Vertices, %d Faces"
                % (n, max(faces) if faces else 0))


def _which(prog):
    from shutil import which
    return which(prog)


def main(argv):
    mesh_dir = argv[1] if len(argv) > 1 else DEFAULT_DIR
    ref = os.path.join(mesh_dir, "facescan_m1.ply")
    if not os.path.exists(ref):
        print("Keine Referenz unter %s -- bitte zuerst run_m1.py laufen lassen."
              % ref)
        return 2

    import trimesh                                   # noqa: F401
    ref_mesh = _flat(trimesh.load(ref, process=False))
    n_v, n_f = len(ref_mesh.vertices), len(ref_mesh.faces)
    bounds = np.vstack([ref_mesh.vertices.min(axis=0),
                        ref_mesh.vertices.max(axis=0)])
    print("Referenz (unser PLY): %s" % ref)
    print("  %d Punkte / %d Dreiecke" % (n_v, n_f))
    print("  Bounding Box min %s  max %s" % (bounds[0], bounds[1]))
    print()

    jobs = [
        ("facescan_m1.obj", "trimesh", check_trimesh),
        ("facescan_m1.stl", "trimesh", check_trimesh),
        ("facescan_m1.glb", "trimesh", check_trimesh),
        ("facescan_m1.usda", "pxr/USD", check_usd),
        ("facescan_m1.usdz", "pxr/USD", check_usd),
        ("facescan_m1.abc", "Alembic", check_abc),
        ("facescan_m1.fbx", "assimp", check_assimp),
    ]

    results = []
    for fname, tool, fn in jobs:
        path = os.path.join(mesh_dir, fname)
        if not os.path.exists(path):
            results.append((fname, tool, "FEHLT", "Datei fehlt"))
            continue
        try:
            ok, note = fn(path, n_v, n_f, bounds)
        except Exception as exc:                     # noqa: BLE001
            ok, note = False, "%s: %s" % (type(exc).__name__, exc)
        state = "--" if ok is None else ("OK" if ok else "FEHLER")
        results.append((fname, tool, state, note))

    print("%-18s %-9s %-10s %s" % ("Datei", "Leser", "Ergebnis", "Befund"))
    print("-" * 90)
    for fname, tool, state, note in results:
        print("%-18s %-9s %-10s %s" % (fname, tool, state, note))
    print("-" * 90)

    good = [r for r in results if r[2] == "OK"]
    bad = [r for r in results if r[2] == "FEHLER"]
    skipped = [r for r in results if r[2] != "OK" and r[2] != "FEHLER"]
    print("%d von %d Formaten von einem fremden Leser bestaetigt."
          % (len(good), len(results)))
    if bad:
        print("ABGELEHNT: %s" % ", ".join(r[0] for r in bad))
    if skipped:
        print("Ohne Pruefer: %s" % ", ".join(r[0] for r in skipped))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
