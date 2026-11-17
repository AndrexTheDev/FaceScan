"""Export-Schreiber (M1): OBJ, PLY (binär), GLB (binäres glTF).

Warum eigene Schreiber statt assimp & Co.?
  * assimp kann zwar OBJ/PLY/STL/GLB schreiben, aber kein verlässliches
    binäres FBX und kein Alembic -- wir brauchen aber beides (docs/05).
  * Ein Schreiber, den wir selbst haben, lässt sich in Kotlin und C++
    übersetzen, ohne eine 30-MB-Bibliothek mitzuschleppen und ohne
    Lizenzfrage.
  * Die Formate sind dokumentiert und kurz. Das ist Fleissarbeit, keine Kunst.

STAND M1: Geometrie mit Vertexfarben.
  Die UV-Atlas-Packung (xatlas) kommt in M2 -- sie ist für professionelle
  Texturen nötig, aber unabhängig von der Korrektheit der Schreiber.

Jeder Schreiber hat einen Prüfleser (`read_*`), damit ein Test nicht nur
"Datei existiert" feststellt, sondern die Daten wirklich zurückliest und
vergleicht. Genau das ist der Unterschied zwischen "geschrieben" und
"funktioniert".
"""
from __future__ import annotations

import json
import os
import struct

import numpy as np

# ------------------------------------------------------------------ OBJ ---


def write_obj(path: str, v: np.ndarray, f: np.ndarray,
              colors: np.ndarray | None = None, name: str = "FaceScan",
              normals: np.ndarray | None = None, uv: np.ndarray | None = None,
              texture: str | None = None):
    """Wavefront OBJ.

    Millimeter bleiben Millimeter: OBJ kennt keine Einheit, alle Profi-Tools
    fragen beim Import nach -- und Blender/Maya/Unity nehmen "1 Unit = 1 m"
    an, deshalb schreiben wir einen Hinweis in den Kopf. Der Nutzer stellt im
    Import 0.001 ein -- das sagen wir ihm im Export-Dialog der App.

    Index-Notation: OBJ zählt ab 1 und erlaubt ``v/vt/vn``. Fehlt die
    Textur, bleibt der mittlere Slot leer (``v//vn``) -- beides muss man
    kennen, sonst schreibt man ``v/vn`` und das Modell kommt ohne Normalen
    an, also facettiert.
    """
    v = np.asarray(v, dtype=np.float64)
    f = np.asarray(f, dtype=np.int64)
    c = (np.asarray(colors, dtype=np.float64) / 255.0) if colors is not None else None
    n = np.asarray(normals, dtype=np.float64) if normals is not None else None
    t = np.asarray(uv, dtype=np.float64) if uv is not None else None

    base = os.path.splitext(path)[0]
    mtl_name = os.path.basename(base) + ".mtl"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"# FaceScan export -- {name}\n")
        fh.write("# Einheit: Millimeter (beim Import 0.001 skalieren)\n")
        if texture is not None:
            fh.write(f"mtllib {mtl_name}\n")
        fh.write(f"o {name}\n")
        for i in range(len(v)):
            if c is not None:
                fh.write("v %.6f %.6f %.6f %.6f %.6f %.6f\n"
                         % (v[i, 0], v[i, 1], v[i, 2], c[i, 0], c[i, 1], c[i, 2]))
            else:
                fh.write("v %.6f %.6f %.6f\n" % (v[i, 0], v[i, 1], v[i, 2]))
        if t is not None:
            for i in range(len(t)):
                fh.write("vt %.6f %.6f\n" % (t[i, 0], 1.0 - t[i, 1]))
        if n is not None:
            for i in range(len(n)):
                fh.write("vn %.6f %.6f %.6f\n" % (n[i, 0], n[i, 1], n[i, 2]))
        if texture is not None:
            fh.write("usemtl scan\n")
        for tri in f:
            a, b, d = tri[0] + 1, tri[1] + 1, tri[2] + 1
            if t is not None and n is not None:
                fh.write("f %d/%d/%d %d/%d/%d %d/%d/%d\n"
                         % (a, a, a, b, b, b, d, d, d))
            elif n is not None:
                fh.write("f %d//%d %d//%d %d//%d\n" % (a, a, b, b, d, d))
            elif t is not None:
                fh.write("f %d/%d %d/%d %d/%d\n" % (a, a, b, b, d, d))
            else:
                fh.write("f %d %d %d\n" % (a, b, d))
    if texture is not None:
        with open(os.path.join(os.path.dirname(path), mtl_name), "w",
                  encoding="utf-8") as fh:
            fh.write("# FaceScan -- gebackene Vertexfarben\n")
            fh.write("newmtl scan\n")
            fh.write("Ka 0 0 0\nKd 1 1 1\nKs 0 0 0\n")
            fh.write("illum 1\n")
            fh.write("map_Kd %s\n" % os.path.basename(texture))
    return path


def read_obj(path: str):
    v, c, n, t, f = [], [], [], [], []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("v "):
                p = line.split()
                v.append([float(p[1]), float(p[2]), float(p[3])])
                if len(p) >= 7:
                    c.append([float(p[4]), float(p[5]), float(p[6])])
            elif line.startswith("vn "):
                p = line.split()
                n.append([float(p[1]), float(p[2]), float(p[3])])
            elif line.startswith("vt "):
                p = line.split()
                t.append([float(p[1]), float(p[2])])
            elif line.startswith("f "):
                p = line.split()
                f.append([int(x.split("/")[0]) - 1 for x in p[1:4]])
    out = {"vertices": np.array(v), "faces": np.array(f, dtype=np.int64)}
    if c:
        out["colors"] = np.array(c)
    if n:
        out["normals"] = np.array(n)
    if t:
        out["uv"] = np.array(t)
    return out


# ------------------------------------------------------------------ PLY ---

_PLY_TYPES = {1: "b", 2: "h", 4: "i", 8: "d", 11: "f"}


def write_ply(path: str, v: np.ndarray, f: np.ndarray,
              colors: np.ndarray | None = None, binary: bool = True,
              normals: np.ndarray | None = None, uv: np.ndarray | None = None):
    """Stanford PLY, binär little-endian (oder ASCII zum Debuggen).

    Property-Reihenfolge: ``x y z [nx ny nz] [s t] [red green blue]``.
    Sie ist nicht vorgeschrieben, aber MeshLab und CloudCompare erwarten
    genau sie.
    """
    v = np.asarray(v, dtype=np.float64)
    f = np.asarray(f, dtype=np.int64)
    c = np.asarray(colors, dtype=np.uint8) if colors is not None else None
    n = np.asarray(normals, dtype=np.float64) if normals is not None else None
    t = np.asarray(uv, dtype=np.float64) if uv is not None else None

    if not binary:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("ply\nformat ascii 1.0\n")
            fh.write(f"element vertex {len(v)}\n")
            fh.write("property float x\nproperty float y\nproperty float z\n")
            if n is not None:
                fh.write("property float nx\nproperty float ny\n"
                         "property float nz\n")
            if t is not None:
                fh.write("property float s\nproperty float t\n")
            if c is not None:
                fh.write("property uchar red\nproperty uchar green\n"
                         "property uchar blue\n")
            fh.write(f"element face {len(f)}\nproperty list uchar int vertex_indices\n")
            fh.write("end_header\n")
            for i in range(len(v)):
                line = "%.6f %.6f %.6f" % (v[i, 0], v[i, 1], v[i, 2])
                if n is not None:
                    line += " %.6f %.6f %.6f" % (n[i, 0], n[i, 1], n[i, 2])
                if t is not None:
                    line += " %.6f %.6f" % (t[i, 0], t[i, 1])
                if c is not None:
                    line += " %d %d %d" % (c[i, 0], c[i, 1], c[i, 2])
                fh.write(line + "\n")
            for tri in f:
                fh.write("3 %d %d %d\n" % (tri[0], tri[1], tri[2]))
        return path

    with open(path, "wb") as fh:
        header = "ply\nformat binary_little_endian 1.0\n"
        header += f"element vertex {len(v)}\n"
        header += "property float x\nproperty float y\nproperty float z\n"
        if n is not None:
            header += ("property float nx\nproperty float ny\n"
                       "property float nz\n")
        if t is not None:
            header += "property float s\nproperty float t\n"
        if c is not None:
            header += ("property uchar red\nproperty uchar green\n"
                       "property uchar blue\n")
        header += f"element face {len(f)}\nproperty list uchar int vertex_indices\n"
        header += "end_header\n"
        fh.write(header.encode("ascii"))

        dtype = [("x", "<f4"), ("y", "<f4"), ("z", "<f4")]
        if n is not None:
            dtype += [("nx", "<f4"), ("ny", "<f4"), ("nz", "<f4")]
        if t is not None:
            dtype += [("s", "<f4"), ("t", "<f4")]
        if c is not None:
            dtype += [("r", "u1"), ("g", "u1"), ("b", "u1")]
        data = np.empty(len(v), dtype=dtype)
        data["x"], data["y"], data["z"] = v[:, 0], v[:, 1], v[:, 2]
        if n is not None:
            data["nx"], data["ny"], data["nz"] = n[:, 0], n[:, 1], n[:, 2]
        if t is not None:
            data["s"], data["t"] = t[:, 0], t[:, 1]
        if c is not None:
            data["r"], data["g"], data["b"] = c[:, 0], c[:, 1], c[:, 2]
        fh.write(data.tobytes())

        for tri in f:
            fh.write(struct.pack("<Biii", 3, int(tri[0]), int(tri[1]), int(tri[2])))
    return path


def read_ply(path: str):
    with open(path, "rb") as fh:
        assert fh.readline().strip() == b"ply"
        fmt = fh.readline().decode().strip()
        binary = "binary" in fmt
        le = "little" in fmt
        props, n_vert, n_face = [], 0, 0
        while True:
            line = fh.readline().decode().strip()
            if line == "end_header":
                break
            parts = line.split()
            if parts[0] == "element":
                if parts[1] == "vertex":
                    n_vert = int(parts[2]); cur = "vertex"
                else:
                    n_face = int(parts[2]); cur = "face"
            elif parts[0] == "property" and cur == "vertex":
                props.append((parts[2], parts[1]))
        dtype = "<" if le else ">"
        if binary:
            code = {"char": "b", "uchar": "B", "short": "h", "ushort": "H",
                    "int": "i", "uint": "I", "float": "f", "double": "d"}
            rec = np.dtype([(n, dtype + code[t]) for n, t in props])
            buf = fh.read(rec.itemsize * n_vert)
            verts = np.frombuffer(buf, dtype=rec, count=n_vert)
            v = np.stack([verts["x"], verts["y"], verts["z"]], axis=1)
            c = None
            if "red" in verts.dtype.names:
                c = np.stack([verts["red"], verts["green"], verts["blue"]], axis=1)
            if "nx" in verts.dtype.names:
                out_normals = np.stack([verts["nx"], verts["ny"],
                                        verts["nz"]], axis=1)
            else:
                out_normals = None
            if "s" in verts.dtype.names:
                out_uv = np.stack([verts["s"], verts["t"]], axis=1)
            else:
                out_uv = None
            faces = []
            for _ in range(n_face):
                cnt = struct.unpack(dtype + "B", fh.read(1))[0]
                faces.append(struct.unpack(dtype + "i" * cnt, fh.read(4 * cnt)))
            f = np.array(faces, dtype=np.int64)
        else:
            out_normals = out_uv = None
            rest = fh.read().decode().splitlines()
            names = [nm for nm, _ in props]
            nums = [[float(x) for x in l.split()] for l in rest[:n_vert]]
            ix, iy, iz = names.index("x"), names.index("y"), names.index("z")
            v = np.array([[r[ix], r[iy], r[iz]] for r in nums])
            c = None
            if "red" in names:
                ir = names.index("red")
                c = np.array([[r[ir], r[ir + 1], r[ir + 2]] for r in nums])
            f = np.array([[int(x) for x in l.split()[1:4]]
                          for l in rest[n_vert:n_vert + n_face]])
    out = {"vertices": v, "faces": f}
    if c is not None:
        out["colors"] = c
    if out_normals is not None:
        out["normals"] = out_normals
    if out_uv is not None:
        out["uv"] = out_uv
    return out


# ------------------------------------------------------------------ GLB ---

GL_FLOAT = 5126
GL_UNSIGNED_INT = 5125
GL_UNSIGNED_BYTE = 5121


def _pad4(b: bytes, fill: bytes = b"\x00") -> bytes:
    """Auffuellen auf 4 Byte.

    glTF schreibt zwingend vor: JSON-Chunk wird mit Leerzeichen (0x20)
    aufgepolstert, BIN-Chunk mit Nullen. Wer bei JSON Nullen nimmt, produziert
    Dateien, die strenge Parser ablehnen -- ein klassischer Exportfehler.
    """
    pad = (-len(b)) % 4
    return b + fill * pad


def write_glb(path: str, v: np.ndarray, f: np.ndarray,
              colors: np.ndarray | None = None, name: str = "FaceScan",
              normals: np.ndarray | None = None, uv: np.ndarray | None = None,
              texture_png: bytes | None = None,
              targets: list | None = None, target_names: list | None = None):
    """Binäres glTF 2.0 (.glb) -- ein Container, alles inline.

    Warum GLB und nicht glTF+bin? Weil ein EINZELNES File beim Teilen,
    Importieren und Archivieren keine Frage aufwirft ("wo ist die .bin?").
    Für USDZ gilt genau dieselbe Überlegung (docs/05).

    Wenn `texture_png` (fertig kodierte PNG-Bytes) und `uv` übergeben
    werden, bekommt das Material ein `baseColorTexture` und die Farben
    werden NICHT als COLOR_0 geschrieben. Grund: beide gleichzeitig ist in
    Blender und im Android-Viewer zu "doppelt gefärbten" Modellen.

    **Morph-Ziele (M3):** `targets` ist eine Liste von `(n_punkte, 3)`-Feldern
    mit den VERSCHIEBUNGEN je Ausdruck -- nicht die Zielpositionen. glTF
    rechnet `position + summe(gewicht * ziel)`, ein Ziel ist also immer eine
    Differenz. Drei Fallen:

      1. Die Verschiebungen müssen in **derselben Einheit** stehen wie die
         Positionen. Wer Millimeter-Positionen und Millimeter-Deltas mischt,
         bekommt ein Modell, das beim Lächeln auseinanderfliegt.
      2. `min`/`max` sind auch für Ziel-Accessoren vorgeschrieben; manche
         Prüfer lehnen die Datei ohne sie ab.
      3. Die **Namen** der Ziele stehen in `mesh.extras.targetNames`. Das ist
         eine Konvention, kein Pflichtfeld -- aber ohne sie heißen die
         Regler in Blender "Key 1, Key 2" statt "jawOpen, mouthSmile".
    """
    v = np.asarray(v, dtype=np.float32)
    f = np.asarray(f, dtype=np.uint32).reshape(-1)
    c = np.asarray(colors, dtype=np.uint8) if colors is not None else None
    n = np.asarray(normals, dtype=np.float32) if normals is not None else None
    t = np.asarray(uv, dtype=np.float32) if uv is not None else None

    chunks = []
    views = []
    accessors = []
    offset = 0

    def add(arr: np.ndarray, target=None):
        nonlocal offset
        raw = np.asarray(arr, dtype=arr.dtype).tobytes()
        chunks.append(_pad4(raw))
        views.append({"buffer": 0,
                      "byteOffset": offset,
                      "byteLength": len(raw),
                      **({"target": target} if target else {})})
        offset += len(_pad4(raw))
        return len(views) - 1

    def acc(view, ctype, count, type_, **kw):
        accessors.append({"bufferView": view, "componentType": ctype,
                          "count": count, "type": type_, **kw})
        return len(accessors) - 1

    pos_view = add(v)
    acc(pos_view, GL_FLOAT, len(v), "VEC3",
        min=v.min(axis=0).tolist(), max=v.max(axis=0).tolist())
    idx_view = add(f)
    acc(idx_view, GL_UNSIGNED_INT, len(f), "SCALAR")
    attrs = {"POSITION": 0}
    next_acc = 2

    if n is not None:
        nv = add(n)
        attrs["NORMAL"] = acc(nv, GL_FLOAT, len(n), "VEC3")
        next_acc = len(accessors)
    if t is not None:
        tv = add(t)
        attrs["TEXCOORD_0"] = acc(tv, GL_FLOAT, len(t), "VEC2")
        next_acc = len(accessors)
    if c is not None and texture_png is None:
        cview = add(np.asarray(c, dtype=np.uint8))
        attrs["COLOR_0"] = acc(cview, GL_UNSIGNED_BYTE, len(c), "VEC3",
                               normalized=True)

    ziel_liste = None
    if targets:
        ziel_liste = []
        for d in targets:
            d = np.asarray(d, dtype=np.float32).reshape(-1, 3)
            if len(d) != len(v):
                raise ValueError(
                    "Morph-Ziel hat %d Punkte, das Netz %d" % (len(d), len(v)))
            dv = add(d)
            ziel_liste.append({"POSITION": acc(
                dv, GL_FLOAT, len(d), "VEC3",
                min=d.min(axis=0).tolist(), max=d.max(axis=0).tolist())})

    prim = {"attributes": attrs, "indices": 1, "material": 0}
    if ziel_liste is not None:
        prim["targets"] = ziel_liste
    mesh = {"primitives": [prim]}
    if target_names:
        mesh["extras"] = {"targetNames": [str(n) for n in target_names]}

    gltf = {
        "asset": {"version": "2.0", "generator": "FaceScan (AndrexTheDev)"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": name}],
        "meshes": [mesh],
        "materials": [{"name": "scan", "doubleSided": True,
                       "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1],
                                                "metallicFactor": 0.0,
                                                "roughnessFactor": 0.75}}],
        "buffers": [{"byteLength": 0}],
        "bufferViews": views,
        "accessors": accessors,
    }

    if texture_png is not None:
        # Das Bild liegt im selben Puffer wie die Geometrie. Wichtig:
        # bufferViews MIT Bild brauchen ein 4-Byte-Alignment, und das Bild
        # selbst darf NICHT mit dem Leerzeichen-Padding des JSON verwechselt
        # werden -- deshalb hier 0x00 (wie beim BIN-Chunk).
        pad = (-offset) % 4
        if pad:
            chunks.append(b"\x00" * pad)
            offset += pad
        raw = bytes(texture_png)
        chunks.append(_pad4(raw, fill=b"\x00"))
        views.append({"buffer": 0, "byteOffset": offset,
                      "byteLength": len(raw)})
        offset += len(_pad4(raw, fill=b"\x00"))
        gltf.setdefault("samplers", []).append(
            {"magFilter": 9729, "minFilter": 9987,
             "wrapS": 10497, "wrapT": 10497})
        gltf["images"] = [{"bufferView": len(views) - 1,
                           "mimeType": "image/png", "name": "albedo"}]
        gltf["textures"] = [{"sampler": 0, "source": 0}]
        gltf["materials"][0]["pbrMetallicRoughness"]["baseColorTexture"] = {
            "index": 0, "texCoord": 0}

    bin_blob = b"".join(chunks)
    gltf["buffers"][0]["byteLength"] = len(bin_blob)
    json_blob = _pad4(json.dumps(gltf, separators=(",", ":")).encode("utf-8"),
                      fill=b" ")
    total = 12 + 8 + len(json_blob) + 8 + len(bin_blob)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<III", 0x46546C67, 2, total))
        fh.write(struct.pack("<II", len(json_blob), 0x4E4F534A))
        fh.write(json_blob)
        fh.write(struct.pack("<II", len(bin_blob), 0x004E4942))
        fh.write(bin_blob)
    return path


def read_glb(path: str):
    with open(path, "rb") as fh:
        blob = fh.read()
    magic, ver, total = struct.unpack("<III", blob[:12])
    assert magic == 0x46546C67, "kein GLB"
    assert total == len(blob), f"Laenge {len(blob)} != Header {total}"
    off = 12
    out = {}
    while off < len(blob):
        clen, ctype = struct.unpack("<II", blob[off:off + 8])
        data = blob[off + 8:off + 8 + clen]
        if ctype == 0x4E4F534A:
            out["json"] = json.loads(data.decode("utf-8"))
        elif ctype == 0x004E4942:
            out["bin"] = data
        off += 8 + clen
    g = out["json"]
    acc = g["accessors"][g["meshes"][0]["primitives"][0]["attributes"]["POSITION"]]
    bv = g["bufferViews"][acc["bufferView"]]
    start, length = bv["byteOffset"], bv["byteLength"]
    v = np.frombuffer(out["bin"][start:start + length], dtype="<f4").reshape(-1, 3)
    ia = g["accessors"][g["meshes"][0]["primitives"][0]["indices"]]
    ibv = g["bufferViews"][ia["bufferView"]]
    f = np.frombuffer(out["bin"][ibv["byteOffset"]:ibv["byteOffset"] + ibv["byteLength"]],
                      dtype="<u4").reshape(-1, 3)
    return {"vertices": v.astype(np.float64), "faces": f.astype(np.int64)}


# -------------------------------------------------------------- Prüfung ---

def roundtrip_check(path: str, v: np.ndarray, f: np.ndarray,
                    colors: np.ndarray | None = None, tol: float = 1e-4) -> dict:
    """Schreibt nichts neu -- liest die Datei und vergleicht mit dem Original.

    Damit ist bewiesen, dass ein ANDERES Programm (unser Leser) die Datei
    so versteht, wie wir sie gemeint haben.
    """
    back = None
    if path.endswith(".obj"):
        back = read_obj(path)
    elif path.endswith(".ply"):
        back = read_ply(path)
    elif path.endswith(".glb"):
        back = read_glb(path)
    else:
        raise ValueError(path)

    v = np.asarray(v, dtype=np.float64)
    f = np.asarray(f, dtype=np.int64)
    res = {
        "file": path,
        "vertices_ok": back["vertices"].shape == v.shape,
        "faces_ok": back["faces"].shape == f.shape,
        "max_vertex_error_mm": float(np.abs(back["vertices"] - v).max())
        if back["vertices"].shape == v.shape else float("inf"),
        "face_index_match": bool(np.array_equal(back["faces"], f))
        if back["faces"].shape == f.shape else False,
    }
    if colors is not None and "colors" in back and back["colors"].shape[0] == len(v):
        # OBJ speichert 0..1 floats, PLY 0..255 ints
        cb = back["colors"].astype(np.float64)
        if cb.max() <= 1.5:
            cb = cb * 255.0
        res["max_color_error"] = float(np.abs(cb - np.asarray(colors, dtype=np.float64)).max())
    res["passed"] = (res["vertices_ok"] and res["faces_ok"]
                     and res["max_vertex_error_mm"] < max(tol, 0.01)
                     and res["face_index_match"])
    return res
