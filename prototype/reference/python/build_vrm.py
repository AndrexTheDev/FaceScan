"""Baut die VRM-1.0-Datei (`meshes/facescan.vrm`) aus dem Referenznetz.

Das ist der letzte der vier M3-Posten. VRM ist die Variante, die ein
VRChat-, VSeeFace- oder vtuber-Avatar verlangt: ein glTF-2.0-Binary, in dem
zusätzlich die Erweiterung `VRMC_vrm` steckt. Der Trick ist also nicht, ein
neues Format zu schreiben, sondern glTF **und** die Erweiterung in dieselbe
Datei zu packen.

Der Weg:
  1. Rahmen bestimmen (steht in `lod_state.npz`), Messpunkte setzen.
  2. Kopfskelett messen (M2) und zum VRM-Skelett erweitern (`build_vrm_skeleton`).
  3. Hautgewichte auf dem EINHEITLICHEN Skelett rechnen, damit die Gelenke
     im richtigen Koordinatensystem stehen.
  4. Blendshapes (M3c) als Morph-Ziele mitgeben.
  5. Alles in Metern nach GLB schreiben und `VRMC_vrm` anhängen.

Drei Entscheidungen, die man kennen muss, bevor man die Datei benutzt:

  * **Der Körper ist eine Attrappe.** VRM verlangt 15 Pflichtknochen,
    darunter Arme und Beine. Eine Büste hat keine. Die Gelenke sitzen
    anatomisch plausibel und bekommen keine Hautgewichte -- die Datei ist
    damit gültig, aber nur der Kopf bewegt sich. Ehrlicher als erfundene
    Beine unter dem Hals.
  * **Die Füße stehen auf Y=0** (tpose.md 1.3), nicht die Büste. Deshalb
    schwebt der Kopf auf 1,1 m Höhe. Wer die Büste auf dem Tisch haben will,
    zieht die Verschiebung wieder ab -- sie steht in `results/vrm_report.json`.
  * **Nur 6 Mimiken**, die das 3D-Modell wirklich hat. ARKit kennt 52. Die
    fehlenden 46 werden ausdrücklich NICHT erfunden.

Start:
    /tmp/qrenv/bin/python python/build_vrm.py
"""

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from facescan_ref import export_mesh, rig                     # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MESHES = os.path.join(HERE, "..", "meshes")
RESULTS = os.path.join(HERE, "..", "results")

# Die 15 Pflichtknochen nach humanoid.md. Fehlt einer, ist die Datei kein
# VRM -- egal wie schön der Kopf ist.
LIZENZ = "https://vrm.dev/licenses/1.0/"


def main() -> int:
    os.makedirs(MESHES, exist_ok=True)
    os.makedirs(RESULTS, exist_ok=True)

    print("=" * 66)
    print("FaceScan -- VRM 1.0 (M3, letzter Posten)")
    print("=" * 66)

    z = np.load(os.path.join(MESHES, "lod_state.npz"))
    v, f = z["v0"], z["f0"]
    print("\n[1/6] Netz: %d Punkte, %d Dreiecke" % (len(v), len(f)))

    print("[2/6] Rahmen und Messpunkte ...")
    fit = rig.estimate_frame(v, f)
    lm = rig.landmark_positions(fit.frame)

    print("[3/6] Skelett: gemessener Kopf + VRM-Rumpf ...")
    kopf = rig.build_skeleton(lm, fit.frame, v)
    sk = rig.build_vrm_skeleton(kopf, lm, fit.frame)
    namen = list(sk.names)
    eltern = [namen.index(j.parent) if j.parent is not None else -1
              for j in sk.joints]
    # Gelenkpositionen im selben metrischen Rahmen wie das Netz (siehe
    # build_rig.py): Millimeter -> Meter und Füße auf Y=0.
    versch = rig.boden_hoehe(sk, fit.frame, lm)
    g_pos = (np.array([j.position for j in sk.joints]) / 1000.0)
    g_pos = g_pos + fit.frame.R[:, 1] * (versch / 1000.0)
    print("      %d Gelenke, Verschiebung %.0f mm" % (len(namen), versch))
    fehlend = [n for n in rig.VRM_PFLICHT if n not in sk.names]
    print("      Pflichtknochen fehlend: %s" % (fehlend or "keine"))

    print("[4/6] Hautgewichte ...")
    # `skin_weights` verteilt NUR an die gemessenen Gelenke (Hüfte bis
    # Kiefer, per Namen). Arme und Beine gehen automatisch leer aus -- genau
    # das macht sie zur Attrappe: sie sind da, damit die Datei gültig ist,
    # und sie bewegen kein einziges Dreieck.
    idx4, w4 = rig.skin_weights(v, f, sk, fit.frame)
    W = np.zeros((len(v), len(namen)), dtype=np.float32)
    for spalte in range(idx4.shape[1]):
        np.add.at(W, (np.arange(len(v)), idx4[:, spalte]), w4[:, spalte])
    tragend = [n for n in namen if W[:, namen.index(n)].max() > 0.01]
    print("      Gewicht tragen: %s" % ", ".join(tragend))
    print("      Kopf %.1f %%, Kiefer %.1f %%, Gewichtssumme max %.6f"
          % (100.0 * W[:, namen.index("head")].mean(),
             100.0 * W[:, namen.index("jaw")].mean(),
             float(w4.sum(axis=1).max())))

    netz_v = (v + fit.frame.R[:, 1] * versch) / 1000.0

    print("[5/6] Mimik ...")
    d, mimik = rig.blendshape_deltas(v, fit.frame, amplitude_mm=5.0)
    # Morph-Ziele sind VERSCHIEBUNGEN im selben Maßstab wie POSITION.
    ziele = [(dd / 1000.0).astype(np.float32) for dd in d]

    # Jede der sechs vorhandenen Mimiken bekommt EIN Preset. `blink` ist
    # absichtlich nicht in blinkLeft/blinkRight aufgespalten: das Modell hat
    # nur ein symmetrisches Lidschluss-Feld, und zwei Presets auf dasselbe
    # Ziel zu legen hieße, dem Betrachter eine Trennbarkeit vorzutäuschen,
    # die es nicht gibt.
    vrm = {
        "happy": "mouthSmile",
        "angry": "browDown",
        "surprised": "browInnerUp",
        "blink": "eyeBlink",
        "aa": "jawOpen",
        "oh": "mouthPucker",
    }

    def ausdruck(i: int, gewicht: float = 1.0) -> dict:
        return {"morphTargetBinds": [{"node": 0, "index": i,
                                      "weight": gewicht * 100.0}],
                "isBinary": False, "overrideBlink": "none",
                "overrideLookAt": "none", "overrideMouth": "none"}

    ausdruecke = {k: ausdruck(mimik.index(m)) for k, m in vrm.items()}

    print("[6/6] VRMC_vrm und GLB schreiben ...")
    knoten_je_gelenk = {n: 1 + i for i, n in enumerate(namen)}
    erweiterung = {
        "VRMC_vrm": {
            "specVersion": "1.0",
            "meta": {
                "name": "FaceScan",
                "version": "1",
                "authors": ["AndrexTheDev"],
                "licenseUrl": LIZENZ,
                "avatarPermission": "onlyAuthor",
                "commercialUsage": "personalNonProfit",
                "creditNotation": "required",
                "allowRedistribution": False,
                "modification": "prohibited",
            },
            # humanoid: Name des Knochens -> Index des glTF-KNOTENS.
            # Genau diese Verwechslung (Knochen- vs. Knotenindex) ist der
            # häufigste VRM-Fehler überhaupt.
            "humanoid": {"humanBones": {n: {"node": knoten_je_gelenk[n]}
                                        for n in namen}},
            "expressions": {"preset": ausdruecke},
            # Blicksteuerung über die Augenknochen -- die einfachere der
            # beiden Varianten aus lookAt.md, und die einzige, die ohne
            # weitere Morph-Ziele auskommt.
            "lookAt": {
                "type": "bone",
                "offsetFromHeadBone": [0.0, 0.06, 0.02],
                "rangeMapHorizontalInner": {"inputMaxValue": 90.0,
                                            "outputScale": 10.0},
                "rangeMapHorizontalOuter": {"inputMaxValue": 90.0,
                                            "outputScale": 10.0},
                "rangeMapVerticalDown": {"inputMaxValue": 90.0,
                                         "outputScale": 10.0},
                "rangeMapVerticalUp": {"inputMaxValue": 90.0,
                                       "outputScale": 10.0},
            },
        }
    }

    export_mesh.write_glb(
        os.path.join(MESHES, "facescan.vrm"),
        netz_v.astype(np.float32), f.astype(np.uint32),
        name="FaceScan",
        targets=ziele, target_names=mimik,
        skin={"joints": namen, "parents": eltern, "positions": g_pos,
              "weights": (idx4, w4)},
        extensions=erweiterung, extensions_used=["VRMC_vrm"],
    )
    print("      %s" % os.path.join(MESHES, "facescan.vrm"))

    bericht = {
        "datei": "meshes/facescan.vrm",
        "gelenke": len(namen),
        "pflichtknochen_fehlend": fehlend,
        "verschiebung_mm": round(float(versch), 1),
        "mimik": mimik,
        "mimik_von_52": len(mimik),
    }
    with open(os.path.join(RESULTS, "vrm_report.json"), "w",
              encoding="utf-8") as fh:
        json.dump(bericht, fh, indent=2, ensure_ascii=False)
    print("\nFertig. Bericht: results/vrm_report.json")
    print("Nur die Gelenke 0-8 haben Gewichte; Arme und Beine sind Attrappen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
