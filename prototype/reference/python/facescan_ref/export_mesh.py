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
import struct

import numpy as np

# ------------------------------------------------------------------ OBJ ---


def write_obj(path: str, v: np.ndarray, f: np.ndarray,
              colors: np.ndarray | None = None, name: str = "FaceScan"):
    """Wavefront OBJ mit Vertexfarben (v x y z r g b).

    Millimeter bleiben Millimeter: OBJ kennt keine Einheit, alle Profi-Tools
    fragen beim Import nach -- und Blender/Maya/Unity nehmen "1 Unit = 1 m"
    an, deshalb schreiben wir einen Hinweis in den Kopf. Der Nutzer stellt im
    Import 0.001 ein -- das sagen wir ihm im Export-Dialog der App.
    """
    v = np.asarray(v, dtype=np.float64)
    f = np.asarray(f, dtype=np.int64)
    c = (np.asarray(colors, dtype=np.float64) / 255.0) if colors is not None else None

    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"# FaceScan export -- {name}\n")
        fh.write("# Einheit: Millimeter (beim Import 0.001 skalieren)\n")
        fh.write(f"o {name}\n")
        for i in range(len(v)):
            if c is not None:
                fh.write("v %.6f %.6f %.6f %.6f %.6f %.6f\n"
                         % (v[i, 0], v[i, 1], v[i, 2], c[i, 0], c[i, 1], c[i, 2]))
            else:
                fh.write("v %.6f %.6f %.6f\n" % (v[i, 0], v[i, 1], v[i, 2]))
        for tri in f:
            fh.write("f %d %d %d\n" % (tri[0] + 1, tri[1] + 1, tri[2] + 1))
    return path


def read_obj(path: str):
    v, c, f = [], [], []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("v "):
                p = line.split()
                v.append([float(p[1]), float(p[2]), float(p[3])])
                if len(p) >= 7:
                    c.append([float(p[4]), float(p[5]), float(p[6])])
            elif line.startswith("f "):
                p = line.split()
                f.append([int(x.split("/")[0]) - 1 for x in p[1:4]])
    out = {"vertices": np.array(v), "faces": np.array(f, dtype=np.int64)}
    if c:
        out["colors"] = np.array(c)
    return out


# ------------------------------------------------------------------ PLY ---

_PLY_TYPES = {1: "b", 2: "h", 4: "i", 8: "d", 11: "f"}


def write_ply(path: str, v: np.ndarray, f: np.ndarray,
              colors: np.ndarray | None = None, binary: bool = True):
    """Stanford PLY, binär little-endian (oder ASCII zum Debuggen)."""
    v = np.asarray(v, dtype=np.float64)
    f = np.asarray(f, dtype=np.int64)
    c = np.asarray(colors, dtype=np.uint8) if colors is not None else None

    if not binary:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("ply\nformat ascii 1.0\n")
            fh.write(f"element vertex {len(v)}\n")
            fh.write("property float x\nproperty float y\nproperty float z\n")
            if c is not None:
                fh.write("property uchar red\nproperty uchar green\n"
                         "property uchar blue\n")
            fh.write(f"element face {len(f)}\nproperty list uchar int vertex_indices\n")
            fh.write("end_header\n")
            for i in range(len(v)):
                line = "%.6f %.6f %.6f" % (v[i, 0], v[i, 1], v[i, 2])
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
        if c is not None:
            header += ("property uchar red\nproperty uchar green\n"
                       "property uchar blue\n")
        header += f"element face {len(f)}\nproperty list uchar int vertex_indices\n"
        header += "end_header\n"
        fh.write(header.encode("ascii"))

        if c is not None:
            data = np.empty(len(v), dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
                                           ("r", "u1"), ("g", "u1"), ("b", "u1")])
            data["x"], data["y"], data["z"] = v[:, 0], v[:, 1], v[:, 2]
            data["r"], data["g"], data["b"] = c[:, 0], c[:, 1], c[:, 2]
            fh.write(data.tobytes())
        else:
            data = np.empty(len(v), dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4")])
            data["x"], data["y"], data["z"] = v[:, 0], v[:, 1], v[:, 2]
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
            faces = []
            for _ in range(n_face):
                cnt = struct.unpack(dtype + "B", fh.read(1))[0]
                faces.append(struct.unpack(dtype + "i" * cnt, fh.read(4 * cnt)))
            f = np.array(faces, dtype=np.int64)
        else:
            rest = fh.read().decode().splitlines()
            v = np.array([[float(x) for x in l.split()[:3]] for l in rest[:n_vert]])
            c = None
            if len(props) >= 6:
                c = np.array([[int(float(x)) for x in l.split()[3:6]] for l in rest[:n_vert]])
            f = np.array([[int(x) for x in l.split()[1:4]] for l in rest[n_vert:n_vert + n_face]])
    out = {"vertices": v, "faces": f}
    if c is not None:
        out["colors"] = c
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
              colors: np.ndarray | None = None, name: str = "FaceScan"):
    """Binäres glTF 2.0 (.glb) -- ein Container, alles inline.

    Warum GLB und nicht glTF+bin? Weil ein EINZELNES File beim Teilen,
    Importieren und Archivieren keine Frage aufwirft ("wo ist die .bin?").
    Für USDZ gilt genau dieselbe Überlegung (docs/05).
    """
    v = np.asarray(v, dtype=np.float32)
    f = np.asarray(f, dtype=np.uint32).reshape(-1)
    c = np.asarray(colors, dtype=np.uint8) if colors is not None else None

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

    pos_view = add(v)
    accessors.append({"bufferView": pos_view, "componentType": GL_FLOAT,
                      "count": len(v), "type": "VEC3",
                      "min": v.min(axis=0).tolist(), "max": v.max(axis=0).tolist()})
    idx_view = add(f)
    accessors.append({"bufferView": idx_view, "componentType": GL_UNSIGNED_INT,
                      "count": len(f), "type": "SCALAR"})
    attrs = {"POSITION": 0}
    if c is not None:
        # COLOR_0 als normalisierte ubyte-Vec3 (in glTF 2.0 zulässig)
        cview = add(np.asarray(c, dtype=np.uint8))
        accessors.append({"bufferView": cview, "componentType": GL_UNSIGNED_BYTE,
                          "count": len(c), "type": "VEC3", "normalized": True})
        attrs["COLOR_0"] = 2

    bin_blob = b"".join(chunks)
    gltf = {
        "asset": {"version": "2.0", "generator": "FaceScan (AndrexTheDev)"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": name}],
        "meshes": [{"primitives": [{"attributes": attrs, "indices": 1,
                                    "material": 0}]}],
        "materials": [{"name": "scan", "doubleSided": True,
                       "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1],
                                                "metallicFactor": 0.0,
                                                "roughnessFactor": 0.75}}],
        "buffers": [{"byteLength": len(bin_blob)}],
        "bufferViews": views,
        "accessors": accessors,
    }
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
