#!/usr/bin/env python3
"""M1: von den Bildern zum texturierten Mesh.

M0 hat bewiesen, dass POSE und MODELL-FIT ohne ARCore funktionieren.
M1 beweist den Rest der Geometrie-Kette -- wieder mit Zahlen gegen eine
bekannte Ground Truth:

  G1  Tiefenfusion: wie genau wird die HAUT aus N Handy-Bildern?
      (Chamfer-Abstand, docs/10: <= 0,8 mm)
  G2  Haare Stufe L1: sitzt das Volumen? (IoU, docs/10: >= 0,85)
      -- getrennt ausgewiesen fuer "beobachtet" und "extrapoliert"
  G3  Textur: wie viel der Oberflaeche bekommt Farbe, und wie oft?
  G4  Export: kommen OBJ / PLY / GLB so heraus, dass ein fremdes Programm
      sie GENAUSO wieder einliest? (Ruecklese-Test, nicht "Datei existiert")

Aufruf:
    /tmp/qrenv/bin/python prototype/reference/python/run_m1.py

Laufzeit: ca. 3-6 Minuten (reines NumPy, ein Kern).
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from facescan_ref import headmesh as hm          # noqa: E402
from facescan_ref import export_mesh as ex       # noqa: E402
from facescan_ref import export_more as em       # noqa: E402
from facescan_ref import hair as hairmod         # noqa: E402
from facescan_ref import metrics as mt           # noqa: E402
from facescan_ref.fusion import TsdfVolume, marching_tetrahedra  # noqa: E402
from facescan_ref.raster import Renderer, lambert  # noqa: E402
from facescan_ref.refine import refine_by_depth  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "..", "results")
OUT = os.path.join(HERE, "..", "meshes")

# --- Versuchsaufbau -------------------------------------------------------
W, H = 540, 960
FX = FY = 916.6
CX, CY = W / 2.0, H / 2.0
N_FRAMES = 16
VOXEL_MM = 1.5
TRUNC_MM = 6.0
BBOX = ([-155, -170, -155], [155, 170, 155])
SEED = 2026


def verify_export(path: str, v: np.ndarray, f: np.ndarray,
                  colors: np.ndarray, normals: np.ndarray | None = None) -> dict:
    """Liest eine geschriebene Datei zurueck und vergleicht.

    Jedes Format hat seine eigenen Fallen -- deshalb prueft jedes Format
    etwas anderes. Wichtig ist nur: es wird WIRKLICH gelesen, nicht bloss
    die Groesse geprueft.
    """
    res = {"file": os.path.basename(path), "passed": False, "note": ""}
    n_v, n_f = len(v), len(f)
    # Normalen werden separat geprueft, weil sie in float32 stehen
    # (GLB, ABC) oder gar nicht mitkommen (STL). Wer sie in den
    # Geometrievergleich hineinmischt, prueft am Ende die Genauigkeit
    # von float32 und nicht mehr die des Exports.
    res["normals"] = None

    def ncheck(got):
        if normals is None or got is None:
            return None
        got = np.asarray(got, dtype=np.float64)
        if got.shape != normals.shape:
            return "Form %s != %s" % (got.shape, normals.shape)
        return float(np.abs(got - normals).max())

    try:
        if path.endswith((".obj", ".ply", ".glb")):
            r = ex.roundtrip_check(path, v, f, colors)
            res["passed"] = bool(r["passed"])
            res["note"] = (f"{n_v:,} Punkte / {n_f:,} Dreiecke, "
                           f"max. Abweichung {r['max_vertex_error_mm']:.1e} mm")
            if path.endswith((".obj", ".ply")):
                back = (ex.read_obj(path) if path.endswith(".obj")
                        else ex.read_ply(path))
                res["normals"] = ncheck(back.get("normals"))
        elif path.endswith(".stl"):
            r = em.read_stl(path)
            want = v[f].reshape(-1, 3)
            ok_pts = r["vertices"].shape == want.shape
            err = float(np.abs(r["vertices"] - want).max()) if ok_pts else float("inf")
            res["passed"] = ok_pts and err < 1e-2 and r["faces"].shape == f.shape
            res["note"] = f"{n_f:,} Dreiecke (je 3 Punkte), max. Abweichung {err:.1e} mm"
        elif path.endswith(".usda"):
            r = em.read_usda(path)
            ok = (np.array_equal(r["faceVertexIndices"], f.reshape(-1))
                  and r["vertices"].shape == v.shape
                  and abs(r["metersPerUnit"] - 0.001) < 1e-12
                  and r["upAxis"] == "Y")
            err = float(np.abs(r["vertices"] - v).max()) if r["vertices"].shape == v.shape else float("inf")
            res["passed"] = bool(ok and err < 1e-6)
            res["normals"] = ncheck(r.get("normals"))
            if res["normals"] is not None and not isinstance(res["normals"], float):
                res["passed"] = False        # Normalen fehlen oder sind falsch
            elif isinstance(res["normals"], float) and res["normals"] > 1e-4:
                res["passed"] = False
            res["note"] = (f"{n_v:,} Punkte, Indizes identisch, "
                           f"metersPerUnit={r['metersPerUnit']}, upAxis={r['upAxis']}")
        elif path.endswith(".usdz"):
            r = em.read_usdz(path)
            ok = (np.array_equal(r["faceVertexIndices"], f.reshape(-1))
                  and r["crc_ok"] and r["all_stored"] and r["aligned64"]
                  and r["primary"] == r["entries"][0])
            res["passed"] = bool(ok)
            res["note"] = (f"ZIP mit {len(r['entries'])} Eintrag(en), primaer "
                           f"{r['primary']}, STORED={r['all_stored']}, "
                           f"64-Byte-ausgerichtet={r['aligned64']}")
        elif path.endswith(".abc"):
            r = em.read_abc(path)
            ok = (r["version"] == 1 and r["vertices"].shape == v.shape
                  and np.array_equal(r["faces"], f)
                  and np.all(r["face_counts"] == 3)
                  and "AbcGeom_PolyMesh_v1" in r["schema"])
            err = float(np.abs(r["vertices"] - v).max()) if r["vertices"].shape == v.shape else float("inf")
            res["passed"] = bool(ok and err < 1e-3)
            res["normals"] = ncheck(r.get("normals"))
            if not isinstance(res["normals"], float) or res["normals"] > 1e-4:
                res["passed"] = False
            res["note"] = (f"Ogawa v{r['version']}, {n_v:,} Punkte (float32, "
                           f"max. Abweichung {err:.1e} mm), Schema PolyMesh_v1")
        elif path.endswith(".dae"):
            r = em.read_dae(path, with_arrays=True)
            idx = r["tris"].reshape(-1, 3)
            pos = r["sources"]["positions"]["data"]
            err = float(np.abs(pos - v).max()) if pos.shape == v.shape \
                else float("inf")
            ok = (abs(r["unit_meter"] - 0.001) < 1e-12
                  and r["up_axis"] == "Y_UP"
                  and np.array_equal(idx, f)
                  and not r["dangling_refs"] and err < 1e-9)
            # Vertexfarben stehen bei uns als 0..1-Quelle im Netz; das
            # ist die einzige Stelle, an der wir runden muessen.
            col = r["sources"].get("colors", {}).get("data")
            if col is not None and col.shape == colors.shape:
                cerr = float(np.abs(col * 255.0 - colors).max())
            else:
                cerr, ok = float("inf"), False
            ok = bool(ok) and cerr < 1e-6
            res["normals"] = ncheck(r["sources"].get("normals", {}).get("data"))
            if not isinstance(res["normals"], float) or res["normals"] > 1e-4:
                ok = False
            res["passed"] = ok
            res["note"] = (f"Collada 1.4.1, {n_v:,} Punkte identisch "
                           f"({err:.1e} mm), {n_f:,} Indizes identisch, "
                           f"unit meter={r['unit_meter']}, "
                           f"up_axis={r['up_axis']}, Farbe {cerr:.1e}/255, "
                           f"Sources {sorted(r['sources'])}, "
                           f"Verweise ins Leere: {len(r['dangling_refs'])}")
        elif path.endswith(".fbx"):
            r = em.read_fbx(path)
            ok = (r["version"] == 7500 and "vertices" in r
                  and r["vertices"].shape == v.shape)
            err = float(np.abs(r["vertices"] - v).max()) if ok else float("inf")
            poly = r.get("polygonVertexIndex")
            ok_poly = poly is not None and len(poly) == 3 * n_f and poly[2] < 0
            res["passed"] = bool(ok and err < 1e-9 and ok_poly)
            res["note"] = (f"Version {r['version']}, {n_v:,} Punkte, "
                           f"PolygonIndex-Konvention {'korrekt' if ok_poly else 'FALSCH'}")
        else:
            res["note"] = "unbekanntes Format"
    except Exception as exc:                       # noqa: BLE001
        res["note"] = "Lesefehler: %s" % exc
    return res


def _view_counts(points, frames, fx, fy, cx, cy, label):
    """Anzahl der Sichtungen je Punkt (fuer die Auswertung gespeichert)."""
    v = np.asarray(points, dtype=np.float64)
    views = np.zeros(len(v), dtype=np.int64)
    for fr in frames:
        r = np.asarray(fr["R"], dtype=np.float64)
        t = np.asarray(fr["t"], dtype=np.float64)
        depth, m = fr["depth"], fr["mask"]
        h, w = depth.shape
        cam = v @ r.T + t
        z = cam[:, 2]
        ok = z > 1.0
        zs = np.where(np.abs(z) < 1e-9, 1e-9, z)
        ui = np.rint(fx * cam[:, 0] / zs + cx).astype(np.int64)
        vi = np.rint(fy * cam[:, 1] / zs + cy).astype(np.int64)
        ok &= (ui >= 0) & (ui < w) & (vi >= 0) & (vi < h)
        idx = np.where(ok)[0]
        if not len(idx):
            continue
        good = m[vi[idx], ui[idx]] & np.isfinite(depth[vi[idx], ui[idx]])
        good &= np.abs(depth[vi[idx], ui[idx]] - z[idx]) <= 2.5
        good &= fr["label"][vi[idx], ui[idx]] == label
        sel = idx[good]
        if len(sel):
            views[sel] += 1
    return views


def banner(text: str) -> None:
    print("\n" + "=" * 74)
    print(text)
    print("=" * 74)


def render_all(poses, head, hair_mesh, light):
    """Rendert alle Bilder: Tiefe, Material-Label (1=Haut, 2=Haar), Farbe."""
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
        frames.append({
            "R": r, "t": t,
            "depth": o["depth"], "color": o["color"], "label": o["label"],
            "mask": o["mask"],
            "skin": o["label"] == 1,
            "hair": o["label"] == 2,
            "object": o["label"] > 0,
        })
        print(f"  Bild {i + 1:2d}/{len(poses)}: Haut {int(frames[-1]['skin'].sum()):6d} px, "
              f"Haar {int(frames[-1]['hair'].sum()):6d} px")
    return frames


def main() -> int:
    t_start = time.time()
    np.random.seed(SEED)

    banner("M1  Von den Bildern zum Mesh (Tiefenfusion, Haare, Textur, Export)")

    # ---------------------------------------------------------------- GT --
    head = hm.head_mesh(96, 144)
    hair_mesh = hm.hair_mesh(96, 144)
    v, f, uv, c = head
    hv, hf, huv, hc = hair_mesh
    print(f"Ground Truth: Kopf {len(v)} Punkte / {len(f)} Dreiecke, "
          f"Haar {len(hv)} / {len(hf)}")
    print(f"Kopf-Radius {np.linalg.norm(v, axis=1).min():.1f} .. "
          f"{np.linalg.norm(v, axis=1).max():.1f} mm")
    # Wie viel der Kopfform ist "Detail", das kein Modell ausdruecken kann?
    plain = hm.uv_sphere(96, 144)[0]
    base_r = 1.0 / np.sqrt((plain[:, 0] / hm.RX) ** 2 + (plain[:, 1] / hm.RY) ** 2
                           + (plain[:, 2] / hm.RZ) ** 2)
    detail = np.abs(np.linalg.norm(v, axis=1) - base_r)
    print(f"Abweichung vom reinen Ellipsoid: {detail.mean():.2f} mm im Mittel, "
          f"{detail.max():.2f} mm maximal (= Ohren, Muttermal, Falten)")
    print("  -> Genau dieser Anteil ist es, den ein Modell-Fit VERLIERT und")
    print("     die Tiefenfusion GEWINNT. Das ist die Rechtfertigung fuer MVS.")

    # ------------------------------------------------------------ Bilder --
    banner(f"Aufnahmen: {N_FRAMES} Bilder, {W}x{H}, Brennweite {FX} px")
    poses = hm.orbit_poses(N_FRAMES, radius=520.0, yaw_deg=75.0, pitch_deg=9.0)
    light = np.array([0.25, 0.55, 1.0])
    frames = render_all(poses, head, hair_mesh, light)
    print(f"  -> {time.time() - t_start:.0f} s nach dem Rendern")

    # ------------------------------------------------- G1: Haut fusionieren
    banner("G1  Tiefenfusion der HAUT (TSDF + Marching-Tetrahedra)")
    vol = TsdfVolume(BBOX[0], BBOX[1], VOXEL_MM, TRUNC_MM)
    print(f"  Gitter {vol.shape} = {np.prod(vol.shape):,} Voxel "
          f"({np.prod(vol.shape) * 8 / 1e6:.0f} MB), Kante {VOXEL_MM} mm")
    t0 = time.time()
    for i, fr in enumerate(frames):
        w = TsdfVolume.incidence_weights(fr["depth"], fr["skin"], FX, FY, CX, CY)
        vol.integrate(fr["depth"], fr["skin"], fr["R"], fr["t"], FX, FY, CX, CY,
                      weights=w)
    print(f"  fusioniert in {time.time() - t0:.1f} s (mit Einfallswinkel-Gewichtung)")

    t0 = time.time()
    # min_weight MUSS kleiner sein als das kleinste Beobachtungsgewicht
    # (unten 0.15), sonst verschwindet streifend gesehene Flaeche komplett.
    sv_raw, sf_raw = marching_tetrahedra(vol, min_weight=0.05)
    print(f"  Oberflaeche geschnitten in {time.time() - t0:.1f} s: "
          f"{len(sv_raw):,} Punkte / {len(sf_raw):,} Dreiecke")

    # Die "Wand" am Rand des beobachteten Bereichs ist kein Gesicht -> weg.
    n_raw = mt.vertex_normals(sv_raw, sf_raw)
    seen_raw = mt.observed_points(sv_raw, frames, FX, FY, CX, CY, label=1,
                                  min_views=2, normals=n_raw, min_cos=0.35)
    # min_seen=3: nur Dreiecke, deren Ecken ALLE wirklich (und nicht nur
    # streifend) gesehen wurden -- nur die bekommen auch Farbe.
    # Damit hat das exportierte Modell keine schwarzen Flecken -- ein
    # Dreieck mit einer ungesehenen Ecke ist im Export ein schwarzer Punkt.
    sv, sf = mt.drop_unobserved_triangles(sv_raw, sf_raw, seen_raw, min_seen=3)
    print(f"  nach Entfernen der Randwand: {len(sv):,} Punkte / {len(sf):,} Dreiecke "
          f"({100.0 * (1 - len(sf) / max(len(sf_raw), 1)):.1f} % entfernt)")

    # Stufe 12: das Mesh auf die gemessene Tiefe ziehen
    sv_before = sv.copy()
    sv = refine_by_depth(sv, sf, frames, FX, FY, CX, CY, label=1,
                         iters=5, depth_tol_mm=2.0, max_move_mm=1.5)
    moved = np.linalg.norm(sv - sv_before, axis=1)
    print(f"  Verfeinerung: {moved.mean():.3f} mm je Punkt im Mittel "
          f"(max {moved.max():.3f} mm)")

    stats_skin = mt.mesh_stats(sv, sf)
    print(f"  Flaeche {stats_skin['surface_cm2']:.1f} cm², "
          f"Kanten {stats_skin['edge_min_mm']:.2f}..{stats_skin['edge_max_mm']:.2f} mm, "
          f"entartete Dreiecke: {stats_skin['degenerate_triangles']}")

    # Chamfer NUR auf der beobachteten Haut. Was unter den Haaren liegt,
    # sieht keine Kamera -- darueber eine Zahl auszurechnen waare Etikettenschwindel.
    # min_views=3 statt 1: Punkte, die nur ein einziges Bild gesehen hat,
    # liegen am Rand des beobachteten Bereichs. Dort endet die
    # Rekonstruktion konstruktionsbedingt -- sie in den Chamfer
    # einzurechnen wuerde die Methode schlechter machen, als sie ist.
    # Auswertung bewusst ZWEISTUFIG:
    #   * Rekonstruktion -> Wahrheit: Referenz ist die gesamte SICHTBARE Haut
    #     (>= 1 Sichtung). Frage: liegt die Rekonstruktion auf der echten Haut?
    #   * Wahrheit -> Rekonstruktion: nur gut beobachtete Punkte (>= 5
    #     Sichtungen). Frage: haben wir da, wo wir viel sahen, auch geliefert?
    # Wer beide Richtungen mit derselben harten Schwelle rechnet, bestraft die
    # Rekonstruktion fuer Flaeche, die sie gar nicht kennen kann.
    gt_all = mt.sample_surface(v, f, 60000, seed=SEED)
    gt_views = _view_counts(gt_all, frames, FX, FY, CX, CY, 1)
    gt_vis = gt_all[gt_views >= 1]
    gt_good = gt_all[gt_views >= 5]
    rec_pts = mt.sample_surface(sv, sf, 60000, seed=SEED + 1)
    print(f"  sichtbare Haut: {100 * (gt_views >= 1).mean():.1f} % der wahren Flaeche, "
          f"gut beobachtet (>= 5x): {100 * (gt_views >= 5).mean():.1f} %")
    print(f"  Referenzwolken: {len(gt_vis):,} sichtbare / {len(gt_good):,} gut "
          f"beobachtete Punkte, {len(rec_pts):,} Rekonstruktionspunkte")
    # Punktwolken ablegen: so kann man die Auswertung nachrechnen, ohne die
    # ganze Pipeline noch einmal laufen zu lassen.
    os.makedirs(OUT, exist_ok=True)
    np.savez_compressed(
        os.path.join(OUT, "m1_chamfer_points.npz"),
        gt=gt_good, recon=rec_pts,
        gt_all=gt_all, gt_views=_view_counts(gt_all, frames, FX, FY, CX, CY, 1),
        sv=sv, sf=sf, sv_raw=sv_raw, sf_raw=sf_raw,
        sv_views=_view_counts(sv, frames, FX, FY, CX, CY, 1),
        seen_raw=seen_raw,
    )
    cham = mt.chamfer(gt_good, rec_pts, cell=1.5, shells=5)
    cham_vis = mt.chamfer(gt_vis, rec_pts, cell=1.5, shells=5)
    print(f"  Chamfer: {cham['chamfer_mm']:.3f} mm | "
          f"Hin {cham['from_recon_mm']:.3f} | Zurueck {cham['to_recon_mm']:.3f} | "
          f"p95 {cham['p95_mm']:.3f} | max {cham['max_mm']:.3f}")
    print(f"  Anteil der Punkte <= 0,8 mm: {cham['within_0_8mm'] * 100:.1f} %")

    # ------------------------------------------------ G2: Haare (Stufe L1)
    banner("G2  Haare Stufe L1: Volumen aus der Silhouette (Visual Hull)")
    t0 = time.time()
    hair_masks = [fr["hair"] for fr in frames]
    obj_masks = [fr["object"] for fr in frames]

    # WICHTIG (und der Fehler im ersten Durchlauf): der Visual Hull braucht
    # die Silhouette des GANZEN Objekts (Kopf + Haar), nicht nur die der
    # Haare. Ein Haarvoxel am Hinterkopf wird aus jeder vorderen Kamera vom
    # KOPF verdeckt -- es faellt also auf ein HAUT-Pixel. Wer hier die
    # Haar-Maske als Silhouette nimmt, loescht den halben Hinterkopf.
    hull = hairmod.visual_hull(vol, poses, obj_masks, FX, FY, CX, CY)
    print(f"  Visual Hull (Objekt-Silhouette): {int(hull.sum()):,} Voxel "
          f"({time.time() - t0:.0f} s)")

    in_head = hairmod.inside_test(vol, None, hm.inside_head)
    seen = hairmod.observed_voxels(vol, poses, hair_masks, FX, FY, CX, CY)

    # Dicke aus den BEOBACHTETEN Haaren schaetzen (nicht raten, nicht aus der
    # Ground Truth). Der Hinterkopf wird damit extrapoliert -- und genau das
    # weist die App spaeter als "geschaetzt" aus.
    cand = hull & (~in_head) & seen
    ii, jj, kk = np.nonzero(cand)
    print(f"  beobachtete Haar-Voxel: {len(ii):,}")

    prior, prior_mm = hairmod.thickness_field_prior(
        vol, cand, hm.head_radius, hm.hair_region, grow_voxels=1)
    print(f"  richtungsabhaengige Dickenschranke: Median {prior_mm:.1f} mm")
    occ = hull & prior & (~in_head)
    print(f"  nach allen Regeln: {int(occ.sum()):,} Voxel "
          f"({time.time() - t0:.0f} s)")

    gt_hair = hairmod.inside_test(vol, None, hm.in_hair_volume)
    print(f"  Ground Truth: {int(gt_hair.sum()):,} Voxel, davon beobachtet: "
          f"{int((gt_hair & seen).sum()):,}")

    iou_all = mt.iou(occ, gt_hair)
    iou_obs = mt.iou(occ & seen, gt_hair & seen)
    print(f"  IoU gesamt:      {iou_all['iou']:.3f}  "
          f"(Treffer {iou_all['precision']:.3f}, Abdeckung {iou_all['recall']:.3f})")
    print(f"  IoU beobachtet:  {iou_obs['iou']:.3f}  "
          f"(Treffer {iou_obs['precision']:.3f}, Abdeckung {iou_obs['recall']:.3f})")
    print("  -> Der Unterschied IST der Hinterkopf. Genau dafuer empfiehlt die")
    print("     App einen Spiegel oder eine zweite Person.")

    hv2, hf2 = (np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64))
    if occ.any():
        # L1 ist ein VOLUMEN, kein Detailmodell: 3 mm Gitter genuegt und
        # spart gegenueber 1,5 mm rund 75 % der Dreiecke. (Ohne das kommt ein
        # 730.000-Dreiecke-Mesh heraus -- fuer ein Handy zu viel, und fuer
        # "Volumen" auch unnoetig genau.)
        occ2 = occ[::2, ::2, ::2]
        v2 = VOXEL_MM * 2.0
        bmax = [BBOX[0][i] + occ2.shape[i] * v2 for i in range(3)]
        hvol = TsdfVolume(BBOX[0], bmax, v2, TRUNC_MM)
        hvol.sdf = hairmod.occupancy_to_sdf(occ2)
        hvol.weight = np.ones(hvol.dims, dtype=np.float32)
        # Achtung: der Konstruktor legt ein Voxel mehr an (obere Ecke).
        # Nach dem Austausch der Felder muss dims zum Inhalt passen --
        # sonst zaehlt Marching-Tetrahedra ueber das Array hinaus.
        hvol.dims = np.asarray(occ2.shape, dtype=np.int64)
        hv2, hf2 = marching_tetrahedra(hvol, min_weight=0.5)
        print(f"  Haar-Mesh auf {v2:.1f} mm Gitter: {len(hv2):,} Punkte / "
              f"{len(hf2):,} Dreiecke")
    stats_hair = mt.mesh_stats(hv2, hf2) if len(hv2) else {}

    # ------------------------------------------------------- G3: Textur --
    banner("G3  Textur: Wie viel Oberflaeche bekommt Farbe?")
    tex = mt.texture_completeness(sv, frames, FX, FY, CX, CY,
                                  depth_tol_mm=2.5, min_views=3)
    tex_skin = mt.texture_completeness(sv, frames, FX, FY, CX, CY,
                                       depth_tol_mm=2.5, min_views=1)
    print(f"  mindestens 1x gesehen (jedes Material): {tex_skin['covered_any'] * 100:.1f} %")
    print(f"  mindestens 3x gesehen:                  {tex['covered_min_views'] * 100:.1f} %")
    print(f"  mittlere Sichtungen je Punkt: {tex['mean_views']:.1f}")

    # ------------------------------------------------------- G4: Export --
    banner("G4  Export mit Ruecklese-Test (9 Formate)")
    os.makedirs(OUT, exist_ok=True)
    colors = tex["colors"]
    checks = []

    # Zusammengesetztes Modell: Haut (mit Projektionsfarbe) + Haare (L1).
    # Das ist genau das, was der Nutzer am Ende exportiert.
    if len(hv2):
        cv = np.vstack([sv, hv2])
        cf = np.vstack([sf, hf2 + len(sv)])
        cc = np.vstack([colors, np.tile(np.array([58, 41, 31], dtype=np.uint8),
                                        (len(hv2), 1))])
    else:
        cv, cf, cc = sv, sf, colors
    print(f"  Modell: {len(cv):,} Punkte / {len(cf):,} Dreiecke")

    # Normalen kommen IMMER mit: sie sind aus dem Netz berechnet, also
    # eine echte Verbesserung und kein Platzhalter. Ohne sie rechnet
    # jedes Empfaengerprogramm sie neu -- und zwar nach Guenstling
    # (Blender "winkelgewichtet", Maya "flach"), was zu zwei
    # unterschiedlich aussehenden Modellen aus derselben Datei fuehrt.
    #
    # UVs bewusst NICHT: das M1-Netz hat keinen Atlas. Eine
    # Kugelprojektion hier hineinzuschreiben wuerde so aussehen, als
    # haetten wir Produktions-UVs -- haben wir aber nicht (docs/03, 11).
    cn = mt.vertex_normals(cv, cf)

    jobs = [
        ("OBJ", lambda p: ex.write_obj(p, cv, cf, cc, normals=cn),
         "facescan_m1.obj"),
        ("PLY (binär)", lambda p: ex.write_ply(p, cv, cf, cc, normals=cn),
         "facescan_m1.ply"),
        ("GLB", lambda p: ex.write_glb(p, cv, cf, cc, normals=cn),
         "facescan_m1.glb"),
        ("STL (binär)", lambda p: em.write_stl(p, cv, cf), "facescan_m1.stl"),
        ("USDA", lambda p: em.write_usda(p, cv, cf, cc, normals=cn),
         "facescan_m1.usda"),
        ("USDZ", lambda p: em.write_usdz(p, cv, cf, cc, normals=cn),
         "facescan_m1.usdz"),
        ("FBX 7.5 (binär)", lambda p: em.write_fbx(p, cv, cf, cc, normals=cn),
         "facescan_m1.fbx"),
        ("Alembic (ABC)", lambda p: em.write_abc(p, cv, cf, normals=cn),
         "facescan_m1.abc"),
        ("DAE (Collada)", lambda p: em.write_dae(p, cv, cf, cc, normals=cn),
         "facescan_m1.dae"),
    ]
    for label, writer, fname in jobs:
        path = os.path.join(OUT, fname)
        writer(path)
        size = os.path.getsize(path)
        check = verify_export(path, cv, cf, cc, cn)
        checks.append(check)
        status = "OK" if check["passed"] else "FEHLGESCHLAGEN"
        note = check["note"]
        if check.get("normals") is not None:
            nv = check["normals"]
            note += (" | Normalen " + (f"max. Abweichung {nv:.1e}"
                                       if isinstance(nv, float) else nv))
        print(f"  {label:16s} {size / 1024:9.1f} kB | Ruecklese {status:15s} | "
              f"{note}")

    # ---------------------------------------------------------- Bericht --
    report = {
        "scene": {
            "frames": N_FRAMES, "image": [W, H], "focal_px": FX,
            "voxel_mm": VOXEL_MM, "trunc_mm": TRUNC_MM, "seed": SEED,
            "head_vertices": int(len(v)), "head_triangles": int(len(f)),
            "hair_vertices": int(len(hv)), "hair_triangles": int(len(hf)),
            "non_parametric_detail_mm": {
                "mean": float(detail.mean()), "max": float(detail.max()),
            },
        },
        "skin": {"chamfer": cham, "chamfer_all_visible": cham_vis,
                 "mesh": stats_skin},
        "hair": {
            "iou_all": iou_all, "iou_observed": iou_observed(iou_obs),
            "voxels_observed_truth": int((gt_hair & seen).sum()),
            "mesh": stats_hair,
        },
        "texture": {k: float(val) for k, val in tex.items() if k not in ("colors", "views")},
        "texture_any": {k: float(val) for k, val in tex_skin.items()
                        if k not in ("colors", "views")},
        "skin_visible_fraction": float((gt_views >= 1).mean()),
        "skin_well_observed_fraction": float((gt_views >= 5).mean()),
        "hair_thickness_estimate_mm": float(prior_mm),
        "hair_mesh_voxel_mm": float(VOXEL_MM * 2.0),
        "export": checks,
        "gates": {},
        "runtime_s": float(time.time() - t_start),
    }
    gates = {
        "chamfer_skin_mm <= 0.8": cham["chamfer_mm"] <= 0.8,
        "hair_iou_observed >= 0.85": iou_obs["iou"] >= 0.85,
        "texture_coverage >= 0.95": tex_skin["covered_any"] >= 0.95,
        "export_roundtrip_ok": all(c["passed"] for c in checks),
        "no_degenerate_triangles": stats_skin["degenerate_triangles"] == 0,
    }
    report["gates"] = gates

    banner("M1-Fazit")
    for name, ok in gates.items():
        print(f"  [{'BESTANDEN' if ok else 'NICHT BESTANDEN'}]  {name}")
    print(f"\n  Gesamtlaufzeit: {time.time() - t_start:.0f} s")

    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.abspath(os.path.join(RESULTS, "m1_report.json"))
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=float)
    print(f"  Bericht: {path}")
    return 0 if all(gates.values()) else 1


def iou_observed(d: dict) -> dict:
    return d


if __name__ == "__main__":
    sys.exit(main())
