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


if __name__ == "__main__":
    root = Path(os.environ["RUNNER_TEMP"])
    try:
        validate(root / "facescan-synthetic.obj", root / "facescan-synthetic-obj-reference.json")
    except Exception as exc:
        print(f"::error title=OBJ-Parser::Synthetic OBJ failed independent parse: {type(exc).__name__}: {exc}")
        raise
    print("::notice title=OBJ-Parser::Synthetic OBJ: positions, normals and triangles round-trip through trimesh")
