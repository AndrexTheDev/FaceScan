#!/usr/bin/env python3
"""Stufe 6.3: das Drucknetz vereinfachen (docs/05, 12.2).

775 k Dreiecke (hohl: 1,19 M) braucht kein Drucker -- ein Slicer wird
damit nicht fertig, und kein Mensch sieht den Unterschied. Dieses Werk-
zeug sucht die gröbste Fassung, die eine **Formfehlergrenze** einhält --
nicht die, die eine bestimmte Dreieckszahl hat. Der Unterschied ist der
ganze Punkt: eine Dreieckszahl zu nennen, heißt eine Zahl zu nennen, von
der niemand weiß, was sie über das Ergebnis aussagt.

Vier Dinge, die auf dem Weg im Weg standen:

1. **`_MeshState._unlink` hat Kanten aus der Nachbarliste eines Punktes
   entfernt, die noch ein anderes Dreieck benutzte** (`meshopt.py`).
   Danach kannte der Zusammenfasser nur noch einen Teil der Dreiecke um
   einen Punkt, ließ den Rest stehen, und der hing am Schluß nur noch an
   einer Kante am Rest: 8.660 Randkanten, 1.805 nicht-manigfaltige Kanten
   und **255 Einzelteile aus einem Stück** nach einer harmlosen
   Vereinfachung von 775 k auf 300 k Dreiecke.
2. **Es fehlte die Nachbarschaftsbedingung** (link condition), jetzt in
   `quadric_decimate`: `lk(u) ∩ lk(w) = lk(uw)`. Ohne sie entsteht beim
   Zusammenfassen eine Kante mit vier Nachbarn -- zwei Flächenblätter,
   die sich nur in dieser Kante berühren. Danach ist das Netz nicht mehr
   wasserdicht, obwohl es genauso aussieht wie vorher.
3. **Der gemessene Formfehler war eine Tautologie.**
   `metrics.surface_deviation` fragt an den VERTICES, und die Vertices
   eines vereinfachten Netzes sind lauter Punkte des Originals -- ihr
   Abstand zum Original ist null, egal wie grob das Netz inzwischen ist
   (p95 0,0015 mm bei 300 k statt 775 k). `metrics.form_error` mißt
   deshalb flächengewichtet auf der Oberfläche: p95 0,082 mm für
   dasselbe Netz, also das Fünfundfünfzigfache.
4. **Das Netz im Speicher war dicht, die DATEI nicht.** STL speichert
   Positionen als 32-Bit-Zahl, und das Optimum der Quadrik fällt sehr oft
   fast genau auf einen schon vorhandenen Punkt: zwei Punkte, im Speicher
   um 1e-6 mm verschieden, sind in der Datei identisch. 14 solcher Paare
   genügten, und aus einem Netz mit 0 Randkanten und Euler 2 kam aus der
   Datei ein Netz mit Euler 17 und `is_watertight = False` zurück.
   Zusammenfaßen NACH dem Runden heilt das nicht (es bleiben Kanten mit
   vier Nachbarn), also wird die Kollision vermieden: `float32_safe`.

Und eine Lehre, die nicht im Code steht, sondern in der Wahl der Grenzen:
**das Maximum ist keine brauchbare Grenze.** Es sitzt an einer einzigen
Haarspitze oder an der scharfen Kante unten am Sockel und wandert mit
der Stichprobe. Gezählt wird deshalb, welcher ANTEIL der Fläche über
einer Grenze liegt.

Aufruf:
    /tmp/qrenv/bin/python prototype/reference/tools/build_print_lod.py
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

sys.path.insert(0, HERE)
from build_hollow import WALL_MIN_MM, DRAIN_R_MM                    # noqa: E402
from build_hollow import build as build_hollow_field                # noqa: E402
from build_hollow import drain_connected, measure_wall              # noqa: E402

MESHES = os.path.abspath(os.path.join(HERE, "..", "meshes"))
RESULTS = os.path.abspath(os.path.join(HERE, "..", "results"))

# Kette: jeder Schritt behält diesen Anteil der AUSGANGSDREIECKE. Der
# Zusammenfasser läuft Stufe für Stufe weiter (nicht jedes Mal vom
# Original), deshalb kostet die ganze Kette kaum mehr als ein einziger
# Lauf auf die gröbste Stufe -- und man bekommt die ganze Kurve.
CHAIN = (0.60, 0.50, 0.42, 0.35, 0.29, 0.24, 0.20, 0.16, 0.13)
# Grenzen. 0,10 mm sind ein Viertel der kleinsten Düse (0,4 mm) -- auf dem
# Druck nicht zu sehen. p99 darf eine Düsenbreite erreichen, aber nur auf
# 1 % der Fläche. Das MAXIMUM ist bewußt keine Grenze (s. oben), sondern
# der Anteil über 0,5 mm.
LIMIT_P95_MM = 0.10
LIMIT_P99_MM = 0.35
LIMIT_OVER_MM = 0.50        # ab hier zählt eine Stelle als Ausreißer
LIMIT_OVER_FRAC = 0.01      # höchstens 1 % der Fläche
LIMIT_HOLE_MM = 4.0         # Ablaufloch: von 5 mm dürfen 1 mm wegfallen
N_STEP = 12_000
N_FINAL = 20_000
OVERHANG_DEG = 45.0


def banner(text: str) -> None:
    print("\n" + "=" * 74)
    print(text)
    print("=" * 74)
    sys.stdout.flush()


def volume_cm3(v, f) -> float:
    p = v[np.asarray(f, dtype=np.int64)]
    return abs(float(np.einsum("ij,ij->i", p[:, 0],
                               np.cross(p[:, 1] - p[:, 0],
                                        p[:, 2] - p[:, 0])).sum() / 6.0)) / 1000.0


def hole_radius_mm(v, f, axis_xy, z_from, z_to, n=24):
    """Freier Radius des Ablauflochs: Abstand von der Achse zur Wand.

    Gemessen wird im Netz, nicht im Feld -- gefragt ist, was der Drucker
    nachher bekommt. Sitzt die engste Stelle nicht am Loch, sondern an
    einer Dreieckskante, die schräg darüber liegt, ist das genau der
    Fehler, den man sehen will.
    """
    zs = np.linspace(float(z_from), float(z_to), int(n))
    pts = np.column_stack([np.full(n, float(axis_xy[0])),
                           np.full(n, float(axis_xy[1])), zs])
    dist, ok = mt.point_to_surface(pts, v, f, cell=4.0)
    if not ok.any():
        return 0.0
    return float(np.min(dist[ok]))


def over_frac(v, f, v_ref, f_ref, n_samples):
    """Formfehler und der Anteil der Fläche über der Ausreißgrenze."""
    q = mt.sample_surface(v_ref, f_ref, int(n_samples), seed=2026)
    d1, ok1 = mt.point_to_surface(q, v, f, cell=4.0)
    q2 = mt.sample_surface(v, f, int(n_samples), seed=2027)
    d2, ok2 = mt.point_to_surface(q2, v_ref, f_ref, cell=4.0)
    both = np.concatenate([d1[ok1], d2[ok2]])
    return float(np.percentile(both, 95)), float(np.percentile(both, 99)), \
        float(np.mean(both > LIMIT_OVER_MM)), float(both.max())


def walk(v0, f0, lock_fn=None, keepout=None, extra=None):
    """Läuft die Kette durch und mißt auf jeder Stufe.

    `lock_fn` ist eine Funktion (v, f) -> Maske, KEINE fertige Maske: der
    Zusammenfasser wirft tote Punkte heraus und numeriert die restlichen
    neu, deshalb gehört nach jedem Schritt eine andere Punktnummer zu
    derselben Stelle. Eine einmal gerechnete Maske sitzt ab dem zweiten
    Schritt auf den falschen Punkten -- das Ablaufloch war dann nur auf
    der ersten Stufe geschützt und fiel von 4,6 mm auf 2,1 mm.
    """
    rows = []
    v, f = v0, f0
    n0 = len(f0)
    for frac in CHAIN:
        target = int(round(frac * n0))
        if target >= len(f):
            continue
        t0 = time.time()
        v, f, _, _ = mo.quadric_decimate(
            v, f, target, float32_safe=True, keepout=keepout,
            locked=(None if lock_fn is None else lock_fn(v, f)))
        t_dec = time.time() - t0
        p95, p99, over, mx = over_frac(v, f, v0, f0, N_STEP)
        row = {
            "target_frac": float(frac),
            "faces": int(len(f)),
            "vertices": int(len(v)),
            "volume_cm3": volume_cm3(v, f),
            "watertight": repair.watertight_report(f),
            "p95_mm": p95, "p99_mm": p99, "over_frac": over, "max_mm": mx,
            "decimate_s": float(t_dec),
        }
        if extra is not None:
            row.update(extra(v, f))
        rows.append(row)
        print("  %4.0f %% -> %9s Dreiecke | %s | p95 %.3f | p99 %.3f | "
              ">%4.1f mm auf %.2f %% | max %5.2f mm | %3.0f s%s"
              % (100 * frac, f"{len(f):,}",
                 "dicht" if row["watertight"]["watertight"] else "UNDICHT",
                 p95, p99, LIMIT_OVER_MM, 100 * over, mx, t_dec,
                 "" if extra is None
                 else " | Wand p01 %.2f | Loch %.1f mm"
                      % (row["wall"]["p01_mm"], row["hole_mm"])))
        sys.stdout.flush()
    return rows


def ok_row(row) -> bool:
    if not row["watertight"]["watertight"]:
        return False
    if row["p95_mm"] > LIMIT_P95_MM or row["p99_mm"] > LIMIT_P99_MM:
        return False
    if row["over_frac"] > LIMIT_OVER_FRAC:
        return False
    if "wall" in row and row["wall"]["p01_mm"] < WALL_MIN_MM:
        return False
    if "hole_mm" in row and row["hole_mm"] < LIMIT_HOLE_MM:
        return False
    return True


def pick(rows):
    best = None
    for row in rows:
        if ok_row(row):
            best = row
    return best


def main() -> int:
    t_start = time.time()
    path = os.path.join(MESHES, "print_field.npz")
    if not os.path.exists(path):
        print("Kein Feld unter %s -- bitte zuerst build_print.py laufen "
              "lassen." % path)
        return 2
    st = np.load(path)
    field, lo, h, level = (st["field"], st["lo"], float(st["h"]),
                           float(st["level"]))
    z_cut, z_base, axis_xy = float(st["z_cut"]), float(st["z_base"]), st["axis_xy"]
    sv, sf = st["v"], st["f"]

    banner("DRUCKNETZ VEREINFACHEN  (docs/05 12.2)")
    print(f"  massiv: {len(sv):,} Punkte / {len(sf):,} Dreiecke, "
          f"{volume_cm3(sv, sf):.1f} cm³")
    print("  Grenzen: p95 <= %.2f mm, p99 <= %.2f mm, hoechstens %.0f %% der "
          "Flaeche ueber %.2f mm" % (LIMIT_P95_MM, LIMIT_P99_MM,
                                     100 * LIMIT_OVER_FRAC, LIMIT_OVER_MM))
    print(f"           Hohlkoerper zusaetzlich: Wand p01 >= {WALL_MIN_MM:.1f} mm, "
          f"Ablaufloch >= {LIMIT_HOLE_MM:.1f} mm frei")
    print("           und das Netz muß dicht bleiben -- im Speicher UND in der Datei")
    sys.stdout.flush()

    # ------------------------------------------------- 1) Hohlkörper ----
    banner("1)  Hohlkörper frisch marchieren (Vorlage für die Kette)")
    hollow_field = build_hollow_field(field, lo, h, level, 2.4,
                                      z_cut, z_base, axis_xy)
    raw_v, raw_f, ties = repair.march_indicator(hollow_field, lo, h, level,
                                                tie_eps=1e-5)
    hv, hf, info = repair.clean_mesh(raw_v, raw_f)
    # Funktionsfläche schützen: das Ablaufloch. Ohne diesen Schutz
    # schrumpft es von 10 mm auf gut 4 mm -- ein Zylinder ist eine
    # abwickelbare Fläche, und das Zusammenfassen entlang der Achse kostet
    # die Quadrik praktisch nichts.
    def lock_fn(v, f):
        rad = np.hypot(v[:, 0] - axis_xy[0], v[:, 1] - axis_xy[1])
        return (rad < DRAIN_R_MM + 4.0) & (v[:, 2] < z_cut + 6.0)

    locked = lock_fn(hv, hf)
    # Sperrgebiet: keine Dreieckskante darf durch diesen Zylinder. Sonst
    # deckt ein einziges grobes Dreieck des waagerechten Bodens das
    # Ablaufloch zu -- eine ebene Fläche vereinfacht sich kostenlos, und
    # drei Punkte im Abstand von 120° ergeben ein Dreieck über dem Loch.
    # Das Netz bleibt tadellos wasserdicht und entwässert doch nicht mehr.
    keepout = ((float(axis_xy[0]) - 4.0, float(axis_xy[1]) - 4.0, z_base - 1.0),
               (float(axis_xy[0]) + 4.0, float(axis_xy[1]) + 4.0, z_cut + 3.0))
    print(f"  {len(hv):,} Punkte / {len(hf):,} Dreiecke, "
          f"wasserdicht = {repair.watertight_report(hf)['watertight']}")
    print(f"  geschuetzt: {int(locked.sum()):,} Punkte am Ablaufloch "
          f"({100 * locked.mean():.2f} %), die sich nicht bewegen duerfen")
    sys.stdout.flush()

    # ------------------------------------------------------- 2) Kette ---
    banner("2)  Kette durchlaufen und jede Stufe nachmessen")
    print("  massiv:")
    solid_rows = walk(sv, sf)
    print("\n  hohl:")
    hollow_rows = walk(hv, hf, lock_fn=lock_fn, keepout=keepout,
                       extra=lambda v, f: {
        "wall": {k: x for k, x in measure_wall(v, f, hollow_field, lo, h,
                                               level, z_cut, N_STEP).items()
                 if k != "at_mm"},
        "hole_mm": hole_radius_mm(v, f, axis_xy, z_base + 2.0, z_cut - 2.0),
    })

    # ------------------------------------------------------ 3) Wahl -----
    banner("3)  Gröbste Stufe, die die Grenzen einhält")
    chosen = {}
    for label, rows, n_ref in (("massiv", solid_rows, len(sf)),
                               ("hollow", hollow_rows, len(hf))):
        best = pick(rows)
        chosen[label] = best
        if best is None:
            print(f"  {label}: KEINE Stufe haelt die Grenzen ein")
            continue
        print(f"  {label}: {best['faces']:,} Dreiecke = "
              f"{100 * best['faces'] / n_ref:.0f} % der Ausgangsfassung "
              f"({100 * (1 - best['faces'] / n_ref):.0f} % gespart)")
        print(f"          p95 {best['p95_mm']:.3f} mm | p99 "
              f"{best['p99_mm']:.3f} mm | max {best['max_mm']:.2f} mm | "
              f"{100 * best['over_frac']:.2f} % ueber {LIMIT_OVER_MM:.1f} mm")
        if "wall" in best:
            print(f"          Wand p01 {best['wall']['p01_mm']:.2f} mm, "
                  f"Loch {best['hole_mm']:.1f} mm frei")
    sys.stdout.flush()

    # -------------------------------------------- 4) Frisch und Export --
    # Die Kette rechnet Stufe für Stufe weiter, die gewählte Stufe muß
    # aber FRISCH aus dem Original entstehen -- sonst steht im Bericht ein
    # Netz, das so kein zweites Mal herauskommt.
    banner("4)  Gewaehlte Stufe frisch rechnen, exportieren, gegenlesen")
    out = {}
    for label, v0, f0, lock, tag in (
            ("massiv", sv, sf, None, "facescan_print_lod.stl"),
            ("hollow", hv, hf, lock_fn, "facescan_print_lod_hollow.stl")):
        rows = solid_rows if label == "massiv" else hollow_rows
        best = chosen[label]
        if best is None:
            # Die Kette ist pessimistisch (s. unten), deshalb ist das
            # keine Absage: angefangen wird bei ihrer feinsten Stufe.
            if not rows:
                continue
            best = rows[0]
            print(f"  {label}: keine Stufe der Kette haelt die Grenzen "
                  f"ein -- Versuch ab der feinsten ({best['faces']:,})")
        # Frisch gerechnet ist ein Netz bei GLEICHER Dreieckszahl besser
        # als über die Kette (gemessen: p95 0,081 statt 0,098 bei 387 k).
        # Die Kette sucht also nur den Bereich; nachgeschaerft wird mit
        # frischen Läufen, von der gewählten Stufe immer eine gröber,
        # bis eine die Grenze reißt.
        # Reihenfolge: gewaehlte Stufe zuerst, dann immer eine groeber.
        tries = [r for r in rows if r["faces"] <= best["faces"]][:4]
        rec = None
        for attempt in tries:
            v, f, _, _ = mo.quadric_decimate(
                v0, f0, int(attempt["faces"]), float32_safe=True,
                keepout=(None if lock is None else keepout),
                locked=(None if lock is None else lock(v0, f0)))
            p95, p99, over, mx = over_frac(v, f, v0, f0, N_FINAL)
            rep = repair.watertight_report(f)
            row = {"faces": len(f), "p95_mm": p95, "p99_mm": p99,
                   "over_frac": over, "max_mm": mx, "watertight": rep}
            if label == "hollow":
                th = measure_wall(v, f, hollow_field, lo, h, level, z_cut,
                                  N_FINAL)
                row["wall"] = {k: x for k, x in th.items() if k != "at_mm"}
                row["hole_mm"] = hole_radius_mm(v, f, axis_xy, z_base + 2.0,
                                                z_cut - 2.0)
            if not ok_row(row):
                print(f"  {label}: frisch gerechnet reißt "
                      f"{attempt['faces']:,} Dreiecke die Grenze "
                      f"(p95 {p95:.3f}) -- die Stufe darüber bleibt")
                break
            rec = row
            kept = (v, f)
        if rec is None:
            print(f"  {label}: haelt auch frisch nicht -- "
                  f"Ausgangsfassung bleibt")
            continue
        v, f = kept
        stl = os.path.join(MESHES, tag)
        em.write_stl(stl, v, f)
        back = em.read_stl(stl)
        dev = mt.form_error(v0, f0, v, f, n_samples=N_FINAL)
        oh = pc.overhang_report(v, f, limit_deg=OVERHANG_DEG)
        sd = pc.stand_report(v, f)
        rec.update({
            "vertices": int(len(v)),
            "volume_cm3": volume_cm3(v, f),
            "saved_pct": 100 * (1 - rec["faces"] / (len(sf) if label == "massiv"
                                                    else len(hf))),
            "error": dev,
            "overhang": {k: x for k, x in oh.items()},
            "stand": {k: (x.tolist() if isinstance(x, np.ndarray) else x)
                      for k, x in sd.items()},
            "stl_kb": os.path.getsize(stl) / 1024.0,
            "stl_faces": int(back["faces"].shape[0]),
        })
        if label == "hollow":
            rec["drain_open"] = drain_connected(hollow_field, lo, h, level,
                                                axis_xy, z_base - 1.0,
                                                z_cut + 20.0)[0]
        try:
            import trimesh
            tm = trimesh.load(stl)
            if hasattr(tm, "geometry"):
                tm = list(tm.geometry.values())[0]
            rec["trimesh"] = {"watertight": bool(tm.is_watertight),
                              "euler": int(tm.euler_number),
                              "volume_cm3": float(tm.volume) / 1000.0}
        except Exception as exc:                        # noqa: BLE001
            rec["trimesh"] = {"error": str(exc)}
        out[label] = rec
        print(f"\n  {label}: {len(v):,} Punkte / {len(f):,} Dreiecke -> "
              f"{os.path.basename(stl)} ({rec['stl_kb'] / 1024.0:.1f} MB, "
              f"{100 * (1 - rec['faces'] / (len(sf) if label == 'massiv' else len(hf))):.0f} % gespart)")
        print(f"    im Speicher dicht: {rep['watertight']} (Euler "
              f"{rep['euler']}, {rep['components']} Stueck)")
        print(f"    in der DATEI dicht: trimesh "
              f"{rec['trimesh'].get('watertight')} (Euler "
              f"{rec['trimesh'].get('euler')})")
        print(f"    Formfehler p95 {dev['p95_mm']:.3f} | p99 "
              f"{dev['p99_mm']:.3f} | max {dev['max_mm']:.2f} mm "
              f"bei {np.round(dev['to_lod']['at_mm'], 1)}")
        print(f"    Standflaeche {sd['contact_cm2']:.1f} cm², "
              f"Ueberhang > {OVERHANG_DEG:.0f}° auf "
              f"{100 * oh['fraction']:.1f} %")
        if "wall" in rec:
            print(f"    Wand p01 {rec['wall']['p01_mm']:.2f} mm, "
                  f"Loch {rec['hole_mm']:.1f} mm frei, Ablauf "
                  f"{'offen' if rec['drain_open'] else 'ZU'}")
        sys.stdout.flush()

    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, "m2b_print_lod_report.json"), "w",
              encoding="utf-8") as fh:
        json.dump({
            "limits": {"p95_mm": LIMIT_P95_MM, "p99_mm": LIMIT_P99_MM,
                       "over_mm": LIMIT_OVER_MM,
                       "over_frac": LIMIT_OVER_FRAC,
                       "wall_p01_mm": WALL_MIN_MM,
                       "hole_mm": LIMIT_HOLE_MM},
            "chain": list(CHAIN),
            "solid_reference": {"vertices": int(len(sv)), "faces": int(len(sf)),
                                "volume_cm3": volume_cm3(sv, sf)},
            "hollow_reference": {"vertices": int(len(hv)), "faces": int(len(hf)),
                                 "volume_cm3": volume_cm3(hv, hf),
                                 "locked_vertices": int(locked.sum())},
            "keepout": {"lo": list(keepout[0]), "hi": list(keepout[1])},
            "solid_chain": solid_rows,
            "hollow_chain": hollow_rows,
            "chosen": out,
            "runtime_s": float(time.time() - t_start),
        }, fh, indent=2, default=float)
    print(f"\nFertig in {time.time() - t_start:.0f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
