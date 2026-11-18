"""Baut ein `.fscan`-Projekt: der ganze Scan in einem wiederöffnbaren Container.

Das ist der Unterschied zu allem Bisherigen. Die Exporte (`facescan_m1.glb`,
`facescan_rig.dae`, `facescan.vrm` …) sind Ansichten für fremde Programme.
Das Projekt ist das, wovon sie gemacht werden — verlustfrei, wiederöffnbar,
und mit allem, was ein Export wegwirft: den Kameraposen, den Landmarks, den
Hautgewichten, dem Prüfbericht.

`docs/06` (2) beschreibt den Baum. Dieses Skript füllt ihn **so weit es
etwas Echtes einzutragen gibt** und läßt den Rest weg. Keine
Platzhalter-Datei, die so tut, als stecke etwas darin.

Was der Prototyp NICHT füllen kann und warum:

| Eintrag | fehlt, weil |
|---|---|
| `capture/frames/*.jpg` | die Aufnahmen sind gerendert, nicht fotografiert; Bilder mitschreiben hieße Dateien erfinden |
| `rig/base_head.bin` | keine registrierte Basistopologie — die braucht NRICP und damit einen Basiskopf, den es hier nicht gibt |
| `rig/blendshape_calib.json` | F-402 (Nutzer-Kalibrierung) ist nicht gebaut; ohne echte Kalibrierung wäre die Datei erfunden |
| `geometry/hair_cards.bin`, `hair_strands.bin` | Haar-Stufe L2/L3 ist nicht gebaut, nur die Haarkappe (L1) |
| `provenance/c2pa_manifest.c2pa` | C2PA braucht einen Signaturschlüssel |
| `license.json` | Entitlement, Freemium- und Krypto-Kasse sind nicht gebaut |

Start:
    /tmp/qrenv/bin/python python/build_project.py
"""

import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from facescan_ref import headmesh as hm                       # noqa: E402
from facescan_ref import project as fsp                       # noqa: E402
from facescan_ref import rig                                  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MESHES = os.path.join(HERE, "..", "meshes")
RESULTS = os.path.join(HERE, "..", "results")

# Dieselben Versuchsparameter wie tools/build_master.py — sonst stünde im
# Projekt eine Kalibrierung, die nicht zu seinem Netz paßt.
W, H = 540, 960
FX = FY = 916.6
CX, CY = W / 2.0, H / 2.0
N_FRAMES = 16
VOXEL_MM = 0.75
TRUNC_MM = 5.0
HAIR_VOXEL_MM = 1.2
BBOX = ([-130.0, -90.0, -130.0], [130.0, 160.0, 130.0])
ATLAS_RES = 2048


def _json(obj) -> bytes:
    return json.dumps(obj, indent=2, ensure_ascii=False).encode("utf-8")


def _berichte_sammeln() -> dict:
    """Alle Prüfberichte aus results/ als ein QA-Bericht.

    Nichts wird hier neu gerechnet — es wird zusammengetragen, was die
    einzelnen Bau-Schritte schon gemessen haben. Ein Prüfbericht, der sich
    seine Zahlen selbst ausdenkt, ist wertlos.
    """
    namen = ["m0_report.json", "m1_report.json", "m2b_lod_report.json",
             "m2b_watertight_report.json", "m2b_print_report.json",
             "m2b_print_lod_report.json", "m2b_hollow_report.json",
             "m2b_motion_report.json", "rig_report.json",
             "vrm_report.json", "clip_report.json"]
    gesammelt = {}
    for n in namen:
        p = os.path.join(RESULTS, n)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                gesammelt[n.replace(".json", "")] = json.load(fh)
    return gesammelt


def haupt() -> int:
    os.makedirs(MESHES, exist_ok=True)
    os.makedirs(RESULTS, exist_ok=True)
    t0 = time.time()

    print("=" * 70)
    print("FaceScan -- .fscan Projektcontainer (docs/06)")
    print("=" * 70)

    dateien: dict[str, bytes] = {}

    # --- Geometrie -------------------------------------------------------
    print("\n[1/7] Geometrie ...")
    master = np.load(os.path.join(MESHES, "master_state.npz"))
    lod = np.load(os.path.join(MESHES, "lod_state.npz"))
    v_hi, f_hi, uv_hi = master["v"], master["f"], master["uv"]
    dateien["geometry/mesh_skin_hi.bin"] = fsp.mesh_bin(v_hi, f_hi, uv_hi)
    print("      mesh_skin_hi  %7d Punkte / %7d Dreiecke" % (len(v_hi), len(f_hi)))

    # lod_state hat v0..v3; v0 ist das Master-Hautnetz, also LOD0.
    for stufe in range(4):
        v, f, u = lod["v%d" % stufe], lod["f%d" % stufe], lod["u%d" % stufe]
        dateien["geometry/mesh_skin_lod%d.bin" % stufe] = fsp.mesh_bin(v, f, u)
        print("      mesh_skin_lod%d %6d Punkte / %7d Dreiecke"
              % (stufe, len(v), len(f)))

    hv, hf, huv, _ = hm.hair_mesh()
    dateien["geometry/hair_cap.bin"] = fsp.mesh_bin(hv, hf, huv)
    print("      hair_cap      %7d Punkte / %7d Dreiecke" % (len(hv), len(hf)))

    # Kopfhaut-UV: die UV-Koordinaten der Punkte im Haarbereich. Nicht die
    # des Haarnetzes -- die Kopfhaut ist das, worauf die Haare sitzen.
    v0, f0, u0 = lod["v0"], lod["f0"], lod["u0"]
    fit = rig.estimate_frame(v0, f0)
    lm = rig.landmark_positions(fit.frame)
    richtung = (v0 - fit.frame.center) / np.linalg.norm(
        v0 - fit.frame.center, axis=1, keepdims=True)
    lokal = richtung @ fit.frame.R
    # Kopfhaut = Punkte im Haarbereich, die UNTER der Haaraußenfläche
    # liegen. Nur nach der Richtung zu fragen („liegt im Haarbereich")
    # genügt nicht: dann sind 83 % des Netzes Kopfhaut, weil der Scan das
    # Haarvolumen mit enthält und dessen Außenhaut den größten Teil der
    # Oberfläche stellt. 2 mm Abstand, damit die Haaroberfläche selbst
    # nicht mitzählt.
    kopfhaut = hm.hair_region(lokal) & (
        np.linalg.norm(v0 - fit.frame.center, axis=1)
        < hm.hair_outer(lokal) - 2.0)
    dateien["geometry/scalp_uv.bin"] = fsp.mesh_bin(
        v0[kopfhaut], np.zeros((0, 3), dtype=np.int64), u0[kopfhaut])
    print("      scalp_uv      %7d Punkte im Haarbereich (%.0f %%)"
          % (int(kopfhaut.sum()), 100 * kopfhaut.mean()))

    dateien["geometry/tsdf_meta.json"] = _json({
        "schemaVersion": 1,
        "voxel_mm": VOXEL_MM,
        "trunc_mm": TRUNC_MM,
        "hair_voxel_mm": HAIR_VOXEL_MM,
        "bbox_mm": {"min": BBOX[0], "max": BBOX[1]},
        "stufen": [{"name": "haut", "voxel_mm": VOXEL_MM},
                   {"name": "haar", "voxel_mm": HAIR_VOXEL_MM}],
        "einheit": "mm",
        "hinweis": "Parameter von tools/build_master.py; stehen hier, damit "
                   "ein wiedereröffnetes Projekt sein Netz nachrechnen kann.",
    })

    # --- Aufnahme --------------------------------------------------------
    print("[2/7] Aufnahme ...")
    poses = hm.orbit_poses(N_FRAMES, radius=520.0, yaw_deg=75.0, pitch_deg=9.0)
    dateien["capture/calibration.json"] = _json({
        "schemaVersion": 1,
        "bild": {"breite": W, "hoehe": H},
        "K": [[FX, 0.0, CX], [0.0, FY, CY], [0.0, 0.0, 1.0]],
        "verzeichnung": [0.0, 0.0, 0.0, 0.0, 0.0],
        "einheit": "mm",
        "konvention": "p_cam = R p + t, Blickrichtung +z, y oben",
        "imu_up": [0.0, 1.0, 0.0],
        "frames": [{"index": i,
                    "R": [[float(x) for x in zeile] for zeile in R],
                    "t": [float(x) for x in t],
                    "zeit_s": round(i / 30.0, 4)}
                   for i, (R, t) in enumerate(poses)],
        "hinweis": "Synthetische Aufnahme. K und Posen sind die Parameter, "
                   "mit denen das Netz WIRKLICH gerechnet wurde -- keine "
                   "geschätzte Kalibrierung.",
    })
    print("      %d Posen, K = [[%.1f, 0, %.1f], ...]" % (len(poses), FX, CX))

    # perception.bin: die Landmarks. Sie sind der Rohstoff, aus dem Rahmen
    # und Modell-Fit entstanden sind; ohne sie ist ein Projekt nicht mehr
    # nachvollziehbar.
    namen_lm = sorted(lm.keys())
    punkte = np.array([lm[n] for n in namen_lm], dtype=float)
    q, skal, vers = fsp.quantisieren(punkte)
    kopf = {"schemaVersion": 1, "landmarks": namen_lm,
            "dtype": "int16", "skalierung": skal, "versatz": vers,
            "einheit": "mm"}
    roh = json.dumps(kopf, separators=(",", ":")).encode("utf-8")
    dateien["capture/perception.bin"] = (
        fsp.MAGIE + len(roh).to_bytes(4, "little") + roh
        + q.astype("<i2").tobytes())
    print("      %d Landmarks, groesste Quantisierungsstufe %.4f mm"
          % (len(namen_lm), max(skal) / 2))

    # --- Rig -------------------------------------------------------------
    print("[3/7] Rig ...")
    sk = rig.build_skeleton(lm, fit.frame, v0)
    gelenke = []
    for i, j in enumerate(sk.joints):
        gelenke.append({
            "name": j.name,
            "elter": j.parent,
            "position_mm": [round(float(x), 4) for x in j.position],
            # Bindematrix in der Ruhepose: reine Verschiebung, spaltenweise.
            "bind": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0],
                     [round(float(-j.position[0]), 4),
                      round(float(-j.position[1]), 4),
                      round(float(-j.position[2]), 4), 1]],
        })
    dateien["rig/skeleton.json"] = _json({
        "schemaVersion": 1,
        "einheit": "mm",
        "rahmen": {"oben": [round(float(x), 6) for x in fit.frame.R[:, 1]],
                   "vorn": [round(float(x), 6) for x in fit.frame.R[:, 2]],
                   "mitte": [round(float(x), 4) for x in fit.frame.center],
                   "massstab": round(float(fit.frame.scale), 6)},
        "gelenke": gelenke,
    })
    print("      skeleton.json: %d Gelenke" % len(gelenke))

    idx, wts = rig.skin_weights(v0, f0, sk, fit.frame)
    dateien["rig/weights.bin"] = fsp.weights_bin(idx, wts, len(sk.joints))
    print("      weights.bin: %d Punkte x %d Einfluesse, uint8"
          % (idx.shape[0], idx.shape[1]))

    deltas, bs_namen = rig.blendshape_deltas(v0, fit.frame)
    for name, d in zip(bs_namen, deltas):
        dateien["rig/blendshapes/%s.bin" % name] = fsp.deltas_bin(d)
    dateien["rig/morph_names.json"] = _json({
        "schemaVersion": 1,
        "reihenfolge": bs_namen,
        "benennung": "ARKit",
        "anzahl": len(bs_namen),
        "anzahl_arkit": 52,
        "hinweis": "Nur die Ausdruecke, zu denen das 3DMM eine Richtung "
                   "besitzt. Die anderen 46 werden NICHT aus diesen "
                   "abgeleitet -- echte Gesichter laecheln nicht "
                   "spiegelsymmetrisch.",
    })
    print("      %d Blendshapes: %s" % (len(bs_namen), ", ".join(bs_namen)))

    # --- Texturen --------------------------------------------------------
    print("[4/7] Texturen ...")
    tex_pfad = os.path.join(MESHES, "texture_2048.png")
    if os.path.exists(tex_pfad):
        with open(tex_pfad, "rb") as fh:
            dateien["textures/basecolor.png"] = fh.read()
        print("      basecolor.png %d kB (2048er Atlas, docs/06 nennt 4K)"
              % (len(dateien["textures/basecolor.png"]) / 1000))
    dateien["textures/uv_meta.json"] = _json({
        "schemaVersion": 1,
        "aufloesung": ATLAS_RES,
        "kanaele": {"farbe": "RGB", "alpha": "keins"},
        "konvention": "UV-Ursprung links unten (glTF/OpenGL), nicht links oben",
        "karten": {"basecolor": "basecolor.png"},
        "hinweis": "Nur die Basisfarbe ist gebacken. Normal, Roughness und "
                   "AO sind in docs/06 gefordert, aber nicht gebaut.",
    })

    # --- Animation -------------------------------------------------------
    print("[5/7] Animation ...")
    clip_pfad = os.path.join(MESHES, "facescan_clip.fsmc")
    if os.path.exists(clip_pfad):
        with open(clip_pfad, "rb") as fh:
            cl = fh.read()
        dateien["animation/clips/pruefbewegung.fsmc"] = cl
        dateien["animation/library.json"] = _json({
            "schemaVersion": 1,
            "clips": [{"name": "pruefbewegung",
                       "datei": "pruefbewegung.fsmc",
                       "fps": 30.0, "frames": 120,
                       "dauer_s": 4.0,
                       "bytes": len(cl),
                       "art": "Pruefbewegung, keine aufgenommene Mimik"}],
        })
        print("      1 Clip, %d kB" % (len(cl) / 1000))

    # --- QA und Herkunft -------------------------------------------------
    print("[6/7] QA und Herkunft ...")
    berichte = _berichte_sammeln()
    dateien["qa/report.json"] = _json({
        "schemaVersion": 1,
        "erzeugt": fsp.ZEITSTEMPEL,
        "berichte": berichte,
        "hinweis": "Zusammengetragen aus results/. Keine Zahl ist neu "
                   "gerechnet; jede stammt aus dem Bau-Schritt, der sie "
                   "gemessen hat.",
    })
    print("      report.json mit %d Teilberichten" % len(berichte))
    thumb = os.path.join(RESULTS, "texture_preview.png")
    if os.path.exists(thumb):
        with open(thumb, "rb") as fh:
            dateien["qa/thumb.png"] = fh.read()
        print("      thumb.png %d kB" % (len(dateien["qa/thumb.png"]) / 1000))
    dateien["provenance/third_party.json"] = _json({
        "schemaVersion": 1,
        "bibliotheken": [
            {"name": "NumPy", "lizenz": "BSD-3-Clause",
             "nutzung": "Lineare Algebra, allgegenwaertig"},
            {"name": "trimesh", "lizenz": "MIT",
             "nutzung": "nur zum GEGENLESEN der Exporte"},
            {"name": "pycollada", "lizenz": "BSD-2-Clause",
             "nutzung": "nur zum GEGENLESEN von DAE"},
            {"name": "usd-core (pxr)", "lizenz": "Apache-2.0",
             "nutzung": "nur zum GEGENLESEN von USDA/USDZ"},
            {"name": "assimp", "lizenz": "BSD-3-Clause",
             "nutzung": "nur zum GEGENLESEN (DAE, BVH, GLB)"},
        ],
        "3dmm": {"name": "eigenes synthetisches Kopfmodell",
                 "lizenz": "selbst erzeugt",
                 "hinweis": "FLAME, Basel Face Model, ICT-FaceKit (voll) und "
                            "SMPL sind forschungs- oder einzelfalllizenziert "
                            "und deshalb tabu (docs/09)."},
    })
    print("      third_party.json: 5 Bibliotheken, alle nur zum Gegenlesen")

    # --- schreiben und zuruecklesen --------------------------------------
    print("[7/7] Container schreiben und zuruecklesen ...")
    pfad = os.path.join(MESHES, "facescan.fscan")
    manifest = fsp.write_fscan(pfad, dateien, name="Referenzkopf",
                               notizen="Synthetischer Referenzscan (Prototyp)",
                               tags=["prototyp", "synthetisch", "referenz"])
    groesse = os.path.getsize(pfad)
    gelesen_manifest, gelesen = fsp.read_fscan(pfad)

    # manifest.json steht nicht im gelesenen Dict -- read_fscan nimmt es
    # heraus, weil es die Prüfsummen enthält und sich nicht selbst prüfen
    # kann. Für das Inventar zählt es trotzdem mit.
    inv = fsp.inventar(set(gelesen) | {"manifest.json"})
    print("      %s  %.1f MB, %d Eintraege"
          % (os.path.basename(pfad), groesse / 1e6, len(gelesen)))
    print("      Pruefsummen: %d geprueft, alle i.O."
          % len(gelesen_manifest["dateien"]))

    # Der Rueckweg: ein Netz herausgreifen und nachrechnen, was beim
    # Quantisieren verloren ging.
    netz = fsp.lese_mesh_bin(gelesen["geometry/mesh_skin_lod0.bin"])
    fehler = float(np.abs(netz["v"] - v0).max())
    print("      Rueckweg LOD0: groesster Punktfehler %.4f mm "
          "(halbe Stufe %.4f mm)"
          % (fehler, 0.5 * max(netz["kopf"]["vertex"]["skalierung"])))
    gew = fsp.lese_weights_bin(gelesen["rig/weights.bin"])
    print("      Rueckweg Gewichte: Summe max %.4f (soll 1.0)"
          % float(gew["w"].sum(axis=1).max()))
    d_gelesen = fsp.lese_deltas_bin(gelesen["rig/blendshapes/jawOpen.bin"])
    print("      Rueckweg jawOpen: groesste Abweichung %.4f mm von %.1f mm"
          % (float(np.abs(d_gelesen - deltas[bs_namen.index("jawOpen")]).max()),
             float(np.abs(deltas[bs_namen.index("jawOpen")]).max())))

    ergebnis = {
        "datei": "meshes/facescan.fscan",
        "schemaVersion": fsp.SCHEMA_VERSION,
        "eintraege": len(gelesen),
        "bytes": groesse,
        "pruefsummen_geprueft": len(gelesen_manifest["dateien"]),
        "inventar": inv,
        "rueckweg": {
            "lod0_max_fehler_mm": round(fehler, 5),
            "lod0_halbe_stufe_mm": round(
                0.5 * max(netz["kopf"]["vertex"]["skalierung"]), 5),
            "gewichte_summe_max": round(float(gew["w"].sum(axis=1).max()), 4),
            "jawopen_max_fehler_mm": round(
                float(np.abs(d_gelesen
                             - deltas[bs_namen.index("jawOpen")]).max()), 5),
        },
    }
    with open(os.path.join(RESULTS, "project_report.json"), "w",
              encoding="utf-8") as fh:
        json.dump(ergebnis, fh, indent=2, ensure_ascii=False)

    print("\nInventar gegen docs/06 (2): %d von %d Eintraegen gefuellt"
          % (len(inv["vorhanden"]), len(fsp.INHALT_VERZEICHNIS)))
    if inv["fehlend"]:
        print("Fehlend (absichtlich, keine Platzhalter):")
        for e in inv["fehlend"]:
            print("  - %s" % e)
    print("\nBericht: results/project_report.json  (%.1f s)"
          % (time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(haupt())
