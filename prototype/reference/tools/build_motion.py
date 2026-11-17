#!/usr/bin/env python3
"""Stufe 5.9: die Bewegung der Aufnahme als BVH, CSV und JSON.

docs/05 (4.8) verlangt drei Motion-Formate. Was wir in M2 an Bewegung
haben, ist nicht der Rig (der kommt mit M3), sondern **die Aufnahme
selbst**: 16 Kameraposen auf einem Bogen um den Kopf. Umgerechnet in die
Sprache eines DCC-Programms heisst das: die Kamera steht fest und der
Kopf dreht sich auf einem Drehteller, und zwar genau durch die 16
Lagen, aus denen gemessen wurde.

Warum das trotzdem in ein BVH gehoert und nicht bloss in eine Tabelle:

* Wer die Aufnahme nachstellen will („zeig mir, was die Kamera gesehen
  hat"), laedt das BVH, haengt das Mesh dran und hat den Drehteller.
* Der Schreiber ist allgemein (Hierarchie + Kanaele). M3 schiebt den
  fertigen Rig hindurch, ohne ihn anzufassen.

Die Kamerapose (R, t) mit Welt -> Kamera (``p_cam = R p + t``) ist
GENAU die Transformation, die der Kopf relativ zur Kamera erfaehrt. Die
Umrechnung ist deshalb keine Naerung, sondern dieselbe Bewegung aus der
anderen Richtung betrachtet.

Einheiten: **Meter und Grad, Y-up** (docs/05, 6). BVH traegt keine
Einheit -- wer hier Millimeter hineinschreibt, bekommt in Blender einen
1000-fach zu grossen Sprung.

Aufruf:
    /tmp/qrenv/bin/python prototype/reference/tools/build_motion.py
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(HERE, "..", "python")
sys.path.insert(0, os.path.abspath(PY))

from facescan_ref import headmesh as hm           # noqa: E402
from facescan_ref import export_more as em        # noqa: E402

MESHES = os.path.abspath(os.path.join(HERE, "..", "meshes"))
RESULTS = os.path.abspath(os.path.join(HERE, "..", "results"))

# Dieselben Werte wie in run_m1.py -- sonst beschreibt das BVH eine
# andere Aufnahme als das Mesh, das daneben liegt.
N_FRAMES = 16
RADIUS_MM = 520.0
YAW_DEG = 75.0
PITCH_DEG = 9.0
# docs/03 (Framerate): 30 fps Burst. Die Pipeline selbst hat keine
# Zeitstempel, die Bildrate kommt aus der Kameravorgabe.
FPS = 30.0


def banner(text: str) -> None:
    print("\n" + "=" * 74)
    print(text)
    print("=" * 74)
    sys.stdout.flush()


def main() -> int:
    t_start = time.time()
    banner("Aufnahmebahn: 16 Kameraposen -> Kopfbewegung (BVH, CSV, JSON)")
    poses = hm.orbit_poses(N_FRAMES, radius=RADIUS_MM, yaw_deg=YAW_DEG,
                           pitch_deg=PITCH_DEG)
    print(f"  {len(poses)} Posen auf einem Bogen, Radius {RADIUS_MM:.0f} mm, "
          f"Yaw +-{YAW_DEG:.0f} deg, Pitch +-{PITCH_DEG:.0f} deg")

    # (R, t) ist die Kopftransformation im Kamerarahmen -- keine Umrechnung,
    # nur Einheiten: mm -> m, Bogenmass -> Grad.
    rows = []
    for r, t in poses:
        rows.append(np.concatenate([np.asarray(t, dtype=np.float64) / 1000.0,
                                    em.euler_zxy(r)]))
    values = np.array(rows, dtype=np.float64)
    # Euler-Winkel entwrappen: die Zerlegung liefert Werte in +/-180 Grad,
    # und zwischen Frame 8 und 9 springt die Gierachse von -175 auf +175.
    # Abgespielt wird das als 350 Grad Rueckwaertsdrall, weil BVH zwischen
    # zwei Frames linear interpoliert und nichts von Winkeln weiss.
    rot = np.zeros(values.shape[1], dtype=bool)
    rot[3:] = True
    jump_before = float(np.abs(np.diff(values[:, 3:], axis=0)).max())
    values = em.unwrap_degrees(values, rot)
    jump_after = float(np.abs(np.diff(values[:, 3:], axis=0)).max())
    print(f"  Translation {np.abs(values[:, :3]).max():.3f} m, Rotation bis "
          f"{np.abs(values[:, 3:]).max():.1f} deg (Reihenfolge ZXY)")
    print(f"  groesster Sprung zwischen zwei Frames: {jump_before:.1f} deg "
          f"-> entwrappt {jump_after:.1f} deg")

    joints = [{
        "name": "Head",
        "parent": None,
        "offset": (0.0, 0.0, 0.0),
        # 6 Kanalwerte je Frame: Position (nur das Wurzelgelenk hat sie)
        # und die drei Euler-Winkel.
        "channels": ["Xposition", "Yposition", "Zposition",
                     "Zrotation", "Xrotation", "Yrotation"],
        # End Site: BVH braucht ihn nicht, aber ohne ihn sieht man in
        # Blender nur einen Punkt. 12 cm nach oben = durch den Kopf.
        "end": (0.0, 0.12, 0.0),
    }]
    frame_time = 1.0 / FPS
    channels = ["%s_%s" % (j["name"], c) for j in joints for c in j["channels"]]

    base = os.path.join(MESHES, "facescan_m1_capture")
    files = [
        ("BVH", base + ".bvh",
         lambda p: em.write_bvh(p, joints, values, frame_time)),
        ("CSV", base + ".csv",
         lambda p: em.write_motion_csv(p, channels, values, frame_time)),
        ("JSON", base + ".json",
         lambda p: em.write_motion_json(
             p, channels, values, frame_time, name="FaceScan capture",
             meta={"source": "orbit_poses(N=%d, radius=%.0f mm)" %
                   (N_FRAMES, RADIUS_MM),
                   "meaning": "Kopfbewegung vor fester Kamera "
                              "(= Aufnahmebahn, umgerechnet)"})),
    ]
    sizes = {}
    for tag, path, fn in files:
        fn(path)
        sizes[tag] = os.path.getsize(path) / 1024.0
        print(f"  {tag:4s} {sizes[tag]:8.1f} kB  {os.path.basename(path)}")

    # ------------------------------------------------------ Ruecklese ---
    banner("Ruecklese mit dem eigenen Leser")
    rb = em.read_bvh(base + ".bvh")
    rc = em.read_motion_csv(base + ".csv")
    rj = em.read_motion_json(base + ".json")
    err_b = float(np.abs(rb["values"] - values).max())
    err_c = float(np.abs(rc["values"] - values).max())
    err_j = float(np.abs(rj["values"] - values).max())
    ok = (rb["consistent"] and rb["frames_read"] == N_FRAMES
          and rc["channels"] == channels and rj["channels"] == channels
          and max(err_b, err_c, err_j) < 1e-5)
    print(f"  BVH : {rb['frames_read']} Frames (deklariert "
          f"{rb['frames_declared']}), {len(rb['channels'])} Kanaele, "
          f"Frame Time {rb['frame_time']:.6f} s, max. Abweichung "
          f"{err_b:.1e}")
    print(f"  CSV : {rc['frames']} Zeilen, {len(rc['channels'])} Spalten, "
          f"max. Abweichung {err_c:.1e}")
    print(f"  JSON: {rj['frames']} Frames, Einheiten {rj['units']}, "
          f"Euler {rj['euler_order']}, max. Abweichung {err_j:.1e}")
    print(f"  -> Ruecklese {'OK' if ok else 'FEHLGESCHLAGEN'}")

    report = {
        "frames": int(N_FRAMES),
        "fps": FPS,
        "frame_time_s": frame_time,
        "channels": channels,
        "units": {"translation": "m", "rotation": "deg"},
        "euler_order": "ZXY",
        "up_axis": "Y",
        "radius_mm": RADIUS_MM,
        "translation_range_m": [float(values[:, :3].min()),
                                float(values[:, :3].max())],
        "rotation_range_deg": [float(values[:, 3:].min()),
                               float(values[:, 3:].max())],
        "max_step_deg_before_unwrap": jump_before,
        "max_step_deg_after_unwrap": jump_after,
        "files_kb": sizes,
        "roundtrip_max_error": max(err_b, err_c, err_j),
        "roundtrip_ok": bool(ok),
    }
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, "m2b_motion_report.json"), "w",
              encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(f"\nFertig in {time.time() - t_start:.0f} s")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
