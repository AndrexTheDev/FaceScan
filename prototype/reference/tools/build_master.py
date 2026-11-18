#!/usr/bin/env python3
"""Stufe 4 + 4.5: das MASTER-Mesh mit GLOBALER UV.

Das ist die Netz-Ausgabe auf Pro-Niveau (docs/03, 6.2): feines Gitter,
beobachtete Randanteile entfernt, auf die gemessene Tiefe nachgezogen --
und danach EIN UV-Atlas fuer das ganze Modell.

Warum ein eigenes Skript und nicht ein weiterer Block in run_m1.py:
Das Master-Mesh braucht ein 0,75-mm-Gitter (run_m1 rechnet mit 1,5 mm).
Beides in einem Lauf zu erzwingen hiesse, entweder M1 langsam zu machen
oder das Master-Mesh grob zu lassen. Die Stufen teilen sich die
Zwischenergebnisse ueber `master_state.npz`.

Aufruf:
    /tmp/qrenv/bin/python prototype/reference/tools/build_master.py
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
from facescan_ref import atlas                     # noqa: E402
from facescan_ref import hair as hairmod           # noqa: E402
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

# 0,75 mm -- docs/03 (6.2) nennt 1,5..3 M Dreiecke als Roh-Netz. Bei
# 1,5 mm Kaantenlaenge kommen rund 260.000 heraus, bei 0,75 mm das
# Vierfache. Das ist der Unterschied zwischen "M1 zeigt, dass es geht"
# und "Pro liefert ein Netz, das man retuschieren kann".
VOXEL_MM = 0.75
TRUNC_MM = 5.0
HAIR_VOXEL_MM = 1.2
BBOX = ([-130.0, -90.0, -130.0], [130.0, 160.0, 130.0])
ATLAS_RES = 2048
ATLAS_FACES = 400_000     # Netzgroesse, auf der der Atlas gerechnet wird
ATLAS_ITERS = 1           # Chart-Iterationen (xatlas-Standard)
ATLAS_MAX_COST = 3.0      # hoeher = durfen auch schlechte Charts bleiben


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
    for i, (r, t) in enumerate(poses):
        ren = Renderer(W, H, FX, FY, CX, CY)
        ren.draw(v, f, c, r, t, label=1, shading=sh_v)
        ren.draw(hv, hf, hc, r, t, label=2, shading=sh_h)
        o = ren.finish()
        frames.append({"R": r, "t": t,
                       "depth": o["depth"], "color": o["color"],
                       "label": o["label"], "mask": o["mask"],
                       "skin": o["label"] == 1,
                       "hair": o["label"] == 2,
                       "object": o["label"] > 0})
        print(f"  Bild {i + 1:2d}/{len(poses)}: Haut "
              f"{int(frames[-1]['skin'].sum()):6d} px, "
              f"Haar {int(frames[-1]['hair'].sum()):6d} px")
        sys.stdout.flush()
    return frames


def main() -> int:
    t_start = time.time()
    np.random.seed(SEED)
    os.makedirs(MESHES, exist_ok=True)
    os.makedirs(RESULTS, exist_ok=True)

    raw_path = os.path.join(MESHES, "master_raw.npz")

    banner("MASTER  Tiefenfusion auf 0,75 mm + globaler UV-Atlas")
    if os.path.exists(raw_path):
        st = np.load(raw_path)
        mv, mf = st["v"], st["f"]
        print(f"  Zwischenstand gefunden: {len(mv):,} Punkte / "
              f"{len(mf):,} Dreiecke -- Rekonstruktion wird uebersprungen")
        sys.stdout.flush()
        return atlas_and_write(mv, mf, t_start)
    head = hm.head_mesh(96, 144)
    hair_mesh = hm.hair_mesh(96, 144)
    poses = hm.orbit_poses(N_FRAMES, radius=520.0, yaw_deg=75.0, pitch_deg=9.0)
    light = np.array([0.25, 0.55, 1.0])

    t0 = time.time()
    frames = render_all(poses, head, hair_mesh, light)
    print(f"  -> {time.time() - t0:.0f} s nach dem Rendern")

    # ------------------------------------------------------ Haut (fein) --
    banner("Haut: TSDF-Fusion auf %.2f mm" % VOXEL_MM)
    vol = TsdfVolume(BBOX[0], BBOX[1], VOXEL_MM, TRUNC_MM)
    print(f"  Gitter {vol.shape} = {np.prod(vol.shape):,} Voxel "
          f"({np.prod(vol.shape) * 8 / 1e6:.0f} MB)")
    t0 = time.time()
    for fr in frames:
        w = TsdfVolume.incidence_weights(fr["depth"], fr["skin"], FX, FY, CX, CY)
        vol.integrate(fr["depth"], fr["skin"], fr["R"], fr["t"], FX, FY, CX, CY,
                      weights=w)
    print(f"  fusioniert in {time.time() - t0:.1f} s")

    t0 = time.time()
    sv_raw, sf_raw = marching_tetrahedra(vol, min_weight=0.05)
    print(f"  Nullniveauflaeche in {time.time() - t0:.1f} s: "
          f"{len(sv_raw):,} Punkte / {len(sf_raw):,} Dreiecke")
    del vol

    n_raw = mt.vertex_normals(sv_raw, sf_raw)
    seen_raw = mt.observed_points(sv_raw, frames, FX, FY, CX, CY, label=1,
                                  min_views=2, normals=n_raw, min_cos=0.35)
    sv, sf = mt.drop_unobserved_triangles(sv_raw, sf_raw, seen_raw, min_seen=3)
    print(f"  ohne Randwand: {len(sv):,} Punkte / {len(sf):,} Dreiecke "
          f"({100.0 * (1 - len(sf) / max(len(sf_raw), 1)):.1f} % entfernt)")
    sv = refine_by_depth(sv, sf, frames, FX, FY, CX, CY, label=1,
                         iters=5, depth_tol_mm=2.0, max_move_mm=1.5)
    print(f"  auf die gemessene Tiefe nachgezogen ({time.time() - t_start:.0f} s)")
    sys.stdout.flush()

    # ---------------------------------------------------------- Haare ----
    banner("Haare: Visual Hull auf %.2f mm" % HAIR_VOXEL_MM)
    nb = [[BBOX[0][i] + k for k in (0, 0, 0)] for i in range(3)]
    dims = [int(round((BBOX[1][i] - BBOX[0][i]) / HAIR_VOXEL_MM)) for i in range(3)]
    bmax = [BBOX[0][i] + dims[i] * HAIR_VOXEL_MM for i in range(3)]
    hvol = TsdfVolume(BBOX[0], bmax, HAIR_VOXEL_MM, TRUNC_MM)
    print(f"  Gitter {tuple(dims)} = {np.prod(dims):,} Voxel")
    hull = hairmod.visual_hull(hvol, poses, [fr["object"] for fr in frames],
                               FX, FY, CX, CY)
    in_head = hairmod.inside_test(hvol, None, hm.inside_head)
    seen = hairmod.observed_voxels(hvol, poses, [fr["hair"] for fr in frames],
                                   FX, FY, CX, CY)
    cand = hull & (~in_head) & seen
    print(f"  beobachtete Haar-Voxel: {int(cand.sum()):,}")
    prior, prior_mm = hairmod.thickness_field_prior(
        hvol, cand, hm.head_radius, hm.hair_region, grow_voxels=1)
    occ = hull & prior & (~in_head)
    print(f"  nach allen Regeln: {int(occ.sum()):,} Voxel")
    hv2, hf2 = (np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64))
    if occ.any():
        hvol.sdf = hairmod.occupancy_to_sdf(occ)
        hvol.weight = np.ones(hvol.sdf.shape, dtype=np.float32)
        # Der Konstruktor legt ein Voxel mehr je Achse an. Nach dem
        # Austausch der Felder muss dims zum INHALT passen -- sonst
        # zaehlt Marching-Tetrahedra ueber das Array hinaus.
        hvol.dims = np.asarray(hvol.sdf.shape, dtype=np.int64)
        hv2, hf2 = marching_tetrahedra(hvol, min_weight=0.5)
    print(f"  Haar-Mesh: {len(hv2):,} Punkte / {len(hf2):,} Dreiecke")
    sys.stdout.flush()

    # ----------------------------------------------------- Master-Mesh ---
    banner("Master-Mesh: Haut + Haar zu einem Netz")
    if len(hv2):
        mv = np.vstack([sv, hv2])
        mf = np.vstack([sf, hf2 + len(sv)])
    else:
        mv, mf = sv, sf
    st = mt.mesh_stats(mv, mf)
    print(f"  {len(mv):,} Punkte / {len(mf):,} Dreiecke, "
          f"Flaeche {st['surface_cm2']:.1f} cm², "
          f"entartete Dreiecke: {st['degenerate_triangles']}")
    # SOFORT sichern. Der Atlas-Schritt ist der teure (xatlas braucht auf
    # 1,5 M Dreiecken Minuten), und ohne diesen Zwischenstand kostet
    # jeder Atlas-Versuch die volle Rekonstruktion mit.
    np.savez_compressed(os.path.join(MESHES, "master_raw.npz"), v=mv, f=mf)
    print("  zwischengesichert: master_raw.npz")
    sys.stdout.flush()
    return atlas_and_write(mv, mf, t_start)

    # --------------------------------------------------- Globaler Atlas --
def atlas_and_write(mv, mf, t_start, uv_method="xatlas"):
    banner("Globaler UV-Atlas (xatlas, %d²)" % ATLAS_RES)

    # Erst saeubern, dann in Charts zerlegen -- in dieser Reihenfolge.
    # Ein Visual-Hull-Haarnetz enthaelt hunderte Inseln aus drei bis
    # dreissig Dreiecken: geometrisch echt (ein Voxel, das den Anschluss
    # verpasst hat), fuer den Atlas aber pures Rauschen. Jede Insel wird
    # ein eigener Chart, und jeder Chart bekommt beim Packen seinen
    # Abstand -- 855 Inseln kosten also 855-mal Rand, den niemand sieht.
    # docs/03 (6.2) nennt dafuer die Grenze 500 Dreiecke.
    from facescan_ref import meshopt as mo
    n_before = (len(mv), len(mf))
    mv, mf, _, _ = mo.drop_small_components(mv, mf, min_faces=500)
    print(f"  Inseln entfernt (<500 Dreiecke): {n_before[1]:,} -> {len(mf):,} "
          f"Dreiecke, {n_before[0]:,} -> {len(mv):,} Punkte")
    np.savez_compressed(os.path.join(MESHES, "master_raw.npz"), v=mv, f=mf)
    sys.stdout.flush()

    uv_method = "xatlas"
    for arg in sys.argv[1:]:
        if arg.startswith("--uv="):
            uv_method = arg.split("=", 1)[1].strip()
    print(f"  UV-Verfahren: {uv_method}")

    if uv_method != "xatlas":
        # Zylinderprojektion braucht KEIN heruntergerechnetes Netz -- sie
        # ist O(Punkte). Deshalb bleibt das Master-Mesh hier in voller
        # Aufloesung, und genau das wollen wir auch: das gelieferte
        # Master-Mesh ist das Rohnetz, nicht eine Dezimierung davon.
        before = mo.winding_errors(mf)
        mv, mf = mo.orient_mesh(mv, mf)
        print(f"  Umlaufrichtung: {before:,} falsch laufende Kanten -> "
              f"{mo.winding_errors(mf):,}")
        sys.stdout.flush()
        return atlas_and_write2(mv, mf, t_start, uv_method)

    # --- Rohnetz sichern, dann fuer den Atlas herunterrechnen -----------
    # Warum: xatlas braucht auf dem 1,46-Mio.-Netz laenger als 20 Minuten.
    # Der Grund ist die HAUT, nicht die Menge: `refine_by_depth` erzeugt
    # Sliver-Dreiecke bis hinunter zu 6e-6 mm² (Median 0,096 mm²). Ein so
    # schlecht konditioniertes Netz bringt den LSCM-Löser nicht zur
    # Konvergenz. Die Haare (gleichmäßige 0,18-mm²-Dreiecke) laufen
    # dagegen mit 0,06 ms je Dreieck durch.
    # Das Netz für den Atlas ist deshalb eine Dezimierung. Das ist kein
    # Qualitätsverlust, sondern messbar: die Formabweichung wird unten
    # ausgewiesen.
    print(f"  Rohnetz gesichert: {len(mf):,} Dreiecke")
    t0 = time.time()
    mv, mf, _, _ = mo.quadric_decimate(mv, mf, ATLAS_FACES)
    print(f"  auf {len(mf):,} Dreiecke heruntergerechnet "
          f"({time.time() - t0:.0f} s)")
    sys.stdout.flush()

    # --- Umlaufrichtung heilen ------------------------------------------
    # Ohne diesen Schritt zerlegt xatlas das Netz in tausende
    # Einzel-Charts: ein Dezimierer, der Dreiecke sortiert statt
    # zyklisch zu drehen, verliert die Orientierung, und xatlas erkennt
    # die Nachbarschaft nicht mehr. (Der Fehler steckte bis heute in
    # `_MeshState` und hat 20.753 Charts aus 25.000 Dreiecken gemacht.)
    before = mo.winding_errors(mf)
    mv, mf = mo.orient_mesh(mv, mf)
    after = mo.winding_errors(mf)
    print(f"  Umlaufrichtung: {before:,} falsch laufende Kanten -> {after:,}")
    sys.stdout.flush()

    t0 = time.time()
    # max_iterations=1 ist der xatlas-Standard. Mehr Iterationen
    # verbessern die Chart-Qualitaet, kosten aber linear Zeit -- und bei
    # einem 1,5-Millionen-Dreiecke-Netz sind das schnell Minuten pro
    # Iteration. Der Gewinn ist klein gegenueber dem, was das Packen
    # (padding) ohnehin an Sichtbarkeit bestimmt.
    a = atlas.global_uv(mv, mf, resolution=ATLAS_RES, padding=4,
                        max_iterations=ATLAS_ITERS, max_cost=ATLAS_MAX_COST,
                        method=uv_method)
    print(f"  Methode: {a['method']} in {time.time() - t0:.1f} s")
    print(f"  Charts: {a['charts']}, Auslastung: "
          f"{a.get('utilization', 0.0) * 100:.1f} %, "
          f"Atlas {a.get('atlas_width', 0)}x{a.get('atlas_height', 0)} px, "
          f"{a.get('texels_per_unit', 0.0):.2f} Texel/mm")
    if a["method"] == "cylindrical":
        # Texel/Millimeter ausrechnen: die Zahl, die man braucht, um zu
        # sagen, ob 2048² reicht. Umfang auf halber Hoehe geteilt durch
        # die Atlasbreite.
        lo, hi = mv[:, 1].min(), mv[:, 1].max()
        band = mv[(mv[:, 1] > 0.4 * hi + 0.6 * lo) & (mv[:, 1] < 0.6 * hi + 0.4 * lo)]
        if len(band) > 100:
            r = np.hypot(band[:, 0], band[:, 2]).mean()
            print(f"  Umfang auf halber Hoehe: {2 * np.pi * r:.0f} mm -> "
                  f"{ATLAS_RES / (2 * np.pi * r):.2f} Texel/mm")
    print(f"  Punkte durch Naht-Verdopplung: {len(mv):,} -> {len(a['vertices']):,}")
    sys.stdout.flush()

    # Formabweichung des Atlas-Netzes gegen das Rohnetz: die Zahl, die
    # belegt, dass das Herunterrechnen nichts gekostet hat.
    st_raw = np.load(os.path.join(MESHES, "master_raw.npz"))
    dev = mt.surface_deviation(st_raw["v"], st_raw["f"],
                               a["vertices"], a["faces"], cell=3.0,
                               max_ref_points=40_000)
    print(f"  Formfehler Atlas-Netz gegen Rohnetz: {dev['mean_mm']:.3f} mm "
          f"(p95 {dev['p95_mm']:.3f}, max {dev['max_mm']:.2f})")
    sys.stdout.flush()

    mvu, mfu, muv = a["vertices"], a["faces"], a["uv"]
    np.savez_compressed(os.path.join(MESHES, "master_state.npz"),
                        v=mvu, f=mfu, uv=muv,
                        skin_faces=np.array([len(sf)], dtype=np.int64),
                        charts=np.array([a["charts"]]),
                        utilization=np.array([a.get("utilization", 0.0)]),
                        texels_per_unit=np.array([a.get("texels_per_unit", 0.0)]),
                        method=np.array([a["method"]]))

    # Master-OBJ: Geometrie + UV, KEINE Textur (docs/04, 14).
    # uv wird beim Schreiben gekippt (1 - v), weil OBJ/mtl Bildzeilen von
    # OBEN zaehlt, der Atlas aber von UNTEN.
    from facescan_ref import export_mesh as ex
    obj_path = os.path.join(MESHES, "facescan_master_uv.obj")
    ex.write_obj(obj_path, mvu, mfu, None, name="FaceScan_Master",
                 normals=mt.vertex_normals(mvu, mfu), uv=muv)
    print(f"  geschrieben: {os.path.basename(obj_path)} "
          f"({os.path.getsize(obj_path) / 1e6:.1f} MB)")
    print(f"\nFertig in {time.time() - t_start:.0f} s")
    return 0



def atlas_and_write2(mv, mf, t_start, uv_method="cylindrical"):
    """Atlas auf dem VOLLEN Netz (Zylinderprojektion, O(Punkte)).

    Gleicher Ausgang wie `atlas_and_write`, nur ohne die Dezimierung.
    """
    banner("Globaler UV-Atlas (%s, %d²)" % (uv_method, ATLAS_RES))
    t0 = time.time()
    a = atlas.global_uv(mv, mf, resolution=ATLAS_RES, method=uv_method)
    print(f"  Methode: {a['method']} in {time.time() - t0:.1f} s, "
          f"{a['charts']} Chart(s), {len(mv):,} Punkte")
    lo, hi = mv[:, 1].min(), mv[:, 1].max()
    band = mv[(mv[:, 1] > 0.4 * hi + 0.6 * lo) & (mv[:, 1] < 0.6 * hi + 0.4 * lo)]
    if len(band) > 100:
        r = float(np.hypot(band[:, 0], band[:, 2]).mean())
        print(f"  Umfang auf halber Hoehe: {2 * np.pi * r:.0f} mm -> "
              f"{ATLAS_RES / (2 * np.pi * r):.2f} Texel/mm "
              f"(= {2 * np.pi * r / ATLAS_RES:.3f} mm je Texel)")
    sys.stdout.flush()

    mvu, mfu, muv = a["vertices"], a["faces"], a["uv"]
    np.savez_compressed(os.path.join(MESHES, "master_state.npz"),
                        v=mvu, f=mfu, uv=muv,
                        charts=np.array([a["charts"]]),
                        utilization=np.array([a.get("utilization", 0.0)]),
                        texels_per_unit=np.array([a.get("texels_per_unit", 0.0)]),
                        method=np.array([a["method"]]))
    from facescan_ref import export_mesh as ex
    obj_path = os.path.join(MESHES, "facescan_master_uv.obj")
    ex.write_obj(obj_path, mvu, mfu, None, name="FaceScan_Master",
                 normals=mt.vertex_normals(mvu, mfu), uv=muv)
    print(f"  geschrieben: {os.path.basename(obj_path)} "
          f"({os.path.getsize(obj_path) / 1e6:.1f} MB)")
    print(f"\nFertig in {time.time() - t_start:.0f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
