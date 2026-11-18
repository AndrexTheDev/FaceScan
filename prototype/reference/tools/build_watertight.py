#!/usr/bin/env python3
"""Stufe 6.2, zweiter Teil: Loch-Füllung, Taubin-Glättung, Poisson-Variante.

Hier entsteht die Fassung des Netzes, die man einem 3D-Drucker geben
kann: **geschlossen**, also mit klarem Innen und Aussen. Das Mesh aus
Marching Tetrahedra ist das nicht -- überall dort, wo keine Kamera
hinsah, endet die Fläche einfach.

Drei Schritte, genau in der Reihenfolge von docs/03 (6.2):

  1. Löcher bis 3 mm Rand mit der Advancing Front schließen. Was
     größer ist, bleibt offen -- sonst erfinden wir Oberfläche.
  2. Taubin-Glättung (3 Iterationen, nur Haut) gegen das Treppenmuster
     des Voxelgitters.
  3. Poisson-Variante für alles, was danach noch offen ist: aus den
     gerichteten Punkten wird ein Vektorfeld, seine Divergenz ist die
     rechte Seite einer Poisson-Gleichung, und die Isofläche der Lösung
     ist per Konstruktion geschlossen.

Aufruf:
    /tmp/qrenv/bin/python prototype/reference/tools/build_watertight.py
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(HERE, "..", "python")
sys.path.insert(0, os.path.abspath(PY))

from facescan_ref import headmesh as hm            # noqa: E402
from facescan_ref import metrics as mt             # noqa: E402
from facescan_ref import meshopt as mo             # noqa: E402
from facescan_ref import repair                    # noqa: E402
from facescan_ref import export_more as em         # noqa: E402
from facescan_ref.fusion import TsdfVolume, marching_tetrahedra  # noqa: E402
from facescan_ref.raster import Renderer, lambert  # noqa: E402
from facescan_ref.refine import refine_by_depth    # noqa: E402

MESHES = os.path.abspath(os.path.join(HERE, "..", "meshes"))
RESULTS = os.path.abspath(os.path.join(HERE, "..", "results"))

W, H = 540, 960
FX = FY = 916.6
CX, CY = W / 2.0, H / 2.0
N_FRAMES = 16
SEED = 2026
VOXEL_MM = 1.5
TRUNC_MM = 6.0
BBOX = ([-155.0, -170.0, -155.0], [155.0, 170.0, 155.0])
POISSON_RES = 192
MAX_HOLE_MM = 3.0
# Krawatten-Schwelle für das Iso-Level, relativ zur Feldamplitude. Siehe
# repair.poisson_grid: ohne sie fallen Isoflaeche und Gitterknoten exakt
# aufeinander, und das Netz kommt mit gedrehten Dreiecken heraus.
TIE_EPS = 1e-5


def banner(text: str) -> None:
    print("\n" + "=" * 74)
    print(text)
    print("=" * 74)
    sys.stdout.flush()


def render_all(poses, head, hair_mesh, light):
    v, f, uv, c = head
    hv, hf, huv, hc = hair_mesh
    sh_v = lambert(v, f, light)
    sh_h = lambert(hv, hf, light)
    frames = []
    for r, t in poses:
        ren = Renderer(W, H, FX, FY, CX, CY)
        ren.draw(v, f, c, r, t, label=1, shading=sh_v)
        ren.draw(hv, hf, hc, r, t, label=2, shading=sh_h)
        o = ren.finish()
        frames.append({"R": r, "t": t, "depth": o["depth"],
                       "color": np.asarray(o["color"]), "label": o["label"],
                       "mask": o["mask"], "skin": o["label"] == 1,
                       "hair": o["label"] == 2, "object": o["label"] > 0})
    return frames


def main() -> int:
    t_start = time.time()
    np.random.seed(SEED)
    os.makedirs(MESHES, exist_ok=True)
    os.makedirs(RESULTS, exist_ok=True)

    banner("WASSERDICHT  Loch-Fuellung, Taubin-Glaettung, Poisson-Variante")

    # Zwischenstaende liegen als NPZ in meshes/. Wer nur Stufe 3 anders
    # haben will, spart sich damit die 16 Renderings und die TSDF-Fusion
    # (zusammen gut drei Minuten) und rechnet in Sekunden weiter.
    # --fresh wirft die Dateien weg und rechnet alles neu.
    FRESH = "--fresh" in sys.argv
    CACHE_SKIN = os.path.join(MESHES, "watertight_skin.npz")
    CACHE_POIS = os.path.join(MESHES, "watertight_poisson.npz")

    head = hm.head_mesh(96, 144)
    hair_mesh = hm.hair_mesh(96, 144)
    poses = hm.orbit_poses(N_FRAMES, radius=520.0, yaw_deg=75.0, pitch_deg=9.0)
    frames = render_all(poses, head, hair_mesh, np.array([0.25, 0.55, 1.0]))
    print(f"  {len(frames)} Bilder gerendert ({time.time() - t_start:.0f} s)")

    # ------------------------------------------------------- Hautnetz ----
    if os.path.exists(CACHE_SKIN) and not FRESH:
        z = np.load(CACHE_SKIN)
        sv, sf = z["v"], z["f"]
        print(f"  Hautnetz aus dem Cache: {len(sv):,} Punkte / "
              f"{len(sf):,} Dreiecke -- Stufen 1 und 2 sind damit")
        print("  bereits enthalten, es wird nichts gegaettet oder gefuellt.")
        sv2, sf2, sv3 = sv, sf, sv
        info = {"loops": 0, "filled": 0, "triangles": 0, "too_big": 0,
                "open_perimeter_mm": 0.0}
        st_before = st_after = mt.mesh_stats(sv, sf)
        dev_sm = {"to_lod_mm": 0.0, "max_mm": 0.0}
        moved = np.zeros(len(sv))
        print("")
    else:
        vol = TsdfVolume(BBOX[0], BBOX[1], VOXEL_MM, TRUNC_MM)
        for fr in frames:
            w = TsdfVolume.incidence_weights(fr["depth"], fr["skin"], FX, FY, CX, CY)
            vol.integrate(fr["depth"], fr["skin"], fr["R"], fr["t"], FX, FY, CX, CY,
                          weights=w)
        sv_raw, sf_raw = marching_tetrahedra(vol, min_weight=0.05)
        del vol
        n_raw = mt.vertex_normals(sv_raw, sf_raw)
        seen = mt.observed_points(sv_raw, frames, FX, FY, CX, CY, label=1,
                                  min_views=2, normals=n_raw, min_cos=0.35)
        sv, sf = mt.drop_unobserved_triangles(sv_raw, sf_raw, seen, min_seen=3)
        sv = refine_by_depth(sv, sf, frames, FX, FY, CX, CY, label=1,
                             iters=5, depth_tol_mm=2.0, max_move_mm=1.5)
        sv, sf = mo.orient_mesh(sv, sf)
        print(f"  Hautnetz: {len(sv):,} Punkte / {len(sf):,} Dreiecke")
        rep0 = repair.watertight_report(sf)
        print(f"  offen: {rep0['boundary_edges']:,} Randkanten, "
              f"{rep0['components']} Komponenten, "
              f"wasserdicht: {rep0['watertight']}")
        sys.stdout.flush()

        # ------------------------------------------- 1) Löcher schließen ----
        banner("1)  Loch-Fuellung (Advancing Front, Rand < %.0f mm)" % MAX_HOLE_MM)
        loops = repair.boundary_loops(sv, sf)
        pers = sorted(repair.loop_perimeter(sv, l) for l in loops)
        print(f"  {len(loops)} Rand-Schleifen gefunden")
        if pers:
            print(f"  Umfang: kleinste {pers[0]:.2f} mm, groesste {pers[-1]:.1f} mm, "
                  f"Summe {sum(pers):.1f} mm")
        sv2, sf2, _, info = repair.fill_holes(sv, sf, max_perimeter_mm=MAX_HOLE_MM)
        print(f"  geschlossen: {info['filled']}, zu gross: {info['too_big']}, "
              f"neue Dreiecke: {info['triangles']}")
        print(f"  offen geblieben: {info['open_perimeter_mm']:.1f} mm Rand")
        rep1 = repair.watertight_report(sf2)
        print(f"  danach: {rep1['boundary_edges']:,} Randkanten")
        sys.stdout.flush()

        # --------------------------------------------- 2) Taubin-Glättung ---
        banner("2)  Taubin-Glaettung (3 Iterationen, nur Haut)")
        st_before = mt.mesh_stats(sv2, sf2)
        # Ränder festhalten: was am Rand des beobachteten Bereichs liegt, ist
        # echte Kante (Übergang zu den Haaren) und kein Treppenmuster.
        on_edge = np.zeros(len(sv2), dtype=bool)
        for l in repair.boundary_loops(sv2, sf2):
            on_edge[l] = True
        sv3 = repair.taubin_smooth(sv2, sf2, iterations=3, fixed=on_edge)
        st_after = mt.mesh_stats(sv3, sf2)
        # Wie viel Geometrie hat die Glaettung WIRKLICH veraendert? Die
        # Flaeche sinkt um 18 %, aber das ist zum grossten Teil das
        # Treppenmuster, das aus der Messung verschwindet -- nicht Schrumpf.
        dev_sm = mt.surface_deviation(sv2, sf2, sv3, sf2, cell=3.0,
                                      max_ref_points=40_000)
        moved = np.linalg.norm(sv3 - sv2, axis=1)
        print(f"  Verschiebung: {moved.mean():.3f} mm im Mittel "
              f"(max {moved.max():.3f} mm)")
        print(f"  Flaeche {st_before['surface_cm2']:.1f} -> "
              f"{st_after['surface_cm2']:.1f} cm² "
              f"({100 * (st_after['surface_cm2'] / st_before['surface_cm2'] - 1):+.2f} %)")
        print(f"  kuerzeste Kante {st_before['edge_min_mm']:.3f} -> "
              f"{st_after['edge_min_mm']:.3f} mm, "
              f"entartete Dreiecke {st_before['degenerate_triangles']} -> "
              f"{st_after['degenerate_triangles']}")
        print(f"  Abstand geglaettetes Netz -> Original: "
              f"{dev_sm['to_lod_mm']:.3f} mm im Mittel "
              f"(max {dev_sm['max_mm']:.2f}) -- das ist die Zahl, die sagt,")
        print("  ob Glaettung Form zerstoert. Der Flaechenrueckgang allein tut")
        print("  das nicht: eine Treppe hat mehr Flaeche als die Rampe, die sie")
        print("  annahert, und genau den Unterschied haben wir hier entfernt.")
        sys.stdout.flush()

    if not FRESH:
        np.savez_compressed(CACHE_SKIN, v=sv3, f=sf2)

    # -------------------------------------------------- 3) Poisson ------
    banner("3)  Poisson-Variante (regelmaessiges Gitter, %d³)" % POISSON_RES)
    if os.path.exists(CACHE_POIS) and not FRESH:
        z = np.load(CACHE_POIS)
        po = {"vertices": z["v"], "faces": z["f"], "res": POISSON_RES,
              "voxel_mm": float(z["voxel"]), "level": float(z["level"]),
              "ties": int(z["ties"]), "secs": None}
        print(f"  aus dem Cache {os.path.basename(CACHE_POIS)} "
              f"({len(po['vertices']):,} Punkte / {len(po['faces']):,} "
              f"Dreiecke)")
    else:
        pts = sv3
        nrm = mt.vertex_normals(sv3, sf2)
        t0 = time.time()
        po = repair.poisson_grid(pts, nrm, pts.min(axis=0), pts.max(axis=0),
                                 res=POISSON_RES, tie_eps=TIE_EPS)
        po["secs"] = time.time() - t0
        np.savez_compressed(CACHE_POIS, v=po["vertices"], f=po["faces"],
                            voxel=po["voxel_mm"], level=po["level"],
                            ties=po["ties"])
    pts = sv3
    pv, pf = po["vertices"], po["faces"]
    if po["secs"] is None:
        print(f"  {len(pv):,} Punkte / {len(pf):,} Dreiecke, "
              f"Gitterkante {po['voxel_mm']:.2f} mm, "
              f"Iso-Level {po['level']:.4f}")
    else:
        print(f"  gerechnet in {po['secs']:.1f} s: {len(pv):,} Punkte / "
              f"{len(pf):,} Dreiecke, Gitterkante {po['voxel_mm']:.2f} mm, "
              f"Iso-Level {po['level']:.4f}")
    # Erst die Umlaufrichtung. Marching Tetrahedra liefert sie an den
    # Gitterknoten, auf denen der Iso-Wert exakt sitzt, vereinzelt falsch
    # herum -- und ein gedrehtes Dreieck ist topologisch nichts anderes
    # als eine Kante, die zweimal in derselben Richtung benutzt wird.
    # Genau das hat im ersten Lauf 106 offene Schleifen erzeugt, obwohl
    # die Kanten zaehlten, als waere alles dicht: 528 Kanten mit zwei
    # Nachbarn, die beide dieselbe Richtung zeigten.
    n_wind = mo.winding_errors(pf)
    pv, pf = mo.orient_mesh(pv, pf)
    print(f"  Umlaufrichtung vereinheitlicht: {n_wind:,} Kanten mit "
          f"gleichsinnigen Nachbarn -> {mo.winding_errors(pf)}")

    pv, pf, _, _ = repair.remove_degenerate(pv, pf)
    print(f"  ohne Nulldreiecke: {len(pv):,} Punkte / {len(pf):,} Dreiecke, "
          f"davon {repair.watertight_report(pf)['boundary_edges']} Randkanten "
          f"-- die Luecken stopfen wir gleich wieder zu")

    # Das Herauswerfen der Nulldreiecke reisst kleine Loecher: ein
    # entartetes Dreieck haengt mit drei Kanten an drei Nachbarn, und
    # wenn es weg ist, klafft dort ein dreieckiges Loch. Deshalb muss
    # nach dem Aufraeumen noch einmal gefuellt werden -- diesmal ohne die
    # 3-mm-Grenze, denn diese Loecher sind Gitterkanten gross (0.9 mm).
    pv, pf, _, info2 = repair.fill_holes(pv, pf, max_perimeter_mm=50.0)
    pv, pf = mo.orient_mesh(pv, pf)
    print(f"  nachgestopft: {info2['filled']} Schleifen, "
          f"{info2['triangles']} neue Dreiecke, noch "
          f"{info2['open_perimeter_mm']:.1f} mm Rand")

    lab, _ = mo.connected_components(pv, pf)
    sizes = np.bincount(lab[pf[:, 0]])
    order = np.argsort(sizes)[::-1]
    print(f"  {len(sizes)} Inseln -- groesste {sizes[order[0]]:,}, der Rest "
          f"{int(sizes[order[1:]].sum()):,} Dreiecke in "
          f"{len(sizes) - 1} Stueck (groesste davon "
          f"{int(sizes[order[1]]) if len(sizes) > 1 else 0:,})")
    pv, pf, _, _ = repair.largest_component(pv, pf)
    pv, pf = repair.flip_outward(pv, pf)
    print(f"  groesste Insel, Normalen nach aussen: {len(pv):,} Punkte / "
          f"{len(pf):,} Dreiecke")
    rep2 = repair.watertight_report(pf)
    print(f"  Randkanten: {rep2['boundary_edges']:,} | "
          f"nicht-manigfaltig: {rep2['non_manifold_edges']:,} | "
          f"Komponenten: {rep2['components']} | "
          f"Euler-Charakteristik: {rep2['euler']}")
    print(f"  WASSERDICHT: {rep2['watertight']}")
    st_po = mt.mesh_stats(pv, pf)
    print(f"  Flaeche {st_po['surface_cm2']:.1f} cm² (Hautnetz zum Vergleich: "
          f"{st_after['surface_cm2']:.1f} cm² -- die geschlossene Blase hat "
          f"eine Rueckseite, die es in den Aufnahmen nicht gab)")
    print(f"  kuerzeste Kante {st_po['edge_min_mm']:.2e} mm, "
          f"{st_po['degenerate_triangles']} Dreiecke unter der "
          f"Nachweisschwelle fuer Flaeche")
    if pv.size:
        # Volumen über den Divergenzsatz -- nur bei geschlossener Fläche
        # überhaupt eine aussagekräftige Zahl. Der Betrag wird am ENDE
        # genommen, nicht schon je Dreieck: einzeln absolut genommen
        # addieren sich die Vorzeichenfehler zu viel zu 20 cm³ zusammen
        # (757,5 statt 737,5 cm³ -- genau der Unterschied zu trimesh).
        p = pv[pf]
        vol_mm3 = abs(float((np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
                             * p[:, 0]).sum() / 6.0))
        print(f"  Volumen: {vol_mm3 / 1000.0:.1f} cm³ (positiv, weil die "
              f"Umlaufrichtung oben gedreht wurde; bei negativem Volumen "
              f"fuellt ein Slicer spaeter das Falsche aus)")
    # NUR die Richtung Hautnetz -> Poisson-Flaeche ist eine Aussage.
    # Die Gegenrichtung misst die Rückseite der geschlossenen Blase, und
    # die liegt per Konstruktion dort, wo keine Kamera war -- sie als
    # Fehler zu zählen, hieße die Methode dafür zu bestrafen, dass sie
    # eine fehlende Rückseite geschlossen hat.
    dev = mt.surface_deviation(pts, sf2, pv, pf, cell=3.0,
                               max_ref_points=40_000)
    print(f"  Hautnetz -> Poisson-Flaeche: {dev['to_lod_mm']:.3f} mm "
          f"im Mittel (Richtung Haut <- Poisson: {dev['from_lod_mm']:.3f} mm)")
    print(f"  beide Richtungen zusammen: {dev['mean_mm']:.3f} mm "
          f"(p95 {dev['p95_mm']:.3f}, max {dev['max_mm']:.2f}) -- die Zahl")
    print("  ist absichtlich nicht die Kennzahl, weil sie den geschlossenen")
    print("  Hinterkopf mitmisst, den es in den Aufnahmen nicht gibt.")
    sys.stdout.flush()

    # -------------------------------------------------------- Dateien ---
    banner("Export und Gegenprobe")
    stl_path = os.path.join(MESHES, "facescan_watertight.stl")
    em.write_stl(stl_path, pv, pf)
    back = em.read_stl(stl_path)
    print(f"  STL {os.path.getsize(stl_path) / 1e6:.1f} MB, Ruecklese: "
          f"{back['faces'].shape[0]:,} Dreiecke")
    # Der fremde Leser. Wichtig: trimesh darf die Punkte VERSCHMELZEN
    # (Voreinstellung), sonst zaehlt es die 1,37 Mio. Einzelpunkte des
    # STL-Dreieckssatzes und meldet "nicht wasserdicht", weil jede Kante
    # nur einmal vorkommt. Mit process=False kommt genau das heraus --
    # wer nur die kurze Ausgabe sieht, glaubt dann an ein kaputtes Netz.
    try:
        import trimesh
        tm = trimesh.load(stl_path)
        if hasattr(tm, "geometry"):
            tm = list(tm.geometry.values())[0]
        print(f"  trimesh: {len(tm.vertices):,} Punkte / {len(tm.faces):,} "
              f"Dreiecke, is_watertight = {bool(tm.is_watertight)}, "
              f"euler_number = {tm.euler_number}, "
              f"Volumen = {tm.volume / 1000.0:.1f} cm³")
        raw = trimesh.load(stl_path, process=False)
        if hasattr(raw, "geometry"):
            raw = list(raw.geometry.values())[0]
        print(f"  trimesh ohne Punktverschmelzung: {len(raw.vertices):,} "
              f"Punkte, is_watertight = {bool(raw.is_watertight)} -- das ist "
              f"kein Urteil ueber das Netz,")
        print("  sondern darueber, dass ein STL-Satz seine Punkte je Dreieck "
              "einzeln mitfuehrt.")
    except Exception as exc:                        # noqa: BLE001
        print(f"  trimesh nicht geprueft: {exc}")

    import json
    with open(os.path.join(RESULTS, "m2b_watertight_report.json"), "w",
              encoding="utf-8") as fh:
        json.dump({
            "skin_mesh": {"vertices": int(len(sv)), "faces": int(len(sf))},
            "holes": {k: (float(v) if isinstance(v, float) else int(v))
                      for k, v in info.items()},
            "taubin": {"mean_move_mm": float(moved.mean()),
                       "deviation_mm": dev_sm["to_lod_mm"],
                       "area_before_cm2": st_before["surface_cm2"],
                       "area_after_cm2": st_after["surface_cm2"]},
            "poisson": {"res": po["res"], "voxel_mm": po["voxel_mm"],
                        "level": po["level"], "ties": int(po["ties"]),
                        "vertices": int(len(pv)), "faces": int(len(pf)),
                        "watertight": rep2["watertight"],
                        "boundary_edges": int(rep2["boundary_edges"]),
                        "non_manifold_edges": int(rep2["non_manifold_edges"]),
                        "components": int(rep2["components"]),
                        "skin_to_poisson_mm": dev["to_lod_mm"],
                        "poisson_to_skin_mm": dev["from_lod_mm"],
                        "deviation_mm": dev["mean_mm"],
                        "p95_mm": dev["p95_mm"], "max_mm": dev["max_mm"]},
        }, fh, indent=2)
    print(f"\nFertig in {time.time() - t_start:.0f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
