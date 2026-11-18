#!/usr/bin/env python3
"""M0-Machbarkeitsnachweis.

Beantwortet drei Fragen mit Zahlen statt Bauchgefuehl:

  F1  Bekommen wir aus 2D-Landmarks + Kamera-Intrinsics eine metrische
      Kamerapose -- ohne ARCore, ohne SLAM, ohne Tiefensensor?
  F2  Laesst sich eine geteilte Identitaet (Form eines Menschen) aus mehreren
      Bildern stabil schaetzen, waehrend Mimik und Pose pro Bild variieren?
  F3  Wie empfindlich ist das Ganze gegen das, was auf echten Handys passiert:
      Rauschen, Ausreisser, teilweise Verdeckung, weites Sichtfeld?

Aufruf:  python3 prototype/reference/python/run_m0.py
"""
from __future__ import annotations
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from facescan_ref.synthetic import generate_scene          # noqa: E402
from facescan_ref.fit import fit_multiframe, evaluate, _shape  # noqa: E402
from facescan_ref.pose import estimate_pose               # noqa: E402
from facescan_ref.math3d import rotation_error_deg, project_points  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "..", "fixtures")
RESULTS = os.path.join(HERE, "..", "results")


def banner(text: str) -> None:
    print("\n" + "=" * 74)
    print(text)
    print("=" * 74)


def question_1(scene: dict) -> dict:
    """F1: Pose nur aus Landmarks (POSIT-Init + robuster Gauss-Newton)."""
    banner("F1  Kamerapose ohne ARCore (POSIT-Init + Huber-Gauss-Newton)")
    k, base = scene["K"], scene["base"]
    rot, tra, rms = [], [], []
    for fi, fr in enumerate(scene["frames"]):
        m = fr["visibility"].reshape(-1) > 0.5
        # Referenz = das mittlere Gesicht (wir kennen die Identitaet hier noch nicht)
        est = estimate_pose(k, base[m], fr["points2d"][m])
        rot.append(rotation_error_deg(est["R"], fr["R"]))
        tra.append(float(np.linalg.norm(est["t"] - fr["t"])))
        rms.append(est["rms"])
        print(f"  Frame {fi}: Rotationsfehler {rot[-1]:6.3f} deg | "
              f"Translationsfehler {tra[-1]:6.2f} mm | RMS {rms[-1]:5.2f} px | "
              f"Inlier {est['inlier_ratio']*100:5.1f} %")
    out = {
        "rot_deg_mean": float(np.mean(rot)), "rot_deg_max": float(np.max(rot)),
        "trans_mm_mean": float(np.mean(tra)), "trans_mm_max": float(np.max(tra)),
        "rms_px_mean": float(np.mean(rms)),
    }
    print(f"  --> Mittel: {out['rot_deg_mean']:.3f} deg, {out['trans_mm_mean']:.2f} mm, "
          f"{out['rms_px_mean']:.2f} px")
    return out


def question_2(scene: dict) -> dict:
    """F2: Multi-Frame-Fit (geteilte Identitaet, pro Frame Pose + Mimik)."""
    banner("F2  Multi-Frame-3DMM-Fit (Identitaet geteilt, Pose/Mimik pro Frame)")
    result = fit_multiframe(scene, verbose=True)
    metrics = evaluate(scene, result)
    print("\n  Kennzahl                         Wert")
    print("  " + "-" * 48)
    labels = [
        ("Reprojektion Start (px)", "repro_rms_first_px"),
        ("Reprojektion Ende (px)", "repro_rms_final_px"),
        ("Rotationsfehler Mittel (deg)", "rot_err_deg_mean"),
        ("Rotationsfehler Max (deg)", "rot_err_deg_max"),
        ("Translationsfehler Mittel (mm)", "trans_err_mm_mean"),
        ("Translationsfehler Max (mm)", "trans_err_mm_max"),
        ("Identitaet: Korrelation", "alpha_corr"),
        ("Identitaet: RMSE", "alpha_rmse"),
        ("Mimik: RMSE", "beta_rmse"),
        ("Geometriefehler Kopf (mm)", "geometry_err_mm_mean"),
        ("Reprojektion Inlier (px)", "repro_inlier_rms_px"),
    ]
    for label, key in labels:
        print(f"  {label:<32} {metrics[key]:>10.4f}")
    return metrics


def question_3() -> list[dict]:
    """F3: Robustheit gegen reale Stoerungen."""
    banner("F3  Robustheit gegen Rauschen, Ausreisser, Verdeckung")
    rows = []
    scenarios = [
        ("Labor (0.5 px, 0 %)", dict(noise_px=0.5, outlier_ratio=0.00, occlusion_ratio=0.00)),
        ("Gut  (1.0 px, 5 %)", dict(noise_px=1.0, outlier_ratio=0.05, occlusion_ratio=0.08)),
        ("Mittel (2.0 px, 10 %)", dict(noise_px=2.0, outlier_ratio=0.10, occlusion_ratio=0.15)),
        ("Schlecht (4.0 px, 15 %)", dict(noise_px=4.0, outlier_ratio=0.15, occlusion_ratio=0.25)),
    ]
    print(f"  {'Szenario':<24}{'Rot (deg)':>12}{'Trans (mm)':>12}{'Geom (mm)':>12}{'InlierRMS':>11}")
    print("  " + "-" * 71)
    for name, kw in scenarios:
        sc = generate_scene(n_frames=8, n_points=120, seed=2026, **kw)
        res = fit_multiframe(sc)
        m = evaluate(sc, res)
        rows.append({"scenario": name, **{k: m[k] for k in
                     ("rot_err_deg_mean", "trans_err_mm_mean", "geometry_err_mm_mean",
                      "repro_inlier_rms_px")}})
        print(f"  {name:<24}{m['rot_err_deg_mean']:>12.3f}{m['trans_err_mm_mean']:>12.2f}"
              f"{m['geometry_err_mm_mean']:>12.2f}{m['repro_inlier_rms_px']:>11.2f}")
    return rows


def question_4() -> list[dict]:
    """F4: Wie viele Aufnahmen braucht der Assistent wirklich?

    Beantwortet direkt die Produktfrage 'Quick/Standard/Pro': bringt mehr
    Aufnahmezeit ueberhaupt etwas -- und wo ist der Knick?
    """
    banner("F4  Genauigkeit vs. Anzahl der Aufnahmen (Basis fuer Quick/Standard/Pro)")
    rows = []
    print(f"  {'Frames':>8}{'Rot (deg)':>12}{'Trans (mm)':>12}{'Geom (mm)':>12}"
          f"{'Ident.-Korr.':>14}{'InlierRMS':>11}")
    print("  " + "-" * 69)
    for nf in (4, 8, 12, 16, 24):
        sc = generate_scene(n_frames=nf, n_points=120, seed=2026)
        res = fit_multiframe(sc)
        m = evaluate(sc, res)
        rows.append({"frames": nf, **{k: m[k] for k in
                     ("rot_err_deg_mean", "trans_err_mm_mean", "geometry_err_mm_mean",
                      "alpha_corr", "repro_inlier_rms_px")}})
        print(f"  {nf:>8}{m['rot_err_deg_mean']:>12.4f}{m['trans_err_mm_mean']:>12.3f}"
              f"{m['geometry_err_mm_mean']:>12.3f}{m['alpha_corr']:>14.3f}"
              f"{m['repro_inlier_rms_px']:>11.2f}")
    print("\n  -> Mehr Bilder verbessern vor allem die IDENTITAET (Formtreue), kaum die Pose.")
    print("     Das ist die Begruendung fuer 16 (Quick) / 48 (Standard) / 120 (Pro) Frames.")
    return rows


def write_fixtures(scene: dict, metrics: dict) -> str:
    """Schreibt Gold-Fixtures (JSON) fuer die Kotlin-Unit-Tests."""
    os.makedirs(FIXTURES, exist_ok=True)
    path = os.path.abspath(os.path.join(FIXTURES, "m0_fixtures.json"))
    data = {
        "schema": 1,
        "note": "Synthetische Ground Truth. Erzeugt von run_m0.py (seed 2026).",
        "units": "mm",
        "intrinsics": scene["K"].tolist(),
        "base": np.round(scene["base"], 5).tolist(),
        "A_id": np.round(scene["A_id"], 6).tolist(),
        "A_exp": np.round(scene["A_exp"], 6).tolist(),
        "alpha_true": np.round(scene["alpha_true"], 6).tolist(),
        "beta_true": np.round(scene["beta_true"], 6).tolist(),
        "frames": [
            {
                "R_gt": np.round(fr["R"], 8).tolist(),
                "t_gt": np.round(fr["t"], 6).tolist(),
                "visibility": fr["visibility"].tolist(),
                "points2d": np.round(fr["points2d"], 4).tolist(),
                # Ausreisser-Maske: nur damit die Tests die EHRliche Kennzahl
                # (Inlier-RMS) nachrechnen koennen. Sie gehoert nicht zum
                # Verfahren -- der Fit bekommt sie nicht zu sehen.
                "outliers": fr.get("outliers", np.zeros(fr["visibility"].shape[0])).tolist(),
            }
            for fr in scene["frames"]
        ],
        "expected": {k: round(float(v), 6) for k, v in metrics.items()},
        "tolerances": {
            "rot_err_deg_mean": 1.0,
            "trans_err_mm_mean": 15.0,
            "repro_inlier_rms_px": 2.0,
            "geometry_err_mm_mean": 5.0,
        },
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return path


def write_kotlin_fixtures(scene: dict, metrics: dict, pose_metrics: dict) -> str:
    """Erzeugt eine Kotlin-Fixture-Datei fuer reine JVM-Unit-Tests.

    Warum Kotlin statt JSON? Damit die Unit-Tests ohne Robolectric und ohne
    JSON-Parser auskommen (org.json ist auf der JVM nicht enthalten).
    """
    out_dir = os.path.abspath(os.path.join(HERE, "..", "..", "android", "app", "src", "main",
                                           "java", "com", "andrexthedev", "facescan", "geometry"))
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "M0Fixtures.kt")

    def num(v: float) -> str:
        """Kotlin-sichere Zahl: immer mit Punkt oder Exponent.

        Ohne das wuerde aus 1.0 schlicht "1" -- ein Int-Literal. Kotlin
        erlaubt das zwar an einer Double-Position, aber wir wollen uns nicht
        darauf verlassen, dass jeder Leser das weiss.
        """
        s = f"{v:.6g}"
        if "." in s or "e" in s or "inf" in s or "nan" in s:
            return s
        return s + ".0"

    def arr(name: str, values: np.ndarray, per_line: int = 8, indent: str = "        ") -> str:
        flat = np.asarray(values, dtype=float).reshape(-1)
        chunks = []
        for i in range(0, len(flat), per_line):
            chunks.append(", ".join(num(v) for v in flat[i:i + per_line]))
        body = (",\n" + indent).join(chunks)
        return f"    val {name} = doubleArrayOf(\n{indent}{body}\n    )\n"

    n = scene["base"].shape[0]
    k_id = scene["A_id"].shape[1]
    k_exp = scene["A_exp"].shape[1]
    f = len(scene["frames"])
    k = scene["K"]

    src = []
    src.append("// GENERATED by prototype/reference/python/run_m0.py -- DO NOT EDIT\n")
    src.append("// Synthetische Ground Truth fuer die M0-Unit-Tests (Einheiten: mm, px).\n")
    src.append("package com.andrexthedev.facescan.geometry\n\n")
    src.append("internal object M0Fixtures {\n")
    src.append(f"    const val N_POINTS = {n}\n")
    src.append(f"    const val K_IDENTITY = {k_id}\n")
    src.append(f"    const val K_EXPRESSION = {k_exp}\n")
    src.append(f"    const val N_FRAMES = {f}\n\n")
    src.append(arr("intrinsics", np.array([k[0, 0], k[1, 1], k[0, 2], k[1, 2]]), per_line=4))
    src.append("\n")
    src.append(arr("baseVertices", scene["base"]))
    src.append("\n")
    src.append(arr("identityBasis", scene["A_id"]))
    src.append("\n")
    src.append(arr("expressionBasis", scene["A_exp"]))
    src.append("\n")
    src.append(arr("alphaTrue", scene["alpha_true"], per_line=8))
    src.append("\n")
    # Mimik von Frame 0: wird gebraucht, um den Geometriefehler genauso zu
    # berechnen wie die Referenz (wahre Form von Frame 0 vs. geschaetzte).
    src.append("    // Mimik (Ausdruck) von Frame 0 -- nur fuer die Auswertung\n")
    src.append(arr("betaTrueFrame0", scene["beta_true"][0], per_line=8))
    src.append("\n")
    for fi, fr in enumerate(scene["frames"]):
        src.append(f"    // ---- Frame {fi} ----\n")
        src.append(arr(f"rotationTrue{fi}", fr["R"], per_line=3))
        src.append(arr(f"translationTrue{fi}", fr["t"], per_line=3))
        src.append(arr(f"landmarks{fi}", fr["points2d"], per_line=8))
        src.append(arr(f"visibility{fi}", fr["visibility"], per_line=16))
        # Die Ausreisser-Maske dient AUSSCHLIESSLICH dem Nachrechnen der
        # ehrlichen Kennzahl (Inlier-RMS) im Test. Der Fit bekommt sie nicht.
        src.append(arr(f"outlierMask{fi}",
                       fr.get("outliers", np.zeros(fr["visibility"].shape[0])), per_line=16))
        src.append("\n")
    # ---- Erwartete Ergebnisse (aus dem Python-Referenzlauf) ----
    #
    # ZWEI Gruppen, weil der Report zwei Fragen beantwortet:
    #   * question_1: Pose je Frame, direkt aus den Landmarks  (F1)
    #   * question_2: gemeinsamer Multi-Frame-Fit              (F2)
    # F1 und F2 sind NICHT vertauschbar -- F2 ist deutlich genauer, weil die
    # Identitaet ueber alle Frames geteilt wird. Genau diese Verwechslung hat
    # einen Test einmal gegen die falsche Zahl pruefen lassen. Deshalb stehen
    # die Gruppen hier getrennt und benannt, statt unter einem Namen.
    src.append("    // ---- Erwartete Ergebnisse (aus dem Python-Referenzlauf) ----\n")
    src.append("    //\n")
    src.append("    // F2: gemeinsamer Multi-Frame-Fit -> ModelFitterTest (F1-Werte\n")
    src.append("    // sind das NICHT, siehe unten).\n")
    for name, key in [("expectedRotDegMean", "rot_err_deg_mean"),
                      ("expectedTransMmMean", "trans_err_mm_mean"),
                      ("expectedGeometryMm", "geometry_err_mm_mean"),
                      ("expectedInlierRmsPx", "repro_inlier_rms_px"),
                      ("expectedReproFinalPx", "repro_rms_final_px")]:
        src.append(f"    const val {name} = {float(metrics[key]):.6f}\n")
    src.append("\n")
    src.append("    // F1: Pose je Frame einzeln, ohne Kenntnis der Identitaet\n")
    src.append("    // -> PoseEstimatorTest. Groesser als F2, das ist kein Fehler,\n")
    src.append("    // sondern der Preis dafuer, dass die Identitaet noch fehlt.\n")
    for name, key in [("expectedPoseOnlyRotDegMean", "rot_deg_mean"),
                      ("expectedPoseOnlyRotDegMax", "rot_deg_max"),
                      ("expectedPoseOnlyTransMmMean", "trans_mm_mean"),
                      ("expectedPoseOnlyTransMmMax", "trans_mm_max")]:
        src.append(f"    const val {name} = {float(pose_metrics[key]):.6f}\n")
    src.append("}\n")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("".join(src))
    return path


def main() -> int:
    scene = generate_scene(n_frames=8, n_points=120, seed=2026,
                           noise_px=1.0, outlier_ratio=0.05, occlusion_ratio=0.08)
    m1 = question_1(scene)
    m2 = question_2(scene)
    m3 = question_3()
    m4 = question_4()
    path = write_fixtures(scene, m2)
    kpath = write_kotlin_fixtures(scene, m2, m1)

    os.makedirs(RESULTS, exist_ok=True)
    report = {"pose_only": m1, "multiframe": m2, "robustness": m3, "frames_sweep": m4}
    with open(os.path.join(RESULTS, "m0_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    banner("M0-Fazit")
    ok_rot = m2["rot_err_deg_mean"] < 1.0
    ok_tra = m2["trans_err_mm_mean"] < 15.0
    ok_geo = m2["geometry_err_mm_mean"] < 5.0
    ok_rep = m2["repro_inlier_rms_px"] < 2.0
    for label, ok in [("Rotation < 1.0 deg", ok_rot), ("Translation < 15 mm", ok_tra),
                      ("Geometrie < 5 mm", ok_geo), ("Reprojektion < 2 px", ok_rep)]:
        print(f"  [{'BESTANDEN' if ok else 'OFFEN    '}]  {label}")
    print(f"\n  Fixtures JSON:   {path}")
    print(f"  Fixtures Kotlin: {kpath}")
    print(f"  Report:   {os.path.abspath(os.path.join(RESULTS, 'm0_report.json'))}")
    return 0 if (ok_rot and ok_tra and ok_geo and ok_rep) else 1


if __name__ == "__main__":
    raise SystemExit(main())
