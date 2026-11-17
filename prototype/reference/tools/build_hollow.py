#!/usr/bin/env python3
"""Stufe 6.2, vierter Teil: der Hohlkörper (docs/05, 12.2).

Die Büste aus `build_print.py` ist massiv: 1171 cm³ Kunststoff, von
denen niemand etwas hat. Dieser Schritt macht daraus eine Schale mit
einer Wand von rund 2 mm und einem Ablaufloch im Sockel -- und mißt
danach nach, was dabei herausgekommen ist.

Vier Entscheidungen, die hier anders sind als in den meisten Anleitungen:

1. **Gefaltet wird das Feld, nicht das Netz.** Die Schale ist eine
   Isofläche eines geänderten Indikatorfeldes (`printcheck.shell_field`),
   kein eingeschobenes Netz. Ein Netz um 2 mm nach innen zu schieben,
   überlappt sich an Haaren und Ohren selbst, weil der Versatz dort
   größer ist als die örtliche Dicke. Eine Isofläche kann sich nie selbst
   schneiden -- wo kein Platz ist, schnürt der Hohlraum ab und die Stelle
   bleibt massiv.
2. **Der Sockel bleibt massiv.** Er ist der Teil, auf dem das Gewicht
   steht; hohl würde die Büste oben schwerer und kippeliger. Das Aushöhlen
   gilt deshalb nur oberhalb der Schnitthöhe.
3. **Ohne Ablaufloch ist ein Hohlkörper ein Gefäß.** Beim Harzdruck
   bleibt das flüssige Harz darin und das Teil reißt später auf; beim
   Pulverdruck bekommt niemand das Pulver heraus. Das Loch geht durch den
   massiven Sockel nach unten -- durch die Standfläche, wo es nachher
   niemand sieht. Daß der Hohlraum WIRKLICH mit der Außenwelt verbunden
   ist, wird hier nachgemessen (ein Strahl vom Boden durch das Loch bis
   in den Hohlraum, alle Proben außen), nicht angenommen.
4. **Die Wandstärke wird kalibriert, nicht gesetzt.** Der Abstand zur
   Oberfläche kommt vom Gitter (`band_distance`, gut ±0,3 mm), und was
   daraus wird, mißt `local_thickness` nach: ein Strahl von der Außenhaut
   nach innen, bis er in den Hohlraum austritt. Gesucht wird die dünnste
   Wand, deren 1-Prozent-Quantil noch über der Grenze aus docs/05 (4.3)
   liegt. Am Ende steht eine Messung, keine Behauptung.

Der erste Versuch ist übrigens daran gescheitert, das Feld direkt zu
falten (`phi = |u + d/2| - d/2`, eine Isofläche im Abstand `d/|grad u|`):
das Poisson-Feld ist bis auf eine Übergangsbreite von knapp 1,5 mm
gesättigt, `|grad u|` fällt dort praktisch auf null -- bei 2 mm Tiefe
liefert diese Schätzung 14 mm. Eine Schale von 2 mm läßt sich als
Niveaufläche dieses Feldes also gar nicht ausdrücken.

Aufruf:
    /tmp/qrenv/bin/python prototype/reference/tools/build_hollow.py
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
from facescan_ref import meshopt as mo                              # noqa: E402
from facescan_ref import metrics as mt                              # noqa: E402
from facescan_ref import printcheck as pc                           # noqa: E402
from facescan_ref import repair                                     # noqa: E402

MESHES = os.path.abspath(os.path.join(HERE, "..", "meshes"))
RESULTS = os.path.abspath(os.path.join(HERE, "..", "results"))

TIE_EPS = 1e-5
WALL_MM = 2.0             # angestrebte Wandstärke
WALL_MIN_MM = 1.2         # docs/05 (4.3): darunter wird gewarnt
WALL_SCAN = (1.6, 2.0, 2.4, 2.8, 3.2)
DRAIN_R_MM = 5.0          # Ablaufloch: 10 mm Durchmesser, Harz läuft aus
DRAIN_OVER_MM = 3.0       # wie weit das Loch in den Hohlraum hineinragt
N_SAMPLES = 20_000
N_CALIB = 6_000           # Stichproben je Kalibrierungsschritt


def banner(text: str) -> None:
    print("\n" + "=" * 74)
    print(text)
    print("=" * 74)
    sys.stdout.flush()


def build(field, lo, h, level, wall_mm, z_cut, z_base, axis_xy):
    """Baut das Feld des Hohlkörpers: Schale oberhalb der Schnitthöhe,
    massiver Sockel darunter, Ablaufloch durch den Sockel.
    """
    shell = pc.shell_field(field, lo, h, level, wall_mm, z_from=z_cut)
    return pc.drill_hole(shell, lo, h, level, axis_xy, DRAIN_R_MM,
                         z_base - 2.0 * h, z_cut + DRAIN_OVER_MM)


def measure_wall(v, f, field, lo, h, level, z_cut, n_samples):
    """Wandstärke auf dem KOPF (nicht auf dem massiven Sockel, dessen
    Proben jeden Median verschleppen würden) mit einer Nadelschwelle von
    einer halben Gitterkante -- bei einem Hohlkörper ist die Wand selbst
    dünn, die Voreinstellung von vier Kanten würde sie wegwerfen.
    """
    return pc.local_thickness(v, f, field, lo, h, level,
                              n_samples=n_samples, z_from=z_cut + 1.0,
                              artefact_mm=0.5 * h, limit_mm=WALL_MIN_MM)


def cross_section_png(path, solid_field, hollow_field, lo, h, level,
                      axis_xy, z_base, z_top, half_width, width=760):
    """Senkrechter Schnitt durch die Achse: dunkel ist gebliebenes
    Material, hellgrau das herausgeholte. Der Schnitt zeigt auf einen
    Blick, was die Schale ist -- und daß das Ablaufloch wirklich durch
    den Sockel geht.
    """
    z0, z1 = float(z_base) - 2.0 * h, float(z_top) + 2.0 * h
    x0, x1 = float(axis_xy[0]) - half_width, float(axis_xy[0]) + half_width
    w = int(width)
    hh = int(round(w * (z1 - z0) / (x1 - x0)))
    xs = np.linspace(x0, x1, w)
    zs = np.linspace(z1, z0, hh)                 # oben beginnen
    gx, gz = np.meshgrid(xs, zs)
    pts = np.column_stack([gx.ravel(),
                           np.full(gx.size, float(axis_xy[1])),
                           gz.ravel()])
    inside_s = pc.sample_field(solid_field, lo, h, pts) < level
    inside_h = pc.sample_field(hollow_field, lo, h, pts) < level
    rgb = np.full((hh, w, 3), 255, dtype=np.uint8)
    rgb[inside_s.reshape(hh, w)] = (206, 210, 214)      # herausgeholt
    rgb[inside_h.reshape(hh, w)] = (58, 74, 92)         # geblieben
    mo.write_png(path, rgb)
    return w, hh


def drain_connected(field, lo, h, level, axis_xy, z_from, z_to, n=200):
    """Ist der Hohlraum wirklich mit der Außenwelt verbunden?

    Ein Strahl auf der Achse des Ablauflochs, vom Boden bis in den
    Hohlraum: jede Probe muß AUSSEN liegen. Wäre der Hohlraum eine
    geschlossene Blase, läge irgendwo auf diesem Weg Material, und der
    Marcher hätte zwei Schalen erzeugt statt einer.
    """
    t = np.linspace(0.0, 1.0, int(n))
    pts = np.column_stack([np.full(n, float(axis_xy[0])),
                           np.full(n, float(axis_xy[1])),
                           float(z_from) + t * (float(z_to) - float(z_from))])
    val = pc.sample_field(field, lo, h, pts) - float(level)
    return bool((val >= 0.0).all()), int((val < 0.0).sum()), float(val.min())


def main() -> int:
    t_start = time.time()
    path = os.path.join(MESHES, "print_field.npz")
    if not os.path.exists(path):
        print("Kein Feld unter %s -- bitte zuerst build_print.py laufen "
              "lassen (es hebt das Feld dort auf)." % path)
        return 2
    st = np.load(path)
    field, lo, h, level = (st["field"], st["lo"], float(st["h"]),
                           float(st["level"]))
    z_cut, z_base, axis_xy = float(st["z_cut"]), float(st["z_base"]), st["axis_xy"]
    bust_v, bust_f = st["v"], st["f"]

    banner("HOHLKOERPER  Schale, Ablaufloch, Wandstaerke (docs/05 12.2)")
    print(f"  Feld {field.shape}, Gitterkante {h:.2f} mm")
    print(f"  Schnitthoehe z = {z_cut:.1f} mm, Standflaeche z = {z_base:.1f} mm")
    print(f"  massive Buesste: {len(bust_v):,} Punkte / {len(bust_f):,} Dreiecke")
    print(f"  Ziel: Wand {WALL_MM:.1f} mm, mindestens {WALL_MIN_MM:.1f} mm "
          f"(docs/05 4.3), Ablaufloch r = {DRAIN_R_MM:.0f} mm")
    sys.stdout.flush()

    # ------------------------------------------------- 1) Kalibrierung ----
    banner("1)  Wandstaerke kalibrieren (Abstand vom Gitter, Messung per Strahl)")
    print("  gesucht ist die duennste Wand, deren 1-%-Quantil noch ueber der")
    print("  Grenze liegt -- duenner heisst mehr gespartes Material,")
    print("  aber die Grenze aus docs/05 gilt ohne Ausnahme.")
    scan = []
    chosen = None
    for wall in WALL_SCAN:
        cand = build(field, lo, h, level, wall, z_cut, z_base, axis_xy)
        th = measure_wall(bust_v, bust_f, cand, lo, h, level, z_cut, N_CALIB)
        row = {"wall_mm": float(wall), "median_mm": th["median_mm"],
               "p01_mm": th["p01_mm"], "p05_mm": th["p05_mm"],
               "min_mm": th["min_mm"], "samples": th["samples"]}
        scan.append(row)
        note = ""
        if row["p01_mm"] is not None and row["p01_mm"] >= WALL_MIN_MM:
            if chosen is None:
                chosen = (wall, th)
                note = "  <- genommen"
        print(f"    Soll {wall:4.1f} mm -> median {row['median_mm']:5.2f} | "
              f"p01 {row['p01_mm']:5.2f} | p05 {row['p05_mm']:5.2f} | "
              f"min {row['min_mm']:5.2f} mm{note}")
        sys.stdout.flush()
    if chosen is None:
        chosen = (WALL_SCAN[-1], scan[-1])
        print("  ACHTUNG: kein Kandidat erreicht das 1-%-Quantil -- "
              "die staerkste Wand wird genommen und gewarnt")
    wall_mm = float(chosen[0])
    ok_limit = bool(chosen[1]["p01_mm"] >= WALL_MIN_MM)
    print(f"  -> Wand {wall_mm:.1f} mm "
          f"({'ueber' if ok_limit else 'UNTER'} der Grenze: p01 "
          f"{chosen[1]['p01_mm']:.2f} mm)")
    sys.stdout.flush()

    # ------------------------------------------------------ 2) Marchieren --
    banner("2)  Neu marchieren und aufraeumen")
    hollow_field = build(field, lo, h, level, wall_mm, z_cut, z_base, axis_xy)
    t0 = time.time()
    raw_v, raw_f, ties = repair.march_indicator(hollow_field, lo, h, level,
                                                tie_eps=TIE_EPS)
    print(f"  {len(raw_v):,} Punkte / {len(raw_f):,} Dreiecke in "
          f"{time.time() - t0:.1f} s ({ties} Krawatten gebrochen)")
    hv, hf, info = repair.clean_mesh(raw_v, raw_f)
    print(f"  ohne Nulldreiecke: {info['triangles']:,} Dreiecke, "
          f"{info['boundary_edges_after_drop']} Randkanten, "
          f"{info['loops_filled']} nachgestopft")
    print(f"  {info['islands']} Inseln -- Aussenwand, Hohlraum und Loch "
          f"muessen EINE sein, sonst faellt der Hohlraum weg "
          f"({info['islands_other_triangles']} Dreiecke in den anderen)")
    rep = repair.watertight_report(hf)
    print(f"  Randkanten: {rep['boundary_edges']} | nicht-manigfaltig: "
          f"{rep['non_manifold_edges']} | Komponenten: {rep['components']} | "
          f"Euler: {rep['euler']}")
    print(f"  WASSERDICHT: {rep['watertight']}")

    conn, n_in, vmin = drain_connected(hollow_field, lo, h, level, axis_xy,
                                       z_base - 1.0, z_cut + 20.0)
    print(f"  Ablauf: Strahl vom Boden (z = {z_base - 1.0:.1f}) bis in den "
          f"Hohlraum (z = {z_cut + 20.0:.1f}) -- "
          f"{'durchgaengig aussen, Hohlraum ist verbunden' if conn else str(n_in) + ' Proben IN MATERIAL, Hohlraum ist eine Blase'}")
    sys.stdout.flush()

    def volume(v, f):
        p = v[f]
        return abs(float(np.einsum("ij,ij->i", p[:, 0],
                                   np.cross(p[:, 1] - p[:, 0],
                                            p[:, 2] - p[:, 0])).sum() / 6.0))

    vol_solid, vol_hollow = volume(bust_v, bust_f), volume(hv, hf)
    print(f"  Volumen massiv {vol_solid / 1000.0:.1f} cm³ -> hohl "
          f"{vol_hollow / 1000.0:.1f} cm³ "
          f"({100 * (1 - vol_hollow / max(vol_solid, 1e-9)):.0f} % gespart)")
    sys.stdout.flush()

    # ------------------------------------------------------ 3) Prüfung ----
    banner("3)  Wandstaerke messen (Ray-Cast, docs/05 4.3)")
    th = measure_wall(bust_v, bust_f, hollow_field, lo, h, level, z_cut,
                      N_SAMPLES)
    thin = pc.local_thickness(bust_v, bust_f, hollow_field, lo, h, level,
                              n_samples=N_SAMPLES, z_from=z_cut + 1.0,
                              artefact_mm=0.5 * h, step_mm=0.25 * h)
    print(f"  Proben auf dem Kopf: {th['samples']:,}")
    print(f"  Wand: median {th['median_mm']:.2f} mm | p05 {th['p05_mm']:.2f} | "
          f"p01 {th['p01_mm']:.2f} | min {th['min_mm']:.2f} mm")
    print(f"  unter {WALL_MIN_MM:.1f} mm: {th['below_limit_n']} von "
          f"{th['samples']:,} Proben = {100 * th['below_limit_frac']:.2f} % "
          f"der Kopfoberflaeche")
    print(f"  kleinste Wand bei {np.round(th['at_mm'], 1)}")
    print(f"  zum Vergleich, mit feinerem Strahlschritt (0,25 Gitterkanten): "
          f"min {thin['min_mm']:.2f} mm, p01 {thin['p01_mm']:.2f} mm --")
    print("  das Minimum wandert mit dem Schritt und handelt deshalb von")
    print("  einer Haarspitze, nicht von der Wand; der Anteil unten tut das nicht.")
    warn = not ok_limit or not conn
    verdict = ("eingehalten (p01 %.2f mm)" % th["p01_mm"] if not warn
               else "WARNUNG: unterschritten")
    print(f"  Grenze aus docs/05 (4.3): {WALL_MIN_MM:.1f} mm -> {verdict}")
    st_h = mt.mesh_stats(hv, hf)
    print(f"  Netz: kuerzeste Kante {st_h['edge_min_mm']:.2e} mm, "
          f"{st_h['degenerate_triangles']} Dreiecke unter der Nachweisschwelle")
    sys.stdout.flush()

    # ------------------------------------------------- 4) Export/Lesen ----
    banner("4)  Export und Gegenprobe")
    stl_path = os.path.join(MESHES, "facescan_print_hollow.stl")
    em.write_stl(stl_path, hv, hf)
    back = em.read_stl(stl_path)
    print(f"  STL {os.path.getsize(stl_path) / 1e6:.1f} MB, eigener Leser: "
          f"{back['faces'].shape[0]:,} Dreiecke")
    tm_wt, tm_vol = None, None
    try:
        import trimesh
        tm = trimesh.load(stl_path)
        if hasattr(tm, "geometry"):
            tm = list(tm.geometry.values())[0]
        tm_wt = bool(tm.is_watertight)
        tm_vol = float(tm.volume) / 1000.0
        print(f"  trimesh: {len(tm.vertices):,} Punkte / {len(tm.faces):,} "
              f"Dreiecke, is_watertight = {tm_wt}, "
              f"euler_number = {tm.euler_number}, Volumen = {tm_vol:.1f} cm³")
    except Exception as exc:                            # noqa: BLE001
        print(f"  trimesh nicht geprueft: {exc}")

    png = os.path.join(RESULTS, "hollow_preview.png")
    pw, ph = cross_section_png(png, field, hollow_field, lo, h, level,
                               axis_xy, z_base, bust_v[:, 2].max(),
                               float(max(st["r_top"], st["r_bottom"])) + 6.0)
    print(f"  Schnitt durch die Achse: {pw}x{ph} px -> "
          f"{os.path.basename(png)} (dunkel = Material, "
          f"hellgrau = herausgeholt, das Loch im Sockel ist der helle Kanal)")

    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, "m2b_hollow_report.json"), "w",
              encoding="utf-8") as fh:
        json.dump({
            "wall_requested_mm": wall_mm,
            "wall_scan": [row for row in scan],
            "target_wall_mm": WALL_MM,
            "wall_min_limit_mm": WALL_MIN_MM,
            "drain": {"radius_mm": DRAIN_R_MM, "z_from_mm": z_base - 2.0 * h,
                      "z_to_mm": z_cut + DRAIN_OVER_MM,
                      "connected": conn, "samples_in_material": n_in},
            "solid": {"vertices": int(len(bust_v)), "faces": int(len(bust_f)),
                      "volume_cm3": vol_solid / 1000.0},
            "hollow": {"vertices": int(len(hv)), "faces": int(len(hf)),
                       "volume_cm3": vol_hollow / 1000.0,
                       "saved_pct": float(100 * (1 - vol_hollow
                                                 / max(vol_solid, 1e-9)))},
            "watertight": rep,
            "wall": {k: v for k, v in th.items() if k != "at_mm"},
            "wall_fine_step": {k: v for k, v in thin.items() if k != "at_mm"},
            "wall_at_mm": th["at_mm"],
            "warning": bool(warn),
            "trimesh": {"watertight": tm_wt, "volume_cm3": tm_vol},
            "stl_kb": os.path.getsize(stl_path) / 1024.0,
            "runtime_s": float(time.time() - t_start),
        }, fh, indent=2, default=float)
    print(f"\nFertig in {time.time() - t_start:.0f} s")
    return 0 if not warn else 1


if __name__ == "__main__":
    raise SystemExit(main())
