#!/usr/bin/env python3
"""Stufe 5.5 + 8: globaler Textur-Bake und die LOD-Kette.

Hier passiert das, was den Unterschied zwischen "Blocken" und einer
glatten Textur ausmacht (docs/03, 6.2 und 10):

  * Der Atlas kommt vom MASTER, nicht von der jeweiligen LOD-Stufe.
    Deshalb teilen alle vier Stufen EINE Textur -- vier Texturen zu
    backen waere vierfacher Speicher fuer denselben Inhalt.

  * Gebacken wird pro TEXEL, nicht pro Vertex: fuer jedes Texel wird
    der 3D-Punkt bestimmt und ALLE Kameras gefragt, die ihn sehen. Die
    Gewichte sind stetig (cos^2), also gibt es keine
    Zustaendigkeitsgrenze zwischen zwei Kameras mehr, die man nachher
    weichzeichnen muesste.

  * Die LOD-Kette traegt die UVs MIT (meshopt.quadric_decimate mit
    uv_weight). Ohne das waere der Atlas nach der ersten Stufe Muell,
    weil Kanten ueber Chart-Abstaende hinweg zusammengefasst wuerden.

Aufruf:
    /tmp/qrenv/bin/python prototype/reference/tools/build_lod.py
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

from facescan_ref import headmesh as hm            # noqa: E402
from facescan_ref import metrics as mt             # noqa: E402
from facescan_ref import meshopt as mo             # noqa: E402
from facescan_ref import bake                      # noqa: E402
from facescan_ref import export_mesh as ex         # noqa: E402
from facescan_ref import export_more as em         # noqa: E402
from facescan_ref.raster import Renderer, lambert  # noqa: E402

MESHES = os.path.abspath(os.path.join(HERE, "..", "meshes"))
RESULTS = os.path.abspath(os.path.join(HERE, "..", "results"))

W, H = 540, 960
FX = FY = 916.6
CX, CY = W / 2.0, H / 2.0
N_FRAMES = 16
SEED = 2026

ATLAS_RES = 2048
# USDZ mit binaerem Crate als Root-Layer (.usdc) statt Text (.usda).
# Apple-Geraete verlangen das: Reality Converter lehnt ein Paket mit
# Text-Root-Layer ab. Der Inhalt kommt weiter aus unserem USDA-Schreiber,
# nur die Serialisierung macht die USD-Bibliothek (export_more.usda_to_usdc).
USDZ_CRATE = True
LOD_TARGETS = (300_000, 80_000, 20_000, 6_000)
UV_WEIGHT = 4000.0        # Strafe dafuer, Kanten ueber Nahtabstaende zu falten
DILATE_PX = 600            # Lueckenfuellung: groesste Lücke ~820 px (Hinterkopf)
MIN_COS = 0.2            # Streifblick zulaessen: Textur gewinnt Flaeche, Genauigkeit verliert sie
BACK_TOL_MM = 4.0         # Punkt darf 4 mm HINTER der Messung liegen
FRONT_TOL_MM = 25.0       # ... aber 25 mm DAVOR (Visual-Hull-Haare)


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


def seam_energy(img: np.ndarray, covered: np.ndarray) -> dict:
    """Farbunterschiede zwischen benachbarten Texeln.

    Das ist die Zahl, die "Blocken" messbar macht: wo zwei
    Zustaendigkeitsbereiche aufeinandertreffen, springt die Farbe um
    viele Stufen.

    Ausgewiesen werden drei Zahlen, weil jede fuer sich irrefuehrend
    ist:
      * `sichtbare_spruenge` -- Anteil der Kanten mit mehr als 20/765
        Unterschied. 20 Stufen Rot+Gruen+Blau sind die Schwelle, ab der
        man bei normaler Bildschirmhelligkeit eine Kante SIEHT. Das ist
        die Zahl, die zaehlt.
      * `p999` -- das 99,9. Perzentil, also die schlimmsten 0,1 %.
      * `mittel` -- der Durchschnitt; niedrig heisst "glatt".
    """
    img = img.astype(np.int16)
    dh = np.abs(img[:, 1:] - img[:, :-1]).sum(axis=2)
    dv = np.abs(img[1:, :] - img[:-1, :]).sum(axis=2)
    ch = covered[:, 1:] & covered[:, :-1]
    cv = covered[1:, :] & covered[:-1, :]
    d = np.concatenate([dh[ch], dv[cv]])
    if len(d) == 0:
        return {"sichtbare_spruenge_pct": 0.0, "p999": 0.0, "mittel": 0.0}
    return {
        "sichtbare_spruenge_pct": float(100.0 * (d > 20).mean()),
        "p999": float(np.percentile(d, 99.9)),
        "mittel": float(d.mean()),
    }


def main() -> int:
    t_start = time.time()
    np.random.seed(SEED)

    st_path = os.path.join(MESHES, "master_state.npz")
    if not os.path.exists(st_path):
        print("FEHLT: %s -- bitte zuerst tools/build_master.py laufen lassen."
              % st_path)
        return 2
    st = np.load(st_path, allow_pickle=True)
    mv, mf, muv = st["v"], st["f"], st["uv"]
    print(f"Master: {len(mv):,} Punkte / {len(mf):,} Dreiecke, "
          f"Methode {str(st['method'][0])}, Charts {int(st['charts'][0])}")

    # ------------------------------------------------------------ Bilder --
    banner("Aufnahmen erneut erzeugen (gleicher Seed, also identisch)")
    t0 = time.time()
    head = hm.head_mesh(96, 144)
    hair_mesh = hm.hair_mesh(96, 144)
    poses = hm.orbit_poses(N_FRAMES, radius=520.0, yaw_deg=75.0, pitch_deg=9.0)
    frames = render_all(poses, head, hair_mesh, np.array([0.25, 0.55, 1.0]))
    print(f"  {len(frames)} Bilder in {time.time() - t0:.0f} s")

    # ------------------------------------------------------- LOD-Kette ---
    banner("LOD-Kette (Garland-Heckbert, UVs wandern mit)")
    cache = os.path.join(MESHES, "lod_state.npz")
    if os.path.exists(cache):
        # Der teuerste Schritt (1,46 Mio. -> 300 Tsd. Dreiecke, gut
        # vier Minuten) aendert sich nicht, wenn man nur den Bake
        # nachbessert. Also zwischenspeichern.
        c = np.load(cache)
        lod = [(c[f"v{i}"], c[f"f{i}"], None, c[f"u{i}"])
               for i in range(len(LOD_TARGETS)) if f"v{i}" in c.files]
        print("  aus %s geladen (%d Stufen)" % (os.path.basename(cache),
                                                len(lod)))
    else:
        lod = mo.lod_chain(mv, mf, targets=LOD_TARGETS, uv=muv,
                           uv_weight=UV_WEIGHT, verbose=True)
    # Umlaufrichtung heilen -- nicht wegen der Anzeige, sondern weil
    # `vertex_normals` aus der Umlaufrichtung gerechnet wird. Ein
    # gedrehtes Dreieck liefert eine nach innen zeigende Normale, und
    # damit faellt der Punkt beim Sichtbarkeitstest (cos > 0,35) durch.
    _lod = []
    for v, f, c, u in lod:
        v, f = mo.orient_mesh(v, f)
        _lod.append((v, f, c, u))
    lod = _lod
    for i, (v, f, _c, u) in enumerate(lod):
        print(f"  LOD{i}: {len(v):,} Punkte / {len(f):,} Dreiecke, "
              f"UV-Bereich {u.min():.4f}..{u.max():.4f}")
    sys.stdout.flush()

    # ------------------------------------------------------------- Bake --
    banner("Globaler Bake: %d² Textur, alle Kameras je Texel" % ATLAS_RES)
    v0, f0, _c0, u0 = lod[0]
    n0 = mt.vertex_normals(v0, f0)

    t0 = time.time()
    tri, bary = bake.rasterize_uv(u0, f0, ATLAS_RES)
    covered0 = tri >= 0
    print(f"  gerastert in {time.time() - t0:.1f} s: "
          f"{int(covered0.sum()):,} / {ATLAS_RES * ATLAS_RES:,} Texel belegt "
          f"({100.0 * covered0.mean():.1f} %)")

    iy, ix, P, N = bake.texel_geometry(tri, bary, v0, f0, n0)
    w_tex = bary[iy, ix].astype(np.float64)      # Gewichte je belegtem Texel
    t0 = time.time()
    res = bake.bake_texels(P, N, frames, FX, FY, CX, CY,
                           back_tol_mm=BACK_TOL_MM,
                           front_tol_mm=FRONT_TOL_MM, min_cos=MIN_COS)
    print(f"  {len(P):,} Texel gegen {len(frames)} Bilder in "
          f"{time.time() - t0:.1f} s")
    print(f"  beitragende Kameras je Texel: "
          f"Mittel {res['views'][res['seen']].mean():.1f}, "
          f"{100.0 * (res['views'][res['seen']] >= 3).mean():.1f} % mit >= 3")
    print(f"  ohne Farbe geblieben: "
          f"{100.0 * (~res['seen']).mean():.2f} % der belegten Texel")

    img = np.zeros((ATLAS_RES, ATLAS_RES, 3), dtype=np.uint8)
    img[iy, ix] = res["rgb"]
    seen_mask = np.zeros((ATLAS_RES, ATLAS_RES), dtype=bool)
    seen_mask[iy, ix] = res["seen"]

    # --- Vergleich: der alte Weg (pro Vertex gemittelt) im selben Atlas --
    old = mt.texture_completeness(v0, frames, FX, FY, CX, CY,
                                  depth_tol_mm=BACK_TOL_MM, min_views=1)
    # ACHTUNG: `bary` ist das ganze Bild (2048, 2048, 3). Wer es direkt
    # nimmt, rechnet mit 4 Millionen Zeilen statt mit den belegten
    # Texeln -- und indiziert anschliessend mit ix/iy in ein Array der
    # falschen Laenge.
    old_rgb = (old["colors"][f0[tri[iy, ix]]] * w_tex[:, :, None]).sum(axis=1)
    img_old = np.zeros((ATLAS_RES, ATLAS_RES, 3), dtype=np.uint8)
    img_old[iy, ix] = old_rgb.astype(np.uint8)

    t0 = time.time()
    real_frac = float(seen_mask.mean())
    img = bake.dilate(img, seen_mask, DILATE_PX)
    img_old = bake.dilate(img_old, seen_mask, DILATE_PX)
    still_empty = (img == 0).all(axis=2) & (~seen_mask)
    filled = np.ones((ATLAS_RES, ATLAS_RES), dtype=bool)
    print(f"  Luecken aufgeweitet ({DILATE_PX} px) in {time.time() - t0:.1f} s")
    print(f"  echte Farbe: {100.0 * real_frac:.1f} % der Atlasflaeche, "
          f"aufgefüllt: {100.0 * (1 - real_frac - still_empty.mean()):.1f} %, "
          f"leer geblieben: {100.0 * still_empty.mean():.1f} %")
    print("  -> Der gefuellte Anteil ist EXTRAPOLATION, keine Messung. Wo")
    print("     die 16 Aufnahmen nichts sahen (Hinterkopf, Haarunterseite),")
    print("     steht der Farbton des naechsten sichtbaren Texels.")

    e_new = seam_energy(img, filled)
    e_old = seam_energy(img_old, filled)
    # "Blocken" = Sprung zwischen benachbarten Texeln, 99. Perzentil.
    # 3 Stufen sind gerade noch als glatte Flaeche zu sehen, 25 Stufen
    # sind eine sichtbare Kante.
    print(f"  sichtbare Spruenge (>20/765): "
          f"pro Vertex {e_old['sichtbare_spruenge_pct']:.2f} %  ->  "
          f"gebacken {e_new['sichtbare_spruenge_pct']:.2f} %  "
          f"({(1 - e_new['sichtbare_spruenge_pct'] / max(e_old['sichtbare_spruenge_pct'], 1e-9)) * 100:.0f} % weniger)")
    print(f"  99,9. Perzentil: {e_old['p999']:.0f} -> {e_new['p999']:.0f} | "
          f"Mittel: {e_old['mittel']:.2f} -> {e_new['mittel']:.2f}")

    tex_path = os.path.join(MESHES, "texture_%d.png" % ATLAS_RES)
    mo.write_png(tex_path, img)
    print(f"  geschrieben: {os.path.basename(tex_path)} "
          f"({os.path.getsize(tex_path) / 1e6:.1f} MB)")
    with open(tex_path, "rb") as fh:
        png_bytes = fh.read()
    sys.stdout.flush()

    # ---------------------------------------------------------- Export ---
    banner("LOD-Export: GLB (mit Textur), OBJ (+mtl), USDZ")
    report = {"atlas": int(ATLAS_RES), "lod": [], "seam": {}}
    for i, (v, f, _c, u) in enumerate(lod):
        nn = mt.vertex_normals(v, f)
        base = f"head_lod{i}"
        jobs = [
            ("GLB", os.path.join(MESHES, base + ".glb"),
             lambda p, v=v, f=f, u=u, n=nn: ex.write_glb(
                 p, v, f, None, name="FaceScan_LOD%d" % i, normals=n, uv=u,
                 texture_png=png_bytes)),
            ("OBJ", os.path.join(MESHES, base + ".obj"),
             lambda p, v=v, f=f, u=u, n=nn: ex.write_obj(
                 p, v, f, None, name="FaceScan_LOD%d" % i, normals=n, uv=u,
                 texture="texture_%d.png" % ATLAS_RES)),
            ("USDZ", os.path.join(MESHES, base + ".usdz"),
             lambda p, v=v, f=f, u=u, n=nn: em.write_usdz(
                 p, v, f, None, name="FaceScan_LOD%d" % i, normals=n, uv=u,
                 texture=tex_path, crate=USDZ_CRATE)),
        ]
        sizes = {}
        for tag, path, fn in jobs:
            t0 = time.time()
            fn(path)
            sizes[tag] = os.path.getsize(path) / 1024.0
            print(f"  LOD{i} {tag:5s} {sizes[tag]:9.1f} kB "
                  f"({time.time() - t0:.1f} s)")
        sys.stdout.flush()

        # Referenz ist das MASTER-Netz, nicht die LOD darueber: gemessen
        # wird, wie weit jede Stufe vom Original abweicht. Wer Stufe gegen
        # Stufe misst, addiert die Fehler und behauptet am Ende, die
        # Kette sei schlechter als sie ist.
        dev = mt.surface_deviation(mv, mf, v, f, cell=4.0,
                                   max_ref_points=40_000)
        stl = mt.mesh_stats(v, f)
        report["lod"].append({
            "level": i, "faces": int(len(f)), "vertices": int(len(v)),
            "form_error_mm": dev["mean_mm"], "p95_mm": dev["p95_mm"],
            "max_mm": dev["max_mm"],
            "to_lod_mm": dev["to_lod_mm"], "from_lod_mm": dev["from_lod_mm"],
            "unresolved": int(dev["unresolved"]),
            "degenerate": int(stl["degenerate_triangles"]),
            "surface_cm2": stl["surface_cm2"], "files_kb": sizes,
        })
        print(f"  LOD{i} Formfehler {dev['mean_mm']:.3f} mm "
              f"(p95 {dev['p95_mm']:.3f}, max {dev['max_mm']:.2f}), "
              f"entartete Dreiecke: {stl['degenerate_triangles']}")
        sys.stdout.flush()

    report["seam"] = {"per_vertex": e_old, "baked": e_new}
    report["texels"] = {
        "covered": int(covered0.sum()),
        "total": int(ATLAS_RES * ATLAS_RES),
        "mean_views": float(res["views"][res["seen"]].mean()),
        "uncolored_pct": float(100.0 * (~res["seen"]).mean()),
    }
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, "m2b_lod_report.json"), "w",
              encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    np.savez_compressed(os.path.join(MESHES, "lod_state.npz"),
                        **{f"v{i}": lod[i][0] for i in range(len(lod))},
                        **{f"f{i}": lod[i][1] for i in range(len(lod))},
                        **{f"u{i}": lod[i][3] for i in range(len(lod))})

    print(f"\nFertig in {time.time() - t_start:.0f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
