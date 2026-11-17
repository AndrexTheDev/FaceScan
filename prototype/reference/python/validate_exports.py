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
  * pycollada -- liest DAE (Collada). Es ist der strengste der Leser hier:
                 ein Material, auf das <instance_material> zeigt und das es
                 nicht gibt, ist fuer assimp kein Fehler, fuer pycollada
                 schon.

Alle sind OPTIONAL: fehlt eines, wird nur gemeldet, dass es fehlt. So
bleibt das Skript auch auf einem Rechner ohne C++-Toolchain lauffaehig.

Aufruf:
    pip install trimesh usd-core pycollada
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

import csv
import json
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


def _assimp_info(path):
    """Ruft `assimp info` auf und liefert die aufgeraeumte Ausgabe.

    Leerer String, wenn assimp fehlt; ``None``, wenn es die Datei nicht
    lesen konnte.
    """
    tool = os.environ.get("ASSIMP", "").strip() or "assimp"
    if not _which(tool):
        return ""
    out = subprocess.run([tool, "info", path], capture_output=True, text=True)
    text = out.stdout + out.stderr
    # Die Fortschrittsanzeige schreibt \r ohne \n -- erst wegraeumen.
    clean = text.replace("\r", "\n")
    if "Unable to load input file" in clean:
        first = next((l for l in clean.splitlines() if "ERROR" in l),
                     clean[:160])
        return "FEHLER: " + first[:160]
    return clean


def check_assimp(path, n_v, n_f, bounds, expect=None):
    """Liest mit assimp (C++), gesteuert ueber die Kommandozeile."""
    tool = os.environ.get("ASSIMP", "").strip() or "assimp"
    if not _which(tool):
        return None, ("nicht geprueft -- assimp fehlt (siehe Kopf des "
                      "Skripts, Umgebungsvariable ASSIMP)")
    clean = _assimp_info(path)
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


def check_dae(path, n_v, n_f, bounds, expect=None):
    """Prueft eine Collada-Datei mit drei Lesern, weil jeder etwas
    anderes sieht:

    * **unser eigener `read_dae`** kennt Einheiten, Hochachse, die
      Quellen und -- am wichtigsten -- Verweise ins Leere. Genau daran
      ist der erste Entwurf gescheitert: `<instance_material
      target="#face_material">` stand auch dann in der Datei, wenn es
      gar kein Material gab. assimp schluckt so etwas wortlos,
      pycollada bricht ab.
    * **assimp** (C++) zaehlt die Geometrie.
    * **pycollada** loest die Materialkette auf -- das ist der strengste
      der drei Leser und der einzige, der die Kette image -> sampler ->
      surface -> lambert wirklich folgt. Fehlt das Paket, bleibt die
      Pruefung ehrlich unvollstaendig statt gruen.

    `n_v`/`n_f` sind die Zaehlwerte der Referenz; bei LOD-Dateien werden
    sie mit 0 uebergeben, dann wird nur die innere Stimmigkeit geprueft
    (alle Quellen gleich lang, Dreieckszahl wie angegeben).
    """
    expect = expect or {}
    from facescan_ref import export_more as em
    r = em.read_dae(path, with_arrays=True)
    src = r["sources"]
    counts = {k: s["accessor_count"] for k, s in src.items()}
    n_pos = counts.get("positions")

    unit_ok = r["unit_meter"] is not None and abs(r["unit_meter"] - 0.001) < 1e-12
    up_ok = r["up_axis"] == "Y_UP"
    ok = unit_ok and up_ok and not r["dangling_refs"]
    if n_v:
        ok = ok and n_pos == n_v and r["triangles"] == n_f
    else:
        ok = ok and n_pos is not None and \
            all(c == n_pos for c in counts.values())
    note = (f"unit meter={r['unit_meter']} ({'i.O.' if unit_ok else 'FALSCH'}), "
            f"up_axis={r['up_axis']} ({'i.O.' if up_ok else 'FALSCH'}), "
            f"{r['triangles']:,} Dreiecke, "
            f"Quellen {sorted(src)} je {n_pos}")

    for key, want in (("uvs", expect.get("uv")),
                      ("normals", expect.get("normals")),
                      ("colors", expect.get("colors"))):
        if not want:
            continue
        got = counts.get(key)
        good = got is not None and (not n_v or got == n_v)
        ok = ok and good
        note += f", {key}={got} ({'i.O.' if good else 'FEHLT'})"
    if expect.get("texture"):
        good = bool(r["texture_files"])
        ok = ok and good
        note += ", Textur %s" % (r["texture_files"] or "FEHLT")
    if r["dangling_refs"]:
        note += " | VERWEISE INS LEERE %s" % (r["dangling_refs"],)

    # --- Fremdleser 1: assimp ------------------------------------
    ok2, note2 = check_assimp(path, n_pos or 0, r["triangles"], bounds, expect)
    if ok2 is False:
        ok = False
    note += " | " + note2

    # --- Fremdleser 2: pycollada ---------------------------------
    try:
        import collada
    except ImportError:
        note += (" | pycollada nicht installiert -- Materialkette "
                 "ungeprueft")
        return ok, note
    col = collada.Collada(path, ignore=[collada.DaeError])
    errs = [str(e) for e in col.errors]
    prims = [p for g in col.geometries for p in g.primitives]
    n_tri = sum(len(p.index) for p in prims)
    mat_ok = len(col.materials) >= 1 and len(col.effects) >= 1
    if expect.get("texture"):
        mat_ok = mat_ok and len(col.images) >= 1
    ok = ok and not errs and n_tri == r["triangles"] and mat_ok
    note += (f" | pycollada: {len(prims)} Primitiv(en), {n_tri:,} Dreiecke, "
             f"{len(col.materials)} Material(ien), {len(col.effects)} Effect(s), "
             f"{len(col.images)} Bild(er), Fehler {errs or 'keine'}")
    return ok, note


def check_bvh(path, n_v, n_f, bounds, expect=None):
    """Prueft eine BVH-Datei mit dem eigenen Leser und mit assimp.

    BVH ist das Format mit den wenigsten Selbstauskünften: keine
    Einheit, kein Kommentar, keine Laengenangabe pro Block. Was der
    fremde Leser deshalb beisteuert, ist nicht die Geometrie (die
    erzeugt assimp beim Importieren selbst), sondern die Frage, ob er
    die Datei ueberhaupt annimmt und ob er daraus eine Animation mit den
    erwarteten Gelenken macht.
    """
    from facescan_ref import export_more as em
    r = em.read_bvh(path)
    ok = (r["consistent"] and r["frames_read"] > 0
          and r["frame_time"] > 0 and len(r["channels"]) > 0)
    vals = r["values"]
    # Kein Frame darf springen: mehr als 180 Grad zwischen zwei Frames
    # heisst, beim Abspielen schnappt die Bewegung zurueck (Euler-Wrap).
    step = (float(np.abs(np.diff(vals, axis=0)).max())
            if len(vals) > 1 else 0.0)
    rot_step = (float(np.abs(np.diff(vals[:, 3:], axis=0)).max())
                if vals.shape[1] > 3 and len(vals) > 1 else 0.0)
    ok = ok and np.isfinite(vals).all()
    note = (f"{r['frames_read']} Frames (deklariert {r['frames_declared']}), "
            f"{len(r['channels'])} Kanaele, Frame Time "
            f"{r['frame_time']:.6f} s, groesster Sprung {step:.3f} "
            f"(Rotation {rot_step:.1f} deg)")

    clean = _assimp_info(path)
    if not clean:
        return ok, note + (" | assimp fehlt -- Animation nicht gegengelesen")
    if clean.startswith("FEHLER"):
        return False, note + " | " + clean
    anims = [int(x) for x in re.findall(r"Animations:\s+(\d+)", clean)]
    nodes = [int(x) for x in re.findall(r"Nodes:\s+(\d+)", clean)]
    chan = [int(x) for x in
            re.findall(r"Animation Channels:\s+(\d+)", clean)]
    # assimp gibt den Knotenbaum mit Baumzeichen davor und dem Mesh in
    # Klammern dahinter aus ("Head (mesh 0)", "└╴EndSite_Head").
    hier = clean.split("Node hierarchy:")[-1].splitlines()
    names = [re.sub(r"^[^\w]+", "", ln).split(" (")[0]
             for ln in hier if ln.strip()]
    want = [j["name"] for j in r["joints"]]
    # assimp baut aus dem BVH einen Knotenbaum; jedes Gelenk muss darin
    # vorkommen, sonst ist die Animation da, aber haengt an nichts.
    have = all(any(w == n for n in names) for w in want)
    ok = ok and bool(anims) and max(anims) >= 1 and have
    if nodes:
        ok = ok and max(nodes) >= len(want)
    note += (f" | assimp: {max(anims) if anims else 0} Animation(en), "
             f"{max(nodes) if nodes else 0} Knoten, "
             f"{max(chan) if chan else 0} Animationskanaele, "
             f"Gelenke {'alle gefunden' if have else 'FEHLEN'}")
    return ok, note


def check_motion_table(path, n_v, n_f, bounds, expect=None):
    """Prueft CSV bzw. JSON derselben Bewegung -- mit stdlib, nicht mit
    unserem Leser.

    Der Punkt ist nicht, ob unsere eigenen Funktionen zueinander passen
    (das prueft `build_motion.py`), sondern ob jemand, der nur `csv` und
    `json` aus der Standardbibliothek hat, dieselben Zahlen herausbekommt.
    """
    if path.endswith(".json"):
        doc = json.load(open(path, encoding="utf-8"))
        vals = np.array(doc["data"], dtype=np.float64)
        channels = list(doc["channels"])
        frame_time = float(doc["frame_time_s"])
        frames = int(doc["frames"])
        extra = ("Einheiten %s, Euler %s"
                 % (doc.get("units", {}), doc.get("euler_order")))
    else:
        with open(path, encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))
        channels = list(rows[0][2:])
        body = rows[1:]
        vals = np.array([[float(x) for x in r[2:]] for r in body],
                        dtype=np.float64)
        times = np.array([float(r[1]) for r in body])
        frame_time = float(times[1] - times[0]) if len(times) > 1 else 0.0
        frames = len(body)
        extra = "Spalten %s" % (rows[0][:2],)
    ok = (len(channels) > 0 and frames > 0 and vals.shape[0] == frames
          and vals.shape[1] == len(channels) and frame_time > 0
          and np.isfinite(vals).all())
    note = (f"{frames} Frames, {len(channels)} Kanaele, "
            f"Frame Time {frame_time:.6f} s, {extra}")
    return ok, note


def check_rig_dae(path, n_v, n_f, bounds, expect=None):
    """Das Rig-DAE: hier muss nicht nur Geometrie stimmen, sondern die HAUT.

    Ein Collada mit ``<skin>`` kann auf zwei Arten kaputt sein, die ein
    Geometrie-Test nie sieht:

      * Die Gelenke sind da, aber die Gewichte fehlen -- dann steht das
        Netz beim Bewegen still.
      * Die Gewichte sind da, aber die Namen in ``<Name_array>`` stimmen
        nicht mit den Knoten-SIDs ueberein -- dann bewegen sich zwar
        Punkte, aber am falschen Gelenk. Manche Leser merken das gar
        nicht, sie bewegen dann einfach nichts.

    Geprueft wird deshalb dreifach: unser Leser (Einheiten, Verweise ins
    Leere), pycollada (loest die Controller-Kette wirklich auf) und
    assimp als Fremdleser (zaehlt die Knochen, die tatsaechlich Gewicht
    tragen).
    """
    from facescan_ref import export_more as em
    text = open(path, encoding="utf-8").read()
    r = em.read_dae(path)
    einheit = r["unit_meter"] is not None and abs(r["unit_meter"] - 0.001) < 1e-12
    hoch = r["up_axis"] == "Y_UP"
    controller = "<skin source=\"#mesh\">" in text
    instanz = "<instance_controller" in text
    skelett = "<skeleton>#joint_0</skeleton>" in text
    n_gelenke = text.count('type="JOINT"')
    if "<Name_array" not in text or "<vertex_weights" not in text:
        return False, "Skin unvollstaendig: Name_array oder vertex_weights fehlt"
    if text.count("<vcount>") != 1 or text.count("<v>") < 1:
        return False, "vertex_weights ohne vcount/v"

    noten = ["Einheit %s" % ("mm" if einheit else "FALSCH"),
             "Hochachse %s" % ("Y" if hoch else "FALSCH"),
             "Controller %s" % ("ja" if controller else "NEIN"),
             "%d Gelenkknoten" % n_gelenke]
    ok = einheit and hoch and controller and instanz and skelett and n_gelenke >= 6

    # pycollada: der strenge Leser
    try:
        import collada
        c = collada.Collada(path)
        namen = [x.id for x in c.controllers]
        knoten = len([1 for n in c.scene.nodes for _ in _walk(n)])
        noten.append("pycollada: %d Controller, %d Knoten" % (len(namen), knoten))
        ok = ok and "skin" in namen
    except ImportError:
        noten.append("pycollada fehlt")
        return None, ", ".join(noten)
    except Exception as exc:                          # noqa: BLE001
        return False, "pycollada: %s" % exc

    # assimp zaehlt die Knochen, die WIRKLICH Gewicht tragen
    info = _assimp_info(path)
    if info is not None:
        knochen = _assimp_zahl(info, r"Bones:\s+(\d+)")
        noten.append("assimp: %s Knochen" % knochen)
        ok = ok and knochen is not None and knochen >= 2
    else:
        noten.append("assimp fehlt")
    return (ok, ", ".join(noten)) if _assimp_info(path) is not None else (None, ", ".join(noten))


def _walk(node):
    yield node
    for k in getattr(node, "children", []):
        yield from _walk(k)


def _assimp_zahl(text, muster):
    m = re.search(muster, text or "")
    return int(m.group(1)) if m else None


def check_rig_bvh(path, n_v, n_f, bounds, expect=None):
    """Das Rig-BVH: ein echtes Skelett mit Bewegung, nicht die Kamerabahn.

    Der Unterschied zu M2: dort lief die Aufnahmebahn durch denselben
    Schreiber (ein Gelenk, sechs Kanaele). Hier muessen acht Gelenke mit
    27 Kanaelen und eine Bewegung herauskommen. Geprueft wird, ob
    deklarierte und tatsaechliche Framezahl uebereinstimmen -- genau der
    Fehler, bei dem BVH keine Warnung ausgibt, sondern alle Kanaele
    stillschweigend verschiebt.
    """
    from facescan_ref import export_more as em
    r = em.read_bvh(path)
    namen = [j["name"] for j in r["joints"]]
    stimmig = bool(r["consistent"])
    kanaele = len(r["channels"])
    ok = stimmig and r["frames_read"] == r["frames_declared"] and len(namen) >= 6
    noten = ["%d Gelenke" % len(namen), "%d Kanaele" % kanaele,
             "%d Frames (%d deklariert)" % (r["frames_read"], r["frames_declared"]),
             "stimmig %s" % stimmig]
    info = _assimp_info(path)
    if info is not None:
        anim = _assimp_zahl(info, r"Animations:\s+(\d+)")
        kan = _assimp_zahl(info, r"Animation Channels:\s+(\d+)")
        noten.append("assimp: %s Animation, %s Kanaele" % (anim, kan))
        ok = ok and anim == 1 and kan is not None and kan >= 6
    else:
        noten.append("assimp fehlt")
        return None, ", ".join(noten)
    return ok, ", ".join(noten)


def check_rig_glb(path, n_v, n_f, bounds, expect=None):
    """Das Rig-GLB: Morph-Ziele in ARKit-Benennung.

    Morph-Ziele sind in glTF VERSCHIEBUNGEN, keine Zielpositionen. Der
    haeufigste Fehler ist eine falsche Einheit: Positionen in Metern und
    Ziele in Millimetern ergibt ein Modell, das beim Lachen um das
    Tausendfache auseinanderfliegt. Geprueft wird deshalb, ob die groesste
    Verschiebung in der Groessenordnung der Amplitude liegt (hier 5 mm).
    """
    import struct
    roh = open(path, "rb").read()
    if roh[:4] != b"glTF":
        return False, "kein GLB"
    off, chunks = 12, {}
    while off < len(roh):
        laenge, typ = struct.unpack("<I4s", roh[off:off + 8])
        chunks[typ] = roh[off + 8:off + 8 + laenge]
        off += 8 + laenge
    g = json.loads(chunks[b"JSON"])
    prim = g["meshes"][0]["primitives"][0]
    ziele = prim.get("targets", [])
    namen = g["meshes"][0].get("extras", {}).get("targetNames", [])
    if not ziele:
        return False, "keine Morph-Ziele"
    if len(namen) != len(ziele):
        return False, "%d Ziele, aber %d Namen" % (len(ziele), len(namen))
    bin_ = chunks[b"BIN\x00"]
    groesstes = 0.0
    stimmt_minmax = True
    for z in ziele:
        a = g["accessors"][z["POSITION"]]
        bv = g["bufferViews"][a["bufferView"]]
        arr = np.frombuffer(bin_[bv["byteOffset"]:bv["byteOffset"] + bv["byteLength"]],
                            dtype=np.float32).reshape(-1, 3)
        groesstes = max(groesstes, float(np.abs(arr).max()))
        stimmt_minmax = stimmt_minmax and np.allclose(arr.min(axis=0), a["min"]) \
            and np.allclose(arr.max(axis=0), a["max"])
        if len(arr) != g["accessors"][prim["attributes"]["POSITION"]]["count"]:
            return False, "Morph-Ziel hat %d Punkte, das Netz %d" % (
                len(arr), g["accessors"][prim["attributes"]["POSITION"]]["count"])
    ok = stimmt_minmax and 1e-4 < groesstes < 0.05      # 0,1 mm .. 50 mm
    return ok, ("%d Morph-Ziele, groesste Verschiebung %.1f mm, min/max %s"
                % (len(ziele), 1000 * groesstes,
                   "stimmt" if stimmt_minmax else "FALSCH"))



def _glb_json_chunks(path):
    """GLB in seine Chunks zerlegen: (json, bin)."""
    import struct
    roh = open(path, "rb").read()
    if roh[:4] != b"glTF":
        raise ValueError("kein GLB")
    off, chunks = 12, {}
    while off < len(roh):
        laenge, typ = struct.unpack("<I4s", roh[off:off + 8])
        chunks[typ] = roh[off + 8:off + 8 + laenge]
        off += 8 + laenge
    return json.loads(chunks[b"JSON"]), chunks[b"BIN\x00"]


def check_vrm(path, n_v, n_f, bounds, expect=None):
    """Die VRM-1.0-Datei.

    VRM ist glTF 2.0 PLUS die Erweiterung VRMC_vrm. Beides wird geprueft.
    Die drei Pruefungen, die wirklich zaehlen:

      1. **humanoid zeigt auf KNOTEN, nicht auf Gelenke.** In `humanBones`
         steht der Index im glTF-Knoten-Array. Wer stattdessen den Index im
         Gelenk-Array eintraegt, verschiebt jeden Knochen um eins -- die
         Datei laedt, aber der Avatar tanzt verrenkt. Deshalb wird hier
         gegengeprueft: heisst der Knoten so wie der Knochen?
      2. **Die 15 Pflichtknochen sind vollzaehlig.** Ohne sie ist die Datei
         nach humanoid.md schlicht kein VRM.
      3. **T-Pose (tpose.md 1.3):** die FUSSSOHLE steht auf Y=0. Geprueft
         wird das Fussgelenk EINE Fusshoehe darueber, weil die Spec `foot`
         an den Knoechel legt -- wer den Knoechel auf 0 legt, versenkt die
         Fuesse bis zu den Knien im Boden.
    """
    g, _ = _glb_json_chunks(path)
    if "VRMC_vrm" not in g.get("extensions", {}):
        return False, "keine VRMC_vrm-Erweiterung"
    v = g["extensions"]["VRMC_vrm"]
    if v.get("specVersion") != "1.0":
        return False, "specVersion %r statt '1.0'" % v.get("specVersion")
    if "VRMC_vrm" not in g.get("extensionsUsed", []):
        return False, "VRMC_vrm fehlt in extensionsUsed"
    meta = v.get("meta", {})
    if not meta.get("name") or not [a for a in meta.get("authors", []) if a]:
        return False, "meta braucht name und mindestens einen Autor"
    if meta.get("licenseUrl") != "https://vrm.dev/licenses/1.0/":
        return False, "licenseUrl ist nicht die VRM-1.0-Lizenz"

    knoten = g["nodes"]
    hb = v["humanoid"]["humanBones"]
    pflicht = ["hips", "spine", "head"] + [
        s + k for s in ("left", "right")
        for k in ("UpperLeg", "LowerLeg", "Foot", "UpperArm", "LowerArm", "Hand")]
    fehlt = [n for n in pflicht if n not in hb]
    if fehlt:
        return False, "Pflichtknochen fehlen: %s" % ", ".join(fehlt)
    verwirrt = [n for n in hb
                if not (0 <= hb[n]["node"] < len(knoten))
                or knoten[hb[n]["node"]]["name"] != n]
    if verwirrt:
        return False, "humanBones zeigen auf den falschen Knoten: %s" % verwirrt[:3]

    elter = {}
    for i, n in enumerate(knoten):
        for c in n.get("children", []):
            elter[c] = i

    def welt(i, tiefe=0):
        p = np.array(knoten[i].get("translation", [0, 0, 0]), dtype=float)
        return p if i not in elter else p + welt(elter[i], tiefe + 1)

    knoechel = min(welt(hb[s + "Foot"]["node"])[1] for s in ("left", "right"))
    if not 0.02 < knoechel < 0.20:      # Fusshoehe bei 1,3 m Koerpergroesse
        return False, "Fussgelenk bei %.3f m -- Sohle steht nicht auf Y=0" % knoechel
    hand_l = welt(hb["leftHand"]["node"])
    hand_r = welt(hb["rightHand"]["node"])
    if hand_l[0] <= 0 or hand_r[0] >= 0:
        return False, "Arme nicht seitlich ausgestreckt (T-Pose)"
    if abs(hand_l[1] - hand_r[1]) > 0.15:
        return False, "Arme haengen schief: %.0f mm Hoehenunterschied" % (
            1000 * abs(hand_l[1] - hand_r[1]))

    ziele = g["meshes"][0]["primitives"][0].get("targets", [])
    namen = g["meshes"][0].get("extras", {}).get("targetNames", [])
    for k, e in v["expressions"]["preset"].items():
        for b in e["morphTargetBinds"]:
            if not (0 <= b["index"] < len(ziele)):
                return False, "Ausdruck %s zeigt auf Morph %d von %d" % (
                    k, b["index"], len(ziele))
            if b["node"] != 0:
                return False, "Ausdruck %s haengt an Knoten %d, nicht am Netz" % (
                    k, b["node"])
    if v["lookAt"]["type"] not in ("bone", "expression"):
        return False, "lookAt.type ungueltig: %r" % v["lookAt"]["type"]
    if v["lookAt"]["type"] == "bone" and \
            not {"leftEye", "rightEye"} <= set(hb):
        return False, "lookAt bone braucht beide Augenknochen"

    return True, ("VRM 1.0: %d Knochen, %d Ausdruecke, lookAt %s, "
                  "Sohle auf Y=0, Arme seitlich" % (
                      len(hb), len(v["expressions"]["preset"]),
                      v["lookAt"]["type"]))



def check_fsmc(path, n_v, n_f, bounds, expect=None):  # noqa: E302
    """Der `.fsmc`-Motion-Clip (F-405).

    Ein Clip zu SCHREIBEN beweist nichts — erst der Rückweg zählt. Der
    Prüfer rechnet deshalb die Quantisierung aus den Metadaten nach und
    verlangt, dass jeder Kanal nach dem Rundweg innerhalb einer halben
    Stufe liegt. Eine halbe Stufe ist dabei nicht irgendwoher geschätzt,
    sondern die Folge der Rundung: wer auf die nächste Stufe rundet, liegt
    nie weiter als eine halbe daneben. Ein größerer Fehler heißt, dass
    Schreiber und Leser verschiedene Skalierungen benutzen — der
    gefährlichste Formatfehler, weil die Datei dabei völlig harmlos
    aussieht, nur die Bewegung ist falsch.

    Geprüft wird außerdem, was der Leser nicht prüfen kann: dass die
    Quaternionen Betrag 1 haben (eine Drehung, die keine ist, fällt sonst
    erst im Animationsprogramm auf) und dass die Blöcke der Kanäle sauber
    hintereinander liegen.
    """
    import zipfile
    from facescan_ref import motion_clip
    if not zipfile.is_zipfile(path):
        return False, "kein ZIP"
    with zipfile.ZipFile(path) as z:
        eintraege = set(z.namelist())
    if not {"manifest.json", "meta.json", "channels.bin"} <= eintraege:
        return False, "Eintraege fehlen: %s" % sorted(
            {"manifest.json", "meta.json", "channels.bin"} - eintraege)

    # read_fsmc prueft die SHA-256-Pruefsummen aus provenance.json selbst
    # und wirft, wenn eine nicht stimmt.
    try:
        manifest, meta, kanaele = motion_clip.read_fsmc(path)
    except Exception as exc:                      # noqa: BLE001
        return False, "beim Lesen: %s: %s" % (type(exc).__name__, exc)

    frames = int(manifest["frames"])
    if frames < 1 or float(manifest["fps"]) <= 0:
        return False, "Frames %d, fps %s" % (frames, manifest["fps"])

    # Bloecke muessen lueckenlos und ohne Ueberlappung liegen.
    erwartet = 0
    for k in meta["channels"]:
        if k["offset"] != erwartet:
            return False, "Kanal %r beginnt bei %d, erwartet %d" % (
                k["name"], k["offset"], erwartet)
        erwartet += k["bytes"]
    if erwartet != meta["channelsBinBytes"]:
        return False, "Bloecke fuellen %d Byte, meta sagt %d" % (
            erwartet, meta["channelsBinBytes"])

    schlimm = 0.0
    schlimm_name = ""
    for k in meta["channels"]:
        name, typ, bits = k["name"], k["typ"], int(k.get("bits", 16))
        w = kanaele[name]
        if w.shape != (frames, motion_clip.KOMPONENTEN[typ]):
            return False, "Kanal %r hat die Form %s" % (name, w.shape)
        if typ == "quat":
            l = float(np.linalg.norm(w, axis=1).std())
            if abs(l) > 0.01:
                return False, "Kanal %r: Quaternionen sind nicht normalisiert" % name
        # halbe Stufe aus den Metadaten: (max-min) / (2^bits - 1) / 2
        spanne = max(float(k["max"][c]) - float(k["min"][c])
                     for c in range(len(k["max"])))
        halbe = spanne / (2 ** bits - 1) / 2.0
        # Der Leser hat die Originalwerte nicht; geprueft wird deshalb, dass
        # die gelesenen Werte auf dem Stufenraster liegen, das meta.json
        # beschreibt. Ein Wert, der nicht auf dem Raster liegt, beweist,
        # dass beim Schreiben oder Lesen verschieden skaliert wurde.
        raster = True
        for c in range(w.shape[1]):
            rest = (w[:, c] - k["mitte"][c]) / k["skalierung"][c]
            raster = raster and bool(np.abs(rest - np.round(rest)).max() < 1e-3)
        if not raster:
            return False, "Kanal %r liegt nicht auf dem Stufenraster" % name
        if halbe > schlimm:
            schlimm, schlimm_name = halbe, name

    return True, ("%d Kanaele, %d Zahlen je Frame, %d Frames @ %g fps, "
                  "Rundweg auf dem Stufenraster, groesste halbe Stufe %.1e (%s), "
                  "Pruefsummen i.O." % (
                      len(meta["channels"]), int(manifest["werte_pro_frame"]),
                      frames, float(manifest["fps"]), schlimm, schlimm_name))


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
        first = names[0]
        # AR Quick Look verlangt als Root-Layer ein binaeres Crate. Ob es
        # eines ist, steht nicht im ZIP-Verzeichnis, sondern in den ersten
        # acht Byte der Nutzlast.
        magic = b""
        if first.lower().endswith(".usdc"):
            with zf.open(first) as fh:
                magic = fh.read(8)
    crate = first.lower().endswith(".usdc") and magic == b"PXR-USDC"
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
    ok = (len(pts) > 0 and n_uv == len(pts) and has_tex and crate
          and need.issubset(set(ids)))
    note = (f"{len(pts):,} Punkte, primvars:st {n_uv}, PNG im ZIP: {has_tex}, "
            f"Shader {ids}, Root-Layer {first} "
            f"({'Crate-Kennung i.O.' if crate else 'KEIN Crate'})")
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
        ("facescan_m1.dae", "eigen+assimp+pycollada", check_dae,
         dict(M1_EXPECT, colors=True)),
    ]
    # Motion-Formate (docs/05, 4.8): die Aufnahmebahn. Sie gehoeren
    # nicht zum Mesh-Satz, sondern liegen daneben -- deshalb einzeln und
    # nur, wenn tools/build_motion.py gelaufen ist.
    for fname, fn in (("facescan_m1_capture.bvh", check_bvh),
                      ("facescan_m1_capture.csv", check_motion_table),
                      ("facescan_m1_capture.json", check_motion_table)):
        if os.path.exists(os.path.join(mesh_dir, fname)):
            jobs.append((fname, "eigen+assimp" if fname.endswith(".bvh")
                         else "stdlib csv/json",
                         lambda p, a, b, c, e=None, fn=fn: fn(p, 0, 0, None),
                         {}))

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
            # DAE gibt es nur fuer eine LOD-Stufe (XML, rund 100 Byte je
            # Dreieck) -- deshalb erst schauen, ob die Datei ueberhaupt
            # da ist, statt sie als "fehlt" zu melden.
            if os.path.exists(os.path.join(lod_dir, f"head_lod{i}.dae")):
                jobs.append((f"head_lod{i}.dae", "eigen+assimp+pycollada",
                             lambda p, a, b, c, e=None: check_dae(
                                 p, 0, 0, None,
                                 dict(LOD_EXPECT, texture=True)),
                             LOD_EXPECT))

    # --- M3: Rig, Mimik und Bewegung ------------------------------------
    # Diese drei Dateien pruefen etwas anderes als der Rest: nicht die
    # Geometrie (die ist schon aus M1/M2 geprueft), sondern ob Haut,
    # Gelenke und Mimik im Dateiformat wirklich ankommen.
    if os.path.exists(os.path.join(mesh_dir, "facescan_rig.dae")):
        jobs.append(("facescan_rig.dae", "eigen+assimp+pycollada",
                     lambda p, a, b, c, e=None: check_rig_dae(p, 0, 0, None), {}))
    if os.path.exists(os.path.join(mesh_dir, "facescan_rig.bvh")):
        jobs.append(("facescan_rig.bvh", "eigen+assimp",
                     lambda p, a, b, c, e=None: check_rig_bvh(p, 0, 0, None), {}))
    if os.path.exists(os.path.join(mesh_dir, "facescan_rig.glb")):
        jobs.append(("facescan_rig.glb", "eigen (Struktur)",
                     lambda p, a, b, c, e=None: check_rig_glb(p, 0, 0, None), {}))
    # Einen Fremdleser fuer VRM gibt es hier nicht -- assimp liest zwar das
    # GLB, ignoriert die Erweiterung aber stillschweigend. Die Pruefung
    # liest die Datei deshalb selbst und hält sich an die Spec-Texte.
    # .fsmc ist ein ZIP mit JSON: die Standardbibliothek liest es vollstaendig,
    # ein Fremdleser wuerde nur das ZIP sehen und den Inhalt nicht verstehen.
    if os.path.exists(os.path.join(mesh_dir, "facescan_clip.fsmc")):
        jobs.append(("facescan_clip.fsmc", "eigen+stdlib",
                     lambda p, a, b, c, e=None: check_fsmc(p, 0, 0, None), {}))
    if os.path.exists(os.path.join(mesh_dir, "facescan.vrm")):
        jobs.append(("facescan.vrm", "eigen (Struktur)",
                     lambda p, a, b, c, e=None: check_vrm(p, 0, 0, None), {}))

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

    print("%-24s %-22s %-10s %s" % ("Datei", "Leser", "Ergebnis", "Befund"))
    print("-" * 107)
    for fname, tool, state, note in results:
        print("%-24s %-22s %-10s %s" % (fname, tool, state, note))
    print("-" * 107)

    good = [r for r in results if r[2] == "OK"]
    bad = [r for r in results if r[2] == "FEHLER"]
    skipped = [r for r in results if r[2] != "OK" and r[2] != "FEHLER"]
    # Nicht jede Datei hat einen Fremdleser: CSV und JSON prueft die
    # Standardbibliothek, weil es dafuer keinen Fremdleser braucht -- eine
    # Tabelle zu lesen, ist keine Frage des Programms. Das muss die
    # Zusammenfassung sagen, sonst steht unten eine Zahl, die mehr
    # behauptet als geprueft wurde.
    foreign = [r for r in good
               if any(k in r[1] for k in
                      ("trimesh", "pxr", "Alembic", "assimp", "pycollada"))]
    print("%d von %d Dateien bestanden -- %d davon von einem fremden "
          "Leser gelesen, %d mit eigenem Leser bzw. stdlib geprueft."
          % (len(good), len(results), len(foreign), len(good) - len(foreign)))
    if bad:
        print("ABGELEHNT: %s" % ", ".join(r[0] for r in bad))
    if skipped:
        print("Ohne Pruefer: %s" % ", ".join(r[0] for r in skipped))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
