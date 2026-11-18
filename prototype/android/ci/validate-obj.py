#!/usr/bin/env python3
"""Lädt nur den synthetischen Kotlin-Export mit einem unabhängigen OBJ-Parser."""
import json
import os
from pathlib import Path

import numpy as np
from trimesh.exchange.obj import load_obj


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
    # Degenerierte Dreiecke dürfen im Export nicht vorkommen.
    triangles = vertices[faces]
    doubled_area = np.linalg.norm(np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]), axis=1)
    if not np.all(doubled_area > 0):
        raise ValueError("Degenerate triangle exported")


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
