#!/usr/bin/env python3
"""Stufe 6.2, dritter Teil: Sockel und Druckprüfung (docs/05, 12.2).

Das wasserdichte Netz aus `build_watertight.py` ist geschlossen, aber
nicht druckbar: es hat keine Standfläche, und niemand hat gemessen, ob
irgendwo ein Nasenflügel dünner ist als eine Düse breit. Genau das steht
in docs/05 (12.2) noch offen, und genau das macht dieses Skript.

Vier Schritte:

  1. Querschnittsprofil des Indikatorfeldes messen und daraus die
     Schnitthöhe bestimmen -- nicht raten, sondern die niedrigste Höhe
     nehmen, an der der Querschnitt 25 % seines Maximums erreicht.
  2. Das Feld unterhalb dieser Höhe durch einen Kegelstumpf ersetzen.
     Das ist der Sockel, und er verschmilzt mit dem Kopf zu EINEM Körper,
     weil beides dasselbe Feld ist.
  3. Neu marchieren, aufräumen und gegenlesen (eigener Leser + trimesh).
  4. Die drei Prüfungen rechnen, vorher und nachher: kleinste lokale
     Dicke, Überhangfläche, Kippsicherheit.

Aufruf:
    /tmp/qrenv/bin/python prototype/reference/tools/build_print.py
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

from facescan_ref import export_more as em                          # noqa: E402
from facescan_ref import metrics as mt                              # noqa: E402
from facescan_ref import meshopt as mo                              # noqa: E402
from facescan_ref import printcheck as pc                           # noqa: E402
from facescan_ref import repair                                     # noqa: E402

MESHES = os.path.abspath(os.path.join(HERE, "..", "meshes"))
RESULTS = os.path.abspath(os.path.join(HERE, "..", "results"))

POISSON_RES = 192
TIE_EPS = 1e-5
# Der Sockel sitzt dort, wo der Querschnitt erstmals einen Viertel seines
# Maximums erreicht. Tiefer geschnitten wäre die Büste ein Stiel, höher
# nähme man dem Kopf zu viel von seiner Unterseite.
CUT_FRAC = 0.25
PLINTH_MM = 35.0          # Höhe des Sockels
PLINTH_CLEAR_MM = 3.0     # Luft zwischen Kopf und Sockelrand an der Schnittstelle
PLINTH_FLARE_MM = 12.0    # wieviel der Sockel nach unten breiter wird
OVERHANG_DEG = 45.0       # was ein FDM-Drucker noch frei drucken kann
N_SAMPLES = 20_000


def banner(text: str) -> None:
    print("\n" + "=" * 74)
    print(text)
    print("=" * 74)


def main() -> int:
    t_start = time.time()
    os.makedirs(MESHES, exist_ok=True)
    os.makedirs(RESULTS, exist_ok=True)

    banner("DRUCKBAR  Sockel, Wandstaerke, Ueberhang, Kippsicherheit")

    skin = np.load(os.path.join(MESHES, "watertight_skin.npz"))
    sv, sf = skin["v"], skin["f"]
    nrm = mt.vertex_normals(sv, sf)
    t0 = time.time()
    po = repair.poisson_grid(sv, nrm, sv.min(axis=0), sv.max(axis=0),
                             res=POISSON_RES, tie_eps=TIE_EPS,
                             return_grid=True)
    print(f"  Indikatorfeld {po['grid'].shape} in {time.time() - t0:.1f} s "
          f"(Gitterkante {po['voxel_mm']:.2f} mm)")
    chi, lo, h, level = po["grid"], po["lo"], po["h"], po["level"]

    head_v, head_f, head_info = repair.clean_mesh(po["vertices"],
                                                  po["faces"].astype(np.int64))
    print(f"  Kopf: {len(head_v):,} Punkte / {len(head_f):,} Dreiecke, "
          f"{repair.watertight_report(head_f)['boundary_edges']} Randkanten")

    # -------------------------------------------------- 1) Schnitthöhe ----
    banner("1)  Querschnittsprofil und Schnitthoehe")
    prof = pc.cross_section_profile(chi, lo, h, level)
    area = prof["area_cm2"]
    z = prof["z_mm"]
    first = int(np.argmax(area > 0.0))
    last = int(len(area) - 1 - np.argmax(area[::-1] > 0.0))
    print(f"  Kopf reicht von z = {z[first]:.1f} mm bis z = {z[last]:.1f} mm "
          f"({z[last] - z[first]:.0f} mm hoch)")
    print(f"  groesster Querschnitt {area.max():.1f} cm² bei "
          f"z = {z[int(np.argmax(area))]:.1f} mm")
    for k in range(first, last + 1, max(1, (last - first) // 12)):
        print(f"    z = {z[k]:7.1f} mm   {area[k]:6.1f} cm²  "
              f"{'#' * int(area[k] * 0.6)}")
    # Der Verlauf wächst vom Hals bis zur Schädelmitte monoton -- eine
    # Taille gibt es bei einem reinen Kopfscan nicht. Die Regel nimmt
    # deshalb die niedrigste Stelle mit ausreichend Querschnitt.
    target = CUT_FRAC * float(area.max())
    ok = np.flatnonzero(area[:int(np.argmax(area)) + 1] >= target)
    k_cut = int(ok[0]) if len(ok) else int(np.argmax(area))
    z_cut = float(z[k_cut])
    print(f"  Regel: tiefste Hoehe mit >= {100 * CUT_FRAC:.0f} % des Maximums "
          f"= {target:.1f} cm²")
    print(f"  -> Schnitt bei z = {z_cut:.1f} mm, Querschnitt dort "
          f"{area[k_cut]:.1f} cm²")

    centre_xy = (float(lo[0]) + h * chi.shape[0] * 0.5,
                 float(lo[1]) + h * chi.shape[1] * 0.5)
    # Achse und Radius am NETZ gemessen, nicht am Feld: das Feld enthält
    # die Rauschinseln, und die wären mitgezählt worden.
    r_head, axis_xy = pc.slice_axis_radius(head_v, z_cut, slab_mm=2.0 * h)
    r_top = r_head + PLINTH_CLEAR_MM
    r_bottom = r_top + PLINTH_FLARE_MM
    room = pc.grid_room_mm(chi, lo, h, axis_xy)
    # Reicht das Gitter? Der Sockel ist breiter als der Hals, und wenn er
    # über den Gitterrand läuft, wird er abgeschnitten -- und offen. Also
    # wird das Feld seitlich erweitert, statt die Rekonstruktion auf einem
    # gröberen Gitter zu wiederholen.
    pad = int(np.ceil((r_bottom + 2.0 * h - room) / h)) if r_bottom + 2.0 * h > room else 0
    if pad > 0:
        chi_e, lo_e, leak = pc.extend_field(chi, lo, h, level, pad)
        print(f"  Feld seitlich um {pad} Zellen erweitert "
              f"({chi.shape} -> {chi_e.shape}); am alten Rand lagen "
              f"{leak} Knoten innen")
        if leak:
            print("  ACHTUNG: dort wuerde die Erweiterung ein Leck "
                  "erzeugen -- das Feld ist am Rand nicht ueberall aussen")
    else:
        chi_e, lo_e, leak = chi, lo, 0
    room_e = pc.grid_room_mm(chi_e, lo_e, h, axis_xy)
    z_base = z_cut - PLINTH_MM
    print(f"  der Halsausschnitt sitzt {np.hypot(axis_xy[0] - centre_xy[0], axis_xy[1] - centre_xy[1]):.1f} mm "
          f"neben der Gittermitte -- der Kopf steht schief,")
    print("  deshalb ist die Schnittebene die Achse und nicht das Gitter")
    print(f"  Kopf reicht dort bis r = {r_head:.1f} mm; das Gitter gab "
          f"r = {room:.1f} mm her, nach der Erweiterung {room_e:.1f} mm")
    print(f"  Sockel von r = {r_top:.1f} mm auf {r_bottom:.1f} mm, "
          f"Hoehe {PLINTH_MM:.0f} mm, Standflaeche bei z = {z_base:.1f} mm")

    # ----------------------------------------------- 2) Feld beschneiden --
    banner("2)  Sockel ans Feld setzen (nicht ans Netz)")
    chi2 = pc.cut_below(chi_e, lo_e, h, level, z_cut)
    chi2 = pc.add_plinth(chi2, lo_e, h, level, z_cut, z_base, r_top, r_bottom,
                         axis_xy)
    changed = int((chi2 != chi_e).sum())
    print(f"  {changed:,} von {chi_e.size:,} Knoten geaendert")

    # ------------------------------------------------------ 3) Marchieren --
    banner("3)  Neu marchieren und aufraeumen")
    t0 = time.time()
    raw_v, raw_f, ties = repair.march_indicator(chi2, lo_e, h, level,
                                                tie_eps=TIE_EPS)
    print(f"  {len(raw_v):,} Punkte / {len(raw_f):,} Dreiecke in "
          f"{time.time() - t0:.1f} s ({ties} Krawatten gebrochen)")
    bust_v, bust_f, info = repair.clean_mesh(raw_v, raw_f)
    print(f"  Umlaufrichtung: {info['winding_edges_before']:,} Kanten mit "
          f"gleichsinnigen Nachbarn -> {info['winding_edges_after']}")
    print(f"  ohne Nulldreiecke: {info['triangles']:,} Dreiecke, "
          f"{info['boundary_edges_after_drop']} Randkanten, "
          f"{info['loops_filled']} nachgestopft "
          f"({info['triangles_added']} neue Dreiecke)")
    print(f"  {info['islands']} Inseln, die groesste behalten "
          f"({info['islands_other_triangles']} Dreiecke in den anderen, "
          f"groesste davon {info['island_next']})")
    rep = repair.watertight_report(bust_f)
    print(f"  Randkanten: {rep['boundary_edges']} | nicht-manigfaltig: "
          f"{rep['non_manifold_edges']} | Komponenten: {rep['components']} | "
          f"Euler: {rep['euler']}")
    print(f"  WASSERDICHT: {rep['watertight']}")
    p = bust_v[bust_f]
    vol = abs(float(np.einsum("ij,ij->i", p[:, 0],
                              np.cross(p[:, 1] - p[:, 0],
                                       p[:, 2] - p[:, 0])).sum() / 6.0))
    print(f"  Volumen {vol / 1000.0:.1f} cm³, Hoehe "
          f"{bust_v[:, 2].max() - bust_v[:, 2].min():.1f} mm")
    st_bust = mt.mesh_stats(bust_v, bust_f)
    print(f"  kuerzeste Kante {st_bust['edge_min_mm']:.2e} mm, "
          f"{st_bust['degenerate_triangles']} Dreiecke unter der "
          f"Nachweisschwelle fuer Flaeche")
    sys.stdout.flush()

    # ---------------------------------------------------- 4) Prüfungen ----
    banner("4)  Druckpruefungen")
    print("  kleinste lokale Dicke -- ein Strahl von der Oberflaeche nach")
    print("  innen, gemessen bis er wieder austritt. Unter zwei Gitterkanten")
    print("  ist im Feld nichts mehr enthalten, die Zahl ist also eine")
    print("  untere Grenze dessen, was das Gitter noch aufloest.")
    th_head = pc.local_thickness(head_v, head_f, chi, lo, h, level,
                                 n_samples=N_SAMPLES)
    th_bust = pc.local_thickness(bust_v, bust_f, chi2, lo_e, h, level,
                                 n_samples=N_SAMPLES)
    for name, th in (("Kopf", th_head), ("Büste", th_bust)):
        print(f"    {name:5s}: min {th['min_mm']:6.2f} mm | "
              f"p01 {th['p01_mm']:6.2f} | p05 {th['p05_mm']:6.2f} | "
              f"median {th['median_mm']:7.1f} mm  "
              f"({th['samples']:,} Proben)")
        print(f"           duennste Stelle {np.round(th['at_mm'], 1)}, "
              f"kleinste Dicke ohne Nadeldreiecke "
              f"{th['min_solid_mm']:.2f} mm "
              f"({th['artefacts']} Artefakt-Proben)")
    oh_head = pc.overhang_report(head_v, head_f, limit_deg=OVERHANG_DEG)
    oh_bust = pc.overhang_report(bust_v, bust_f, limit_deg=OVERHANG_DEG)
    print(f"  Ueberhaenge steiler als {OVERHANG_DEG:.0f}° (brauchen Stuetze):")
    print(f"    Kopf : {oh_head['area_overhang_cm2']:6.1f} cm² von "
          f"{oh_head['area_total_cm2']:6.1f} cm² "
          f"({100 * oh_head['fraction']:4.1f} %)")
    print(f"    Büste: {oh_bust['area_overhang_cm2']:6.1f} cm² von "
          f"{oh_bust['area_total_cm2']:6.1f} cm² "
          f"({100 * oh_bust['fraction']:4.1f} %)")
    st_head = pc.stand_report(head_v, head_f)
    st_bust2 = pc.stand_report(bust_v, bust_f)
    print("  Standflaeche und Kippsicherheit:")
    print(f"    Kopf : {st_head['contact_cm2']:.2f} cm² -- "
          f"{'steht' if st_head['stands'] else 'steht NICHT, kein flacher Boden'}")
    print(f"    Büste: {st_bust2['contact_cm2']:.2f} cm², Schwerpunkt "
          f"{st_bust2['com_offset_mm']:.1f} mm neben der Mitte, "
          f"Rand {st_bust2['tilt_margin_mm']:.1f} mm entfernt -- "
          f"{'steht' if st_bust2['stands'] else 'KIPPT'}")
    print(f"    Ebenheit der Standflaeche: "
          f"{st_bust2.get('flatness_mm', float('nan')):.2f} mm -- woebelt "
          f"sie sich, steht sie auf drei Punkten")
    sys.stdout.flush()

    # ------------------------------------------------- 5) Export/Lesen ----
    banner("5)  Export und Gegenprobe")
    stl_path = os.path.join(MESHES, "facescan_print.stl")
    em.write_stl(stl_path, bust_v, bust_f)
    back = em.read_stl(stl_path)
    print(f"  STL {os.path.getsize(stl_path) / 1e6:.1f} MB, eigener Leser: "
          f"{back['faces'].shape[0]:,} Dreiecke")
    trimesh_watertight = None
    trimesh_volume = None
    try:
        import trimesh
        tm = trimesh.load(stl_path)
        if hasattr(tm, "geometry"):
            tm = list(tm.geometry.values())[0]
        trimesh_watertight = bool(tm.is_watertight)
        trimesh_volume = float(tm.volume) / 1000.0
        print(f"  trimesh: {len(tm.vertices):,} Punkte / {len(tm.faces):,} "
              f"Dreiecke, is_watertight = {trimesh_watertight}, "
              f"euler_number = {tm.euler_number}, "
              f"Volumen = {trimesh_volume:.1f} cm³")
    except Exception as exc:                            # noqa: BLE001
        print(f"  trimesh nicht geprueft: {exc}")

    with open(os.path.join(RESULTS, "m2b_print_report.json"), "w",
              encoding="utf-8") as fh:
        json.dump({
            "cut": {"rule": "niedrigste Hoehe mit >= %.0f %% des groessten "
                            "Querschnitts" % (100 * CUT_FRAC),
                    "cut_frac": CUT_FRAC, "z_cut_mm": z_cut,
                    "area_at_cut_cm2": float(area[k_cut]),
                    "head_radius_at_cut_mm": r_head,
                    "z_range_mm": [float(z[first]), float(z[last])],
                    "max_area_cm2": float(area.max())},
            "plinth": {"axis_xy_mm": [float(axis_xy[0]), float(axis_xy[1])],
                       "height_mm": PLINTH_MM, "r_top_mm": r_top,
                       "r_bottom_mm": r_bottom, "z_base_mm": z_base,
                       "nodes_changed": changed},
            "bust": {"vertices": int(len(bust_v)), "faces": int(len(bust_f)),
                     "volume_cm3": vol / 1000.0,
                     "height_mm": float(bust_v[:, 2].max()
                                        - bust_v[:, 2].min()),
                     "watertight": rep["watertight"],
                     "boundary_edges": int(rep["boundary_edges"]),
                     "non_manifold_edges": int(rep["non_manifold_edges"]),
                     "components": int(rep["components"]),
                     "euler": int(rep["euler"]),
                     "trimesh_watertight": trimesh_watertight,
                     "trimesh_volume_cm3": trimesh_volume},
            "thickness": {"head": th_head, "bust": th_bust},
            "overhang": {"head": oh_head, "bust": oh_bust,
                         "limit_deg": OVERHANG_DEG},
            "standing": {"head": st_head, "bust": st_bust2},
        }, fh, indent=2)
    # ------------------------------------------------------ 6) Vorschau ----
    banner("6)  Vorschau")
    try:
        import preview_watertight as pv
        centre = np.asarray(bust_v, dtype=np.float64).mean(axis=0)
        radius = float(np.linalg.norm(np.asarray(bust_v, dtype=np.float64)
                                      - centre, axis=1).max())
        panels = []
        for name, yaw, pitch in (("Kopf von vorn", 0.0, 0.0),
                                 ("Kopf seitlich", 62.0, 8.0),
                                 ("Büste von vorn", 0.0, 0.0),
                                 ("Büste seitlich", 62.0, 8.0)):
            src = head_v if name.startswith("Kopf") else bust_v
            srf = head_f if name.startswith("Kopf") else bust_f
            img = pv.render(*pv.view(src, srf, yaw, pitch), center=centre,
                            radius=radius)
            print(f"  {name:>16}: {100 * pv.coverage(img):5.1f} % der "
                  f"Bildflaeche")
            panels.append(img)
        pv.panels_to_png(panels, 2,
                         os.path.join(RESULTS, "print_preview.png"))
    except Exception as exc:                            # noqa: BLE001
        print(f"  keine Vorschau: {exc}")

    print(f"\nFertig in {time.time() - t_start:.0f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
