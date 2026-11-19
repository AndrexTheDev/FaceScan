#!/usr/bin/env python3
"""Selbsttest des GLB-Metadatenpruefers mit kuenstlichen Dateien.

Ohne diesen Test waere unklar, ob der Pruefer ueberhaupt anschlaegt: ein
Pruefskript, das immer "in Ordnung" meldet, ist schlimmer als keines.
"""
import copy
import importlib.util
import json
import struct
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_glb_metadata",
                                                  HERE / "validate-glb-metadata.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = load_validator()
REASONS = {key: 0 for key in VALIDATOR.POSE_DROP_REASONS}
ZONES = "forehead=2/2,eyes=7/7,nose=14/14,mouth=4/4,chin=3/3"


def extras(**overrides):
    base = {
        "units": "cm", "limitations": "x", "droppedDegenerateTriangles": 0,
        "topology": {"vertices": 6, "triangles": 4, "boundaryEdges": 3,
                     "nonManifoldEdges": 0, "components": 1,
                     "largestComponentTriangles": 4, "note": "n"},
        "zoneCoverage": ZONES,
        "depthUncertaintyCm": {"median": 0.1, "high": 0.2, "samples": 5, "note": "n"},
        "viewSupport": {"medianUsedViews": 3.0, "fractionThreePlus": 1.0,
                        "twoViewOnly": 0, "triangulated": 30, "note": "n"},
        "pointLoss": {"triangulated": 30, "missing": 0, "tooFewViews": 0,
                      "insufficientParallax": 0, "behindCamera": 0,
                      "unstableGeometry": 0, "noConsensus": 0, "unknown": 0, "note": "n"},
        "focalConsistency": {"views": 3, "medianFocalPx": 760.0, "assumedFocalPx": 760.0,
                            "relativeSpread": 0.01, "deviationFromAssumed": 0.0,
                            "agreeingViews": 3, "consistent": True, "note": "n"},
        "viewUse": {"stored": 3, "used": 3, "notStored": 1, "dropped": 0,
                    "reasons": dict(REASONS), "complete": True, "note": "n"},
    }
    base.update(overrides)
    return base


REFERENCE = {
    "views": 3,
    "pointLoss": {"triangulated": 30, "missing": 0},
    "focalConsistency": {"views": 3, "consistent": True},
    "viewUse": {"stored": 3, "used": 3, "notStored": 1, "reasons": dict(REASONS)},
    "zones": ZONES,
}


def build_glb(document, positions=6, indices=12):
    js = json.dumps(document).encode("utf-8")
    js += b" " * ((4 - len(js) % 4) % 4)
    binary = b"\0" * (indices * 2)
    total = 12 + 8 + len(js) + 8 + len(binary)
    return (struct.pack("<III", 0x46546C67, 2, total)
            + struct.pack("<II", len(js), 0x4E4F534A) + js
            + struct.pack("<II", len(binary), 0x004E4942) + binary)


class ValidatorTest(unittest.TestCase):
    def test_consistent_metadata_passes(self):
        document = {"asset": {"version": "2.0", "extras": extras()},
                    "accessors": [{"count": 6}, {"count": 6}, {"count": 12}]}
        loss, focal, use, zones = VALIDATOR.verify(document, REFERENCE)
        self.assertEqual(30, loss["triangulated"])
        self.assertTrue(focal["consistent"])
        self.assertEqual(3, use["used"])
        self.assertEqual(30, sum(zones.values()))

    def test_contradictions_are_rejected(self):
        def verify(**overrides):
            document = {"asset": {"version": "2.0", "extras": extras(**overrides)},
                        "accessors": [{"count": 6}, {"count": 6}, {"count": 12}]}
            return VALIDATOR.verify(document, REFERENCE)

        loss = extras()["pointLoss"] | {"missing": 3}
        with self.assertRaises(VALIDATOR.Failure):
            verify(pointLoss=loss)
        with self.assertRaises(VALIDATOR.Failure):
            # Kennzeichen widerspricht der Streuung.
            verify(focalConsistency=extras()["focalConsistency"] | {"consistent": False})
        with self.assertRaises(VALIDATOR.Failure):
            verify(viewUse=extras()["viewUse"] | {"dropped": 2})
        with self.assertRaises(VALIDATOR.Failure):
            verify(zoneCoverage="forehead=2/2,eyes=9/7,nose=14/14,mouth=4/4,chin=3/3")
        with self.assertRaises(VALIDATOR.Failure):
            verify(zoneCoverage="forehead=2/2,eyes=7/7,nose=14/14,mouth=4/4")
        with self.assertRaises(VALIDATOR.Failure):
            verify(topology=extras()["topology"] | {"vertices": 5})
        with self.assertRaises(VALIDATOR.Failure):
            verify(viewUse=extras()["viewUse"] | {"reasons": {}})

    def test_reference_mismatch_and_broken_file(self):
        document = {"asset": {"version": "2.0", "extras": extras()},
                    "accessors": [{"count": 6}, {"count": 6}, {"count": 12}]}
        broken = copy.deepcopy(REFERENCE)
        broken["viewUse"]["notStored"] = 0
        with self.assertRaises(VALIDATOR.Failure):
            VALIDATOR.verify(document, broken)
        with self.assertRaises(VALIDATOR.Failure):
            VALIDATOR.verify({"asset": {"extras": {}}}, REFERENCE)
        # Kaputte Bytes: falscher Magic-Wert.
        with self.assertRaises(VALIDATOR.Failure):
            VALIDATOR.read_glb_bytes(b"nicht-glb")
        with self.assertRaises(VALIDATOR.Failure):
            VALIDATOR.read_glb_bytes(build_glb(document)[:-4])


if __name__ == "__main__":
    unittest.main()
