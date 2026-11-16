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


def check_trimesh(path, n_v, n_f, bounds, expect=None):
    """Liest mit trimesh und vergleicht Anzahl und Bounding Box.

    `expect` = {"uv": True/False}: soll die Datei UV-Koordinaten haben?
    trimesh legt UVs NICHT selbst an (im Gegensatz zu Normalen, die es
    bei Bedarf nachrechnet). Wer hier also ein `visual.uv` sieht, weiss:
    es steht wirklich in der Datei.
    """
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
    note = (f"{len(m.vertices):,} Punkte / {len(m.faces):,} Dreiecke, "
            f"Bounding-Box weicht {err:.1e} mm ab")
    uv = getattr(getattr(m, "visual", None), "uv", None)
    has_uv = uv is not None and len(np.asarray(uv)) == len(m.vertices)
    if expect and expect.get("uv"):
        ok = ok and has_uv
        note += f" | UV: {'vorhanden' if has_uv else 'FEHLT'}"
    return ok, note


def check_usd(path, n_v, n_f, bounds, expect=None):
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
    if expect:
        # Normalen: USD unterscheidet "normals" (vertex-varying) von
        # nichts anderem -- ist das Attribut da, ist es das richtige.
        if expect.get("normals"):
            nv = m.GetNormalsAttr().Get()
            has_n = nv is not None and len(nv) == n_v
            ok = ok and bool(has_n)
            note += f" | Normalen: {'vorhanden' if has_n else 'FEHLEN'}"
        if expect.get("uv"):
            pv = UsdGeom.PrimvarsAPI(meshes[0]).GetPrimvar("st")
            uv = pv.Get() if pv else None
            has_uv = uv is not None and len(uv) == n_v
            ok = ok and bool(has_uv)
            note += (f" | primvars:st: {'vorhanden' if has_uv else 'FEHLT'}"
                     + (f" ({pv.GetInterpolation()})" if has_uv else ""))
    if path.lower().endswith(".usdz"):
        note += f" | ZIP: {first}, STORED, Datenanfang bei {offsets[first]} B"
    return ok, note


def check_abc(path, n_v, n_f, bounds, expect=None):
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
    note = ("Alembic %s: PolyMesh_v1, P=%d, faceIndices=%d, faceCounts=%d"
            % (re.search(r"Alembic-Version der Datei: (\d+)",
                         text).group(1), np_, ni, nc))
    if expect and expect.get("normals"):
        mn = re.search(r"N=(\d+)", text)
        mn = int(mn.group(1)) if mn else 0
        ok = ok and mn == n_v
        note += f" | N={mn} (erwartet {n_v})"
    return ok, note


def check_assimp(path, n_v, n_f, bounds, expect=None):
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
    note = ("assimp: %d Vertices, %d Faces"
            % (n, max(faces) if faces else 0))
    # `assimp info` meldet nur Zaehlwerte, keine vorhandenen Kanaele --
    # und der Test-Build hat den Export abgeschaltet ("assimp dump:
    # Export disabled."), sonst koennte man FBX -> OBJ wandeln und die
    # "vn"-Zeilen zaehlen. Deshalb hier bewusst KEIN Urteil: etwas als
    # fehlend zu melden, was der Pruefer gar nicht sehen kann, ist
    # schlechter als die Luecke zuzugeben. Geprueft werden die
    # FBX-Normalen stattdessen von unserem eigenen Leser in run_m1.py.
    if expect and expect.get("normals"):
        note += " | Normalen: mit assimp info nicht pruefbar"
    return ok, note


def _which(prog):
    from shutil import which
    return which(prog)


def _check_lod_trimesh(path):
    """Prueft eine LOD-Datei mit trimesh: Geometrie, UV, Textur.

    Hier zaehlt nicht die Punktzahl (die ist bei jedem LOD anders),
    sondern dass der ATLAS ankommt: ein Mesh ohne UV ist zwar gueltig,
    aber die gebackene Textur zeigt dann nichts.
    """
    import trimesh
    m = _flat(trimesh.load(path, process=False))
    if m is None:
        return False, "keine Geometrie gefunden"
    uv = getattr(getattr(m, "visual", None), "uv", None)
    n_uv = 0 if uv is None else len(np.asarray(uv))
    ok = (len(m.faces) > 0 and len(m.vertices) > 0 and n_uv == len(m.vertices))
    note = (f"{len(m.vertices):,} Punkte / {len(m.faces):,} Dreiecke, "
            f"UV {n_uv}")
    if path.lower().endswith(".glb"):
        # GLB traegt das PNG im BIN-Chunk mit. trimesh macht daraus ein
        # PBRMaterial; steht dort ein baseColorTexture, hat der
        # Empfaenger das Bild wirklich dekodiert und nicht bloss
        # gefunden. (In m.metadata stehen nur Einheiten -- wer dort
        # sucht, prueft am Ende gar nichts.)
        mat = getattr(getattr(m, "visual", None), "material", None)
        tex = getattr(mat, "baseColorTexture", None)
        has_img = tex is not None
        ok = ok and has_img
        if has_img:
            note += (" | Bild eingebettet: %sx%s px"
                     % (getattr(tex, "size", ("?", "?"))[0],
                        getattr(tex, "size", ("?", "?"))[1]))
        else:
            note += " | Bild: FEHLT"
    if path.lower().endswith(".obj"):
        txt = open(path, encoding="utf-8").read()
        has_vt = "\nvt " in txt
        has_use = "usemtl" in txt
        # map_Kd steht im .mtl, NICHT im .obj. Wer beides in derselben
        # Datei sucht, findet es nie und meldet einen Fehler, der
        # keiner ist.
        side_path = path[:-4] + ".mtl"
        side = (open(side_path, encoding="utf-8").read()
                if os.path.exists(side_path) else "")
        has_map = "map_Kd" in side
        ok = ok and has_vt and has_use and has_map
        note += (f" | vt={has_vt}, usemtl={has_use}, map_Kd im .mtl={has_map}")
    return ok, note


def _check_lod_usd(path):
    """Prueft eine LOD-USDZ mit Pixar USD: Mesh, primvars:st, Material.

    Der Punkt, an dem selbstgeschriebene USD-Exporte scheitern, ist die
    Verbindungskette st -> UsdUVTexture -> UsdPreviewSurface. Dass ALLE
    drei Glieder da sind, sieht man nur, wenn man die Stage nach den
    Shadern fragt -- die Datei ist auch ohne sie "gueltig".
    """
    import zipfile
    from pxr import Usd, UsdGeom, UsdShade
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
    has_tex = any(n.lower().endswith(".png") for n in names)
    stage = Usd.Stage.Open(path)
    if stage is None:
        return False, "Stage liess sich nicht oeffnen"
    meshes = [p for p in stage.Traverse() if p.GetTypeName() == "Mesh"]
    if not meshes:
        return False, "kein Mesh-Prim gefunden"
    m = UsdGeom.Mesh(meshes[0])
    pts = np.asarray(m.GetPointsAttr().Get(), dtype=np.float64)
    pv = UsdGeom.PrimvarsAPI(meshes[0]).GetPrimvar("st")
    uv = pv.Get() if pv else None
    n_uv = 0 if uv is None else len(uv)
    shaders = [p for p in stage.Traverse() if p.GetTypeName() == "Shader"]
    ids = sorted({(UsdShade.Shader(p).GetIdAttr().Get() or "")
                  for p in shaders})
    need = {"UsdPreviewSurface", "UsdUVTexture", "UsdPrimvarReader_float2"}
    ok = (len(pts) > 0 and n_uv == len(pts) and has_tex
          and need.issubset(set(ids)))
    note = (f"{len(pts):,} Punkte, primvars:st {n_uv}, PNG im ZIP: {has_tex}, "
            f"Shader {ids}")
    return ok, note


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

    # Was jede Datei ZUSAETZLICH zur Geometrie tragen muss. Normalen
    # schreiben wir ueberall mit (ausser STL: da steht nur die
    # Flaechennormale im 50-Byte-Satz). UVs tragen nur die LOD-Netze,
    # weil nur die einen Atlas haben.
    LOD_EXPECT = {"normals": True, "uv": True}
    M1_EXPECT = {"normals": True, "uv": False}
    jobs = [
        ("facescan_m1.obj", "trimesh", check_trimesh, M1_EXPECT),
        ("facescan_m1.stl", "trimesh", check_trimesh, {}),
        ("facescan_m1.glb", "trimesh", check_trimesh, M1_EXPECT),
        ("facescan_m1.usda", "pxr/USD", check_usd, M1_EXPECT),
        ("facescan_m1.usdz", "pxr/USD", check_usd, M1_EXPECT),
        ("facescan_m1.abc", "Alembic", check_abc, M1_EXPECT),
        ("facescan_m1.fbx", "assimp", check_assimp, M1_EXPECT),
    ]
    lod_dir = mesh_dir
    lod_glb = os.path.join(lod_dir, "head_lod0.glb")
    if os.path.exists(lod_glb):
        for i in (0, 1, 2, 3):
            jobs.append((f"head_lod{i}.glb", "trimesh",
                         lambda p, a, b, c, e=None: _check_lod_trimesh(p),
                         LOD_EXPECT))
            jobs.append((f"head_lod{i}.obj", "trimesh",
                         lambda p, a, b, c, e=None: _check_lod_trimesh(p),
                         LOD_EXPECT))
            jobs.append((f"head_lod{i}.usdz", "pxr/USD",
                         lambda p, a, b, c, e=None: _check_lod_usd(p),
                         LOD_EXPECT))

    results = []
    for fname, tool, fn, expect in jobs:
        path = os.path.join(mesh_dir, fname)
        if not os.path.exists(path):
            results.append((fname, tool, "FEHLT", "Datei fehlt"))
            continue
        try:
            ok, note = fn(path, n_v, n_f, bounds, expect)
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
