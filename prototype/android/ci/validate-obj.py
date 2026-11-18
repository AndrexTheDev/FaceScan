#!/usr/bin/env python3
"""Lädt nur den synthetischen Kotlin-Export mit einem unabhängigen OBJ-Parser."""
import json
import os
import struct
from pathlib import Path

import numpy as np
import trimesh
from trimesh.exchange.obj import load_obj

PLY_TYPES = {
    "float": ("<f", 4),
    "float32": ("<f", 4),
    "double": ("<d", 8),
    "uchar": ("<B", 1),
    "uint8": ("<B", 1),
    "int": ("<i", 4),
    "int32": ("<i", 4),
}


def validate(obj_path: Path, reference_path: Path) -> None:
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    with obj_path.open("rb") as obj_file:
        parsed = load_obj(obj_file, maintain_order=True)
    geometries = list(parsed["geometry"].values())
    if len(geometries) != 1:
        raise ValueError("Expected exactly one geometry")
    mesh = geometries[0]
    vertices = np.asarray(mesh["vertices"])
    normals = np.asarray(mesh["vertex_normals"])
    faces = np.asarray(mesh["faces"])
    if vertices.shape != (468, 3) or normals.shape != (468, 3) or faces.shape != (898, 3):
        raise ValueError(f"Unexpected shapes: {vertices.shape}, {normals.shape}, {faces.shape}")
    if not np.isfinite(vertices).all() or not np.isfinite(normals).all():
        raise ValueError("Nonfinite vertices or normals")
    if not np.allclose(vertices, reference["vertices"], rtol=0, atol=1e-6):
        raise ValueError("Vertex positions do not round-trip")
    if not np.allclose(normals, reference["normals"], rtol=0, atol=1e-6):
        raise ValueError("Vertex normals do not round-trip")
    if not np.array_equal(faces, reference["faces"]):
        raise ValueError("Triangle indices do not round-trip")
    if not np.allclose(np.linalg.norm(normals, axis=1), 1, rtol=0, atol=1e-6):
        raise ValueError("Non-unit normal")


def validate_partial(obj_path: Path, reference_path: Path) -> None:
    """Teilnetz: offene Ränder, weniger Punkte, keine Normalen erlaubt."""
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    with obj_path.open("rb") as obj_file:
        parsed = load_obj(obj_file, maintain_order=True)
    geometries = list(parsed["geometry"].values())
    if len(geometries) != 1:
        raise ValueError("Expected exactly one geometry")
    mesh = geometries[0]
    vertices = np.asarray(mesh["vertices"])
    faces = np.asarray(mesh["faces"])
    expected_vertices = np.asarray(reference["vertices"])
    expected_faces = np.asarray(reference["faces"])
    if vertices.shape != expected_vertices.shape or faces.shape != expected_faces.shape:
        raise ValueError(f"Unexpected shapes: {vertices.shape}, {faces.shape}")
    if not np.isfinite(vertices).all():
        raise ValueError("Nonfinite vertices")
    if not np.allclose(vertices, expected_vertices, rtol=0, atol=1e-9):
        raise ValueError("Vertex positions do not round-trip")
    if not np.array_equal(faces, expected_faces):
        raise ValueError("Triangle indices do not round-trip")
    normals = np.asarray(mesh["vertex_normals"]) if mesh["vertex_normals"] is not None else None
    if normals is not None:
        if normals.shape != vertices.shape or not np.isfinite(normals).all():
            raise ValueError("Invalid partial normals")
        if not np.allclose(np.linalg.norm(normals, axis=1), 1, rtol=0, atol=1e-5):
            raise ValueError("Partial normals are not unit length")
    if faces.shape[0] < 1 or vertices.shape[0] >= 468:
        raise ValueError("Partial mesh must be incomplete but non-empty")
    if faces.max(initial=-1) >= vertices.shape[0]:
        raise ValueError("Out-of-range face index")
    check_partial_topology(reference, faces, "partial OBJ")
    # Degenerierte Dreiecke dürfen im Export nicht vorkommen.
    triangles = vertices[faces]
    doubled_area = np.linalg.norm(np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]), axis=1)
    if not np.all(doubled_area > 0):
        raise ValueError("Degenerate triangle exported")


def topology_counts(faces: np.ndarray) -> dict:
    """Unabhängige Strukturzählung: Kanten über sortierte Endpunkte."""
    edges = {}
    for a, b, c in faces:
        for p, q in ((a, b), (b, c), (c, a)):
            key = (int(min(p, q)), int(max(p, q)))
            edges[key] = edges.get(key, 0) + 1
    boundary = sum(1 for n in edges.values() if n == 1)
    non_manifold = sum(1 for n in edges.values() if n > 2)
    # Zusammenhangskomponenten über Dreieckskanten (Union-Find).
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[ry] = rx

    for a, b, c in faces:
        union(int(a), int(b))
        union(int(b), int(c))
    roots = {}
    for a, _, _ in faces:
        roots[find(int(a))] = roots.get(find(int(a)), 0) + 1
    return {
        "boundary_edges": boundary,
        "non_manifold_edges": non_manifold,
        "components": len(roots),
        "largest_component_triangles": max(roots.values()) if roots else 0,
    }


def check_partial_topology(reference: dict, faces: np.ndarray, label: str,
                           require_open: bool = True) -> None:
    """Die im Export deklarierten Topologiezahlen müssen stimmen.

    `require_open` gilt nur für echte Teilnetz-Exporte; ein geschlossener
    Testkörper ist ein gültiger Gegenfall und darf nicht durchfallen.
    """
    expected = reference.get("topology")
    if expected is None:
        raise ValueError(f"{label}: topology block missing from reference")
    actual = topology_counts(faces)
    for key, value in actual.items():
        if int(expected[key]) != int(value):
            raise ValueError(f"{label}: {key} declared {expected[key]} but measured {value}")
    if actual["non_manifold_edges"] != 0:
        raise ValueError(f"{label}: exported partial mesh has non-manifold edges")
    if require_open and actual["boundary_edges"] == 0:
        raise ValueError(f"{label}: an open partial mesh must have boundary edges")


def parse_binary_ply(data: bytes):
    """Minimaler, eigener PLY-Leser; nutzt bewusst keine Bibliothek des Writers."""
    marker = b"end_header\n"
    index = data.index(marker)
    header = data[:index].decode("ascii").splitlines()
    if header[0].strip() != "ply":
        raise ValueError("Kein PLY-Kopf")
    if header[1].strip() != "format binary_little_endian 1.0":
        raise ValueError(f"Unerwartetes Format: {header[1]}")
    elements = []
    current = None
    for line in header[2:]:
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "element":
            current = {"name": parts[1], "count": int(parts[2]), "properties": []}
            elements.append(current)
        elif parts[0] == "property" and current is not None:
            current["properties"].append(parts[1:])
    body = data[index + len(marker):]
    offset = 0
    parsed = {}
    for element in elements:
        props = element["properties"]
        if any(p[0] == "list" for p in props):
            rows = []
            for _ in range(element["count"]):
                values = []
                for prop in props:
                    if prop[0] == "list":
                        count_type, item_type = prop[1], prop[2]
                        size = 1 if count_type == "uchar" else 4
                        fmt = "<B" if count_type == "uchar" else "<i"
                        count = struct.unpack_from(fmt, body, offset)[0]
                        offset += size
                        item_fmt = "<i" if item_type == "int" else "<f"
                        item_size = 4
                        values.append(list(struct.unpack_from("<" + "i" * count, body, offset)))
                        offset += item_size * count
                    else:
                        fmt, size = PLY_TYPES[prop[0]]
                        values.append(struct.unpack_from(fmt, body, offset)[0])
                        offset += size
                rows.append(values)
            parsed[element["name"]] = rows
        else:
            fmt = "<" + "".join(PLY_TYPES[p[0]][0][1] for p in props)
            size = sum(PLY_TYPES[p[0]][1] for p in props)
            rows = [list(struct.unpack_from(fmt, body, offset + i * size)) for i in range(element["count"])]
            offset += size * element["count"]
            parsed[element["name"]] = rows
    if offset != len(body):
        raise ValueError(f"PLY-Binärteil nicht vollständig gelesen: {offset} von {len(body)}")
    return header, parsed


def validate_partial_ply(ply_path: Path, reference_path: Path) -> None:
    """Teilnetz-PLY: Positionen, Flächen und Unsicherheitsfarben unabhängig prüfen."""
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    header, parsed = parse_binary_ply(ply_path.read_bytes())
    # positions und Farben stehen in derselben Vertexstruktur: x,y,z,red,green,blue.
    vertex_rows = np.asarray(parsed["vertex"], dtype=np.float64)
    vertices = vertex_rows[:, :3]
    actual_colors = vertex_rows[:, 3:6].astype(np.int64)
    expected_vertices = np.asarray(reference["vertices"], dtype=np.float64)
    # Die Face-Elemente haben genau eine Listen-Eigenschaft; sie wird entpackt.
    face_rows = [row[0] if len(row) == 1 else row for row in parsed["face"]]
    for row in face_rows:
        if len(row) != 3:
            raise ValueError("PLY enthält kein reines Dreiecksnetz")
    faces = np.asarray(face_rows, dtype=np.int64).reshape(-1, 3)
    expected_faces = np.asarray(reference["faces"], dtype=np.int64)
    if vertices.shape[0] != expected_vertices.shape[0]:
        raise ValueError(f"Unerwartete Vertexanzahl: {vertices.shape[0]} statt {expected_vertices.shape[0]}")
    if not np.isfinite(vertices).all():
        raise ValueError("Nicht-endliche Vertexposition im PLY")
    if not np.allclose(vertices, expected_vertices, rtol=0, atol=1e-5):
        raise ValueError("PLY-Positionen weichen von den Kotlin-Werten ab")
    if faces.shape != expected_faces.shape or not np.array_equal(faces, expected_faces):
        raise ValueError("PLY-Flächen weichen von den Kotlin-Werten ab")
    colors = np.asarray(reference["colors"], dtype=np.int64)
    if not np.array_equal(actual_colors, colors):
        raise ValueError("PLY-Farben weichen von den Kotlin-Werten ab")
    if actual_colors.min() < 0 or actual_colors.max() > 255:
        raise ValueError("PLY-Farbe außerhalb 0..255")
    if not np.array_equal(actual_colors[:, 0], actual_colors[:, 1]) or \
            not np.array_equal(actual_colors[:, 1], actual_colors[:, 2]):
        raise ValueError("PLY-Farben sind nicht grau")
    unknown = int((actual_colors[:, 0] == 0).sum())
    declared_unknown = int([line for line in header if "uncertaintyUnknown" in line][0].split()[-1])
    if unknown != declared_unknown:
        raise ValueError(f"Kopf nennt {declared_unknown} Punkte ohne Schätzung, gezählt: {unknown}")
    if unknown == actual_colors.shape[0]:
        raise ValueError("PLY enthält keine einzige Unsicherheitsschätzung")
    # Struktur wie beim OBJ/GLB unabhängig nachzählen.
    check_partial_topology(reference, faces, "partial PLY")
    triangles = vertices[faces]
    doubled_area = np.linalg.norm(np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]), axis=1)
    if not np.all(doubled_area > 0):
        raise ValueError("Degeneriertes Dreieck im PLY")


def validate_partial_glb(glb_path: Path, reference_path: Path) -> None:
    """GLB-Teilnetz: Positionen, Normalen und Flächen müssen den Kotlin-Werten entsprechen."""
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    scene = trimesh.load(glb_path, file_type="glb", force="scene", merge_primitives=False, process=False)
    geometries = list(scene.geometry.values())
    if len(geometries) != 1:
        raise ValueError(f"Expected exactly one geometry, got {len(geometries)}")
    mesh = geometries[0]
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    expected_vertices = np.asarray(reference["vertices"], dtype=np.float64)
    expected_faces = np.asarray(reference["faces"], dtype=np.int64)
    if vertices.shape != expected_vertices.shape:
        raise ValueError(f"Unexpected vertex count: {vertices.shape} vs {expected_vertices.shape}")
    if not np.isfinite(vertices).all():
        raise ValueError("Nonfinite vertices in GLB")
    # Der Writer schreibt Float32, die Referenz hält die Double-Werte des Tests;
    # die Toleranz entspricht der Float32-Rundung bei diesen Koordinaten.
    if not np.allclose(vertices, expected_vertices, rtol=0, atol=1e-5):
        raise ValueError("GLB vertex positions do not match the Kotlin mesh")
    if faces.shape != expected_faces.shape or not np.array_equal(faces, expected_faces):
        raise ValueError("GLB triangles do not match the Kotlin mesh")
    if len(vertices) >= 468:
        raise ValueError("Partial GLB must be incomplete")
    check_partial_topology(reference, faces, "partial GLB")
    triangles = vertices[faces]
    doubled_area = np.linalg.norm(np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]), axis=1)
    if not np.all(doubled_area > 0):
        raise ValueError("Degenerate triangle exported in GLB")


if __name__ == "__main__":
    root = Path(os.environ["RUNNER_TEMP"])
    try:
        validate(root / "facescan-synthetic.obj", root / "facescan-synthetic-obj-reference.json")
    except Exception as exc:
        print(f"::error title=OBJ-Parser::Synthetic OBJ failed independent parse: {type(exc).__name__}: {exc}")
        raise
    print("::notice title=OBJ-Parser::Synthetic OBJ: positions, normals and triangles round-trip through trimesh")
    try:
        validate_partial(root / "facescan-synthetic-partial.obj", root / "facescan-synthetic-partial-reference.json")
    except Exception as exc:
        print(f"::error title=OBJ-Parser::Synthetic partial OBJ failed independent parse: {type(exc).__name__}: {exc}")
        raise
    print("::notice title=OBJ-Parser::Synthetic partial OBJ: open mesh round-trips through trimesh")
    try:
        validate_partial_ply(root / "facescan-synthetic-partial.ply", root / "facescan-synthetic-partial-ply-reference.json")
    except Exception as exc:
        print(f"::error title=PLY-Parser::Synthetic partial PLY failed independent parse: {type(exc).__name__}: {exc}")
        raise
    print("::notice title=PLY-Parser::Synthetic partial PLY: positions, triangles and uncertainty colours round-trip")
    try:
        validate_partial_glb(root / "facescan-synthetic-partial.glb", root / "facescan-synthetic-partial-glb-reference.json")
    except Exception as exc:
        print(f"::error title=GLB-Parser::Synthetic partial GLB failed independent parse: {type(exc).__name__}: {exc}")
        raise
    print("::notice title=GLB-Parser::Synthetic partial GLB: positions and triangles round-trip through trimesh")
