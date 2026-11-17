"""Baut den Rig: Gelenke, Hautgewichte, DAE mit Skin und BVH mit Skelett. (M3)

Aufruf::

    python3 python/build_rig.py            # aus prototype/reference

Was es tut, in dieser Reihenfolge:

  1. Kopf-Rahmen bestimmen (oben, Blickrichtung, Kopfmitte, Massstab) aus dem
     dichten Anzeigenetz LOD0 -- je mehr Punkte, desto sicherer der Fit.
  2. Skelett und Hautgewichte fuer das Anzeigenetz LOD1 bauen. LOD1 deshalb,
     weil die fertige Collada-Datei sonst 70 MB statt 10 MB hat; der Rahmen
     kommt trotzdem vom dichten Netz.
  3. Schreiben: ``meshes/facescan_rig.dae`` (mit ``library_controllers``),
     ``meshes/facescan_rig.bvh`` (Skelett + Bewegung) und den Bericht
     ``results/rig_report.json``.
  4. Alles gegen die bekannte Wahrheit pruefen: Das synthetische Kopfmodell
     liegt im Ursprung, unverdreht, im Massstab 1. Wer den Rahmen richtig
     bestimmt hat, muss das zurueckbekommen.

Der Bericht enthaelt bewusst auch die GEGENPROBEN (zweite, unabhaengige
Schaetzung je Achse). Ein Rig, das nur aus einer Quelle stammt, kann still
falsch liegen.
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from facescan_ref import export_mesh as ex           # noqa: E402
from facescan_ref import export_more as em          # noqa: E402
from facescan_ref import headmesh as hm             # noqa: E402
from facescan_ref import rig                        # noqa: E402

MESHES = os.path.join(HERE, "..", "meshes")
RESULTS = os.path.join(HERE, "..", "results")


def main() -> int:
    t0 = time.time()
    os.makedirs(RESULTS, exist_ok=True)
    z = np.load(os.path.join(MESHES, "lod_state.npz"))
    v_dicht, f_dicht = z["v0"], z["f0"]        # Rahmen: dicht
    v, f = z["v1"], z["f1"]                    # Rig: Anzeigenetz LOD1

    print("Rahmen bestimmen (aus %d Punkten) ..." % len(v_dicht))
    fit = rig.estimate_frame(v_dicht, f_dicht, verbose=True)
    print("  %.1f s" % (time.time() - t0))

    print("Gegenproben ...")
    rep = rig.frame_report(fit, v_dicht, f_dicht)
    for k, wert in rep.items():
        print("  %-38s %s" % (k, round(wert, 3) if isinstance(wert, float) else wert))

    lm = rig.landmark_positions(fit.frame)
    sk = rig.build_skeleton(lm, fit.frame, v)
    print("\nGelenke:")
    for j in sk.joints:
        print("  %-9s Elter %-9s %s" % (j.name, str(j.parent), np.round(j.position, 1)))

    print("\nHautgewichte (%d Punkte, %d Dreiecke) ..." % (len(v), len(f)))
    t1 = time.time()
    idx, wts = rig.skin_weights(v, f, sk, fit.frame, smooth_iters=40)
    print("  %.1f s" % (time.time() - t1))

    # --- Wahrheitspruefung: das Modell liegt im Ursprung, unverdreht -----
    print("\nAbweichung von der Wahrheit (Modell im Ursprung, Massstab 1, Blick +z):")
    abw = {}
    for name, d in (("nase", hm.DIR_NOSE), ("kinn", hm.DIR_CHIN), ("mund", hm.DIR_MOUTH),
                    ("auge_l", hm.DIR_EYE_L), ("auge_r", hm.DIR_EYE_R),
                    ("ohr_l", hm.DIR_EAR_L), ("ohr_r", hm.DIR_EAR_R)):
        dn = d / np.linalg.norm(d)
        soll = float(hm.head_radius(dn)) * dn
        abw[name] = float(np.linalg.norm(lm[name] - soll))
    abw["scheitel"] = float(np.linalg.norm(lm["scheitel"] - np.array([0.0, hm.RY, 0.0])))
    for k, wert in abw.items():
        print("  %-9s %.2f mm" % (k, wert))
    print("  Kopfmitte %.2f mm, Massstab %.4f" % (
        float(np.linalg.norm(fit.frame.center)), fit.frame.scale))

    print("\nMimik-Blendshapes ...")
    deltas, bs_namen = rig.blendshape_deltas(v, fit.frame)
    for d, n in zip(deltas, bs_namen):
        betr = np.linalg.norm(d, axis=1)
        sel = betr > 0.2
        print("  %-12s max %4.1f mm, wirkt auf %5d Punkte (Schwerpunkt y %4.0f, z %4.0f)"
              % (n, betr.max(), int(sel.sum()),
                 float(v[sel, 1].mean()) if sel.sum() else 0.0,
                 float(v[sel, 2].mean()) if sel.sum() else 0.0))

    # --- schreiben -------------------------------------------------------
    skin = dict(joints=sk.names,
                parents=[sk.parent_index(i) for i in range(len(sk.joints))],
                positions=sk.positions(), weights=(idx, wts))
    dae = em.write_dae(os.path.join(MESHES, "facescan_rig.dae"), v, f,
                       name="FaceScanRig", skin=skin)
    print("\nDAE  %-34s %6.1f MB" % (os.path.basename(dae),
                                     os.path.getsize(dae) / 1e6))

    joints = rig.skeleton_to_bvh(sk, fit.frame)
    vals = rig.animation_values(sk, n_frames=120, fps=30.0)
    bvh = em.write_bvh(os.path.join(MESHES, "facescan_rig.bvh"), joints, vals, 1 / 30.0)
    print("BVH  %-34s %6.1f kB" % (os.path.basename(bvh),
                                   os.path.getsize(bvh) / 1e3))

    # Mimik: GLB mit Morph-Zielen (Einheit Meter, deshalb /1000)
    glb = ex.write_glb(os.path.join(MESHES, "facescan_rig.glb"), v / 1000.0, f,
                       name="FaceScanRig",
                       targets=[d / 1000.0 for d in deltas],
                       target_names=bs_namen)
    print("GLB  %-34s %6.1f MB (mit %d Morph-Zielen)"
          % (os.path.basename(glb), os.path.getsize(glb) / 1e6, len(deltas)))
    np.savez_compressed(os.path.join(MESHES, "facescan_blendshapes.npz"),
                        **{n: d for n, d in zip(bs_namen, deltas)})
    with open(os.path.join(RESULTS, "blendshape_names.json"), "w") as fh:
        json.dump({"namen": bs_namen, "einheit": "mm",
                   "amplitude_mm": 5.0,
                   "hinweis": "ARKit-Benennung; nur die Ausdruecke, zu denen "
                              "das 3DMM eine Richtung besitzt."}, fh, indent=2)

    # --- zuruecklesen, was wir geschrieben haben -------------------------
    dae_gelesen = em.read_dae(dae)
    bvh_gelesen = em.read_bvh(bvh)

    n_j = len(sk.joints)
    W = np.zeros((len(v), n_j))
    for k in range(wts.shape[1]):
        W[np.arange(len(v)), idx[:, k]] += wts[:, k]
    a, b = rig._vertex_neighbours(f, len(v))
    bericht = {
        "dauer_s": round(time.time() - t0, 1),
        "netz": {"punkte": int(len(v)), "dreiecke": int(len(f)),
                 "quelle": "lod_state.npz v1/f1"},
        "rahmen": {
            "kopfmitte_mm": [round(float(x), 3) for x in fit.frame.center],
            "massstab": round(float(fit.frame.scale), 5),
            "oben": [round(float(x), 4) for x in fit.frame.R[:, 1]],
            "vorn": [round(float(x), 4) for x in fit.frame.R[:, 2]],
            "restfehler_median_mm": round(float(fit.residual_mm), 3),
            "restfehler_p90_mm": round(float(fit.residual_p90_mm), 3),
            "gesichtspunkte": int(fit.n_used),
        },
        "gegenproben": {k: (round(v_, 4) if isinstance(v_, float) else v_)
                        for k, v_ in rep.items()},
        "wahrheit_abweichung_mm": {k: round(v_, 3) for k, v_ in abw.items()},
        "gelenke": [{"name": j.name, "elter": j.parent,
                     "position_mm": [round(float(x), 2) for x in j.position]}
                    for j in sk.joints],
        "gewichte": {
            "summe_min": round(float(wts.sum(1).min()), 6),
            "summe_max": round(float(wts.sum(1).max()), 6),
            "anteil_prozent": {n: round(100 * float(W[:, i].sum()) / len(v), 2)
                               for i, n in enumerate(sk.names)},
            "fuehrend_bei_punkten": {n: int((idx[:, 0] == i).sum())
                                     for i, n in enumerate(sk.names)},
            "groesster_sprung_nachbar": round(float(np.abs(W[a] - W[b]).max()), 4),
        },
        "blendshapes": {
            "namen": bs_namen,
            "amplitude_mm": 5.0,
            "max_mm": {n: round(float(np.linalg.norm(d, axis=1).max()), 2)
                       for n, d in zip(bs_namen, deltas)},
        },
        "dateien": {
            "glb": os.path.basename(glb),
            "glb_morph_ziele": len(deltas),
            "dae": os.path.basename(dae),
            "dae_mb": round(os.path.getsize(dae) / 1e6, 2),
            "dae_gelesen": dae_gelesen,
            "bvh": os.path.basename(bvh),
            "bvh_frames": bvh_gelesen["frames_read"],
            "bvh_frames_deklariert": bvh_gelesen["frames_declared"],
            "bvh_kanaele": len(bvh_gelesen["channels"]),
            "bvh_stimmig": bool(bvh_gelesen["consistent"]),
        },
    }
    with open(os.path.join(RESULTS, "rig_report.json"), "w") as fh:
        json.dump(bericht, fh, indent=2, sort_keys=True)
    print("\nBericht: results/rig_report.json")
    print("DAE gelesen: %s" % dae_gelesen)
    print("BVH: %d Frames (%d deklariert), %d Kanaele, stimmig %s"
          % (bvh_gelesen["frames_read"], bvh_gelesen["frames_declared"],
             len(bvh_gelesen["channels"]), bvh_gelesen["consistent"]))
    print("\nfertig in %.1f s" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
