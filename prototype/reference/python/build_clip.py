"""Baut einen `.fsmc`-Motion-Clip (F-405) aus dem Skelett und der Mimik.

Zwei Dinge werden hier gemessen, und beide sind der Grund, warum es diese
Datei gibt:

1. **Rundet der Clip rund?** Geschrieben und zurückgelesen wird derselbe
   Clip; der größte Fehler darf nicht über einer halben Quantisierungsstufe
   liegen. Das prüft das Format, nicht die Bewegung.
2. **Wie groß wird ein Clip WIRKLICH?** `docs/04` (4.1) schätzt
   „~2,4 KB/Frame ≈ 4,3 MB/Minute". Das läßt sich nachrechnen: 52
   Blendshapes + Kopf-Pose + 37 Gelenke + Wurzel + 30 Fingergelenke +
   Blick sind **243 Zahlen** je Frame, und die brauchen als int16
   **486 Byte**, nicht 2,4 Kilobyte. Die Schätzung liegt also um rund das
   Fünffache daneben. Statt sie zu glauben, baut dieses Skript einen Clip
   mit genau der dokumentierten Kanalzahl und mißt ihn — zweimal: einmal
   mit dem, was der Prototyp wirklich hat, und einmal mit dem vollen Satz.

Start:
    /tmp/qrenv/bin/python python/build_clip.py
"""

import json
import os
import sys
import tempfile
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from facescan_ref import motion_clip as mc                    # noqa: E402
from facescan_ref import rig                                  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MESHES = os.path.join(HERE, "..", "meshes")
RESULTS = os.path.join(HERE, "..", "results")

FPS = 30.0
FRAMES = 120


def mimik_spur(namen: list[str], n: int, fps: float) -> dict[str, np.ndarray]:
    """Gewichte der Mimik-Kanäle über die Zeit — eine kleine Vorstellung.

    Kein echtes Gesicht, sondern ein Prüfsignal, das jeden Kanal einmal
    durch seinen Bereich führt und dabei zwei Dinge enthält, die für das
    Format wichtig sind: einen **Lidschlag** (sprunghaft, der härteste Fall
    für die Delta-Kodierung) und ein **Lächeln** (langsam, der leichteste).
    """
    t = np.arange(n) / fps
    spur = {name: np.zeros(n) for name in namen}

    def puls(mitte: float, breite: float) -> np.ndarray:
        return np.exp(-0.5 * ((t - mitte) / breite) ** 2)

    def setze(name: str, wert: np.ndarray) -> None:
        if name in spur:
            spur[name] = np.clip(wert, 0.0, 1.0)

    # Zwei Lidschläge. Die Breite ist mit 45 ms absichtlich so knapp
    # gewählt, dass der Sprung bei 30 fps in zwei bis drei Frames passiert --
    # das ist der Fall, an dem die Delta-Kodierung an ihre Grenze kommt.
    setze("eyeBlink", puls(0.80, 0.045) + puls(2.60, 0.045))
    # Sprechen: der Kiefer schließt nie über die Ruhelage hinaus.
    setze("jawOpen", (1.0 - np.cos(2 * np.pi * 0.7 * t)) / 2.0)
    # Ein Lächeln, das anschwillt und wieder abfällt.
    setze("mouthSmile", np.clip(1.2 * np.sin(np.pi * np.clip(t / 4.0, 0, 1)),
                                0.0, 1.0))
    setze("browInnerUp", puls(1.80, 0.35))
    setze("browDown", 0.6 * puls(3.10, 0.30))
    setze("mouthPucker", puls(3.30, 0.18))
    return spur


def gelenk_kanaele(sk, werte: np.ndarray) -> tuple[list, np.ndarray]:
    """BVH-Kanalwerte -> Quaternionen je Gelenk.

    `animation_values` liefert je Gelenk drei Euler-Winkel in der
    BVH-Reihenfolge Z, X, Y. Ein Clip soll aber Drehungen als Quaternion
    tragen (die Spec sieht `quat` vor): das spart pro Gelenk eine Zahl und
    hat nicht die Doppeldeutigkeit von Euler-Winkeln.
    """
    n = len(sk.joints)
    q = np.zeros((werte.shape[0], n, 4))
    # Die Wurzel bleibt in der Ruhepose; sie trägt nur die Position.
    for i in range(1, n):
        euler = werte[:, 6 + 3 * (i - 1): 6 + 3 * (i - 1) + 3]
        for f in range(werte.shape[0]):
            q[f, i] = mc.euler_zu_quat(euler[f])
    for i in range(n):
        q[:, i] = mc.quaternionen_stetig(q[:, i])
    return sk.names, q


def haupt() -> int:
    os.makedirs(MESHES, exist_ok=True)
    os.makedirs(RESULTS, exist_ok=True)
    t0 = time.time()

    print("=" * 70)
    print("FaceScan -- .fsmc Motion-Clip (F-405)")
    print("=" * 70)

    z = np.load(os.path.join(MESHES, "lod_state.npz"))
    v, f = z["v0"], z["f0"]
    print("\n[1/5] Rahmen ...")
    fit = rig.estimate_frame(v, f)
    lm = rig.landmark_positions(fit.frame)
    sk = rig.build_skeleton(lm, fit.frame, v)
    print("      %d Gelenke, Rahmen steht" % len(sk.joints))

    print("[2/5] Bewegung ...")
    werte = rig.animation_values(sk, n_frames=FRAMES, fps=FPS)
    namen, quats = gelenk_kanaele(sk, werte)
    print("      %d Frames @ %g fps (%.1f s), je Gelenk als Quaternion"
          % (FRAMES, FPS, FRAMES / FPS))

    print("[3/5] Mimik-Spur ...")
    _, bs_namen = rig.blendshape_deltas(v, fit.frame)
    spur = mimik_spur(bs_namen, FRAMES, FPS)

    # --- Kanäle zusammenstellen -----------------------------------------
    kanaele: list[tuple[str, str, np.ndarray]] = []
    # Kopf-Pose: Wurzelposition in Metern (wie im BVH) plus Kopfdrehung.
    kanaele.append(("head_position", "vec3",
                    np.tile(np.asarray(werte[0, 0:3], dtype=float),
                            (FRAMES, 1))))
    kopf = sk.index("head")
    kanaele.append(("head_rotation", "quat", quats[:, kopf, :]))
    # Je Gelenk eine Drehung.
    for i, name in enumerate(namen):
        kanaele.append(("gelenk_" + name, "quat", quats[:, i, :]))
    # Blickrichtung: wohin die Augen zeigen, aus ihrer Drehung gerechnet
    # (nicht erfunden -- es ist die gedrehte Vorwärtsrichtung des Kopfes).
    li = sk.index("leftEye")
    re = sk.index("rightEye")

    def richtung(q: np.ndarray) -> np.ndarray:
        """Vorwärtsachse (0,0,1) mit dem Quaternion q gedreht."""
        q = q / np.linalg.norm(q, axis=1, keepdims=True)
        x, y, z, w = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
        blick = np.stack([
            2 * (x * z + w * y),
            2 * (y * z - w * x),
            1 - 2 * (x * x + y * y)], axis=1)
        return blick / np.linalg.norm(blick, axis=1, keepdims=True)

    blick = 0.5 * (richtung(quats[:, li, :]) + richtung(quats[:, re, :]))
    kanaele.append(("blickrichtung", "vec3", blick))
    for name in bs_namen:
        kanaele.append((name, "scalar", spur[name].reshape(-1, 1)))

    werte_pro_frame = sum(mc.KOMPONENTEN[t] for _, t, _ in kanaele)
    print("      %d Kanaele, %d Zahlen je Frame"
          % (len(kanaele), werte_pro_frame))

    print("[4/5] Schreiben und zuruecklesen ...")
    pfad = os.path.join(MESHES, "facescan_clip.fsmc")
    # bits=None heißt: so viele Stufen, wie der Kanaltyp braucht (10/14/15),
    # nicht stur 16. Siehe STUFEN_VORGABE in motion_clip.py.
    bericht = mc.write_fsmc(pfad, kanaele, fps=FPS, keyframe_intervall=30,
                            bits=None,
                            erzeuger="FaceScan Prototyp (Referenz-Python)",
                            geraet="synthetischer Referenzkopf",
                            lizenz="eigene synthetische Daten")
    manifest, meta, gelesen = mc.read_fsmc(pfad)
    original = {name: np.asarray(w, dtype=float) for name, _, w in kanaele}
    vergleich = mc.bericht(manifest, meta, gelesen, original)

    groesse = os.path.getsize(pfad)
    print("      %s  %.1f kB" % (os.path.basename(pfad), groesse / 1e3))
    print("      roh %d B/Frame, gezippt %.1f B/Frame"
          % (bericht["bytes_roh"] / FRAMES, bericht["bytes_gezippt"] / FRAMES))
    print("      groesster relativer Fehler nach dem Rundweg: %.2e"
          % vergleich["groesster_relativer_fehler"])
    schlimmster = max(vergleich["kanaele"].items(),
                      key=lambda kv: kv[1]["relativ"])
    print("      ungenauester Kanal: %s (%.2e relativ zur Spanne)"
          % (schlimmster[0], schlimmster[1]["relativ"]))

    # --- Groessenprobe mit dem vollen, dokumentierten Kanalsatz ---------
    print("[5/5] Groessenprobe: der volle Kanalsatz aus docs/04 (4.1) ...")
    voll = voll_kanaele(FRAMES, FPS)
    n_voll = sum(mc.KOMPONENTEN[t] for _, t, _ in voll)
    print("      %d Kanaele, %d Zahlen je Frame" % (len(voll), n_voll))

    messung = {}
    with tempfile.TemporaryDirectory() as tmp:
        for label, bits in (("16 Bit ueberall", 16),
                            ("bedarfsgerecht", None)):
            probe_pfad = os.path.join(tmp, "probe_%s.fsmc"
                                      % (label[:4].strip()))
            probe = mc.write_fsmc(probe_pfad, voll, fps=FPS,
                                  keyframe_intervall=30, bits=bits,
                                  erzeuger="FaceScan Groessenprobe",
                                  geraet="Pruefsignal, keine echten Daten")
            roh = n_voll * 2
            mb_min_roh = roh * FPS * 60 / 1e6
            mb_min_gez = (probe["bytes_gezippt"] / FRAMES) * FPS * 60 / 1e6
            messung[label] = {
                "bytes_pro_frame_roh": roh,
                "bytes_pro_frame_gezippt": probe["bytes_gezippt"] / FRAMES,
                "mb_pro_minute_roh": mb_min_roh,
                "mb_pro_minute_gezippt": mb_min_gez,
                "deflate": probe["bytes_roh"] / max(probe["bytes_gezippt"], 1),
            }
            print("      %-16s roh %.2f kB/Frame = %.2f MB/min | "
                  "gezippt %.2f kB/Frame = %.2f MB/min (Deflate %.1fx)"
                  % (label, roh / 1024.0, mb_min_roh,
                     probe["bytes_gezippt"] / FRAMES / 1024.0, mb_min_gez,
                     messung[label]["deflate"]))
    print("      docs/04 schaetzt 2,4 kB/Frame = 4,3 MB/Minute -- "
          "das ist %.0fx zu viel"
          % (4.3 / messung["bedarfsgerecht"]["mb_pro_minute_gezippt"]))
    mb_min_gezippt = messung["bedarfsgerecht"]["mb_pro_minute_gezippt"]
    kb_frame_roh = n_voll * 2 / 1024.0
    mb_min_roh = n_voll * 2 * FPS * 60 / 1e6

    ergebnis = {
        "datei": "meshes/facescan_clip.fsmc",
        "schemaVersion": mc.SCHEMA_VERSION,
        "fps": FPS,
        "frames": FRAMES,
        "dauer_s": round(FRAMES / FPS, 3),
        "kanaele_dieses_clips": len(kanaele),
        "werte_pro_frame_dieses_clips": werte_pro_frame,
        "dateigroesse_bytes": groesse,
        "bytes_pro_frame_roh": bericht["bytes_roh"] / FRAMES,
        "bytes_pro_frame_gezippt": bericht["bytes_gezippt"] / FRAMES,
        "groesster_relativer_fehler": vergleich["groesster_relativer_fehler"],
        "voll_kanaele": len(voll),
        "voll_werte_pro_frame": n_voll,
        "voll_kb_pro_frame_roh": round(kb_frame_roh, 3),
        "voll_mb_pro_minute_roh": round(mb_min_roh, 3),
        "voll_messung": {k: {kk: round(vv, 3) for kk, vv in v.items()}
                         for k, v in messung.items()},
        "voll_mb_pro_minute_gezippt": round(mb_min_gezippt, 3),
        "dokumentierte_schaetzung_mb_pro_minute": 4.3,
        "dokumentierte_schaetzung_faktor": round(
            4.3 / mb_min_gezippt, 1),
        "hinweis": ("Die Zahlen des vollen Satzes stammen aus einem "
                    "Prüfsignal, nicht aus echten Daten -- gemessen wird "
                    "die Größe, nicht die Bewegung."),
    }
    with open(os.path.join(RESULTS, "clip_report.json"), "w",
              encoding="utf-8") as fh:
        json.dump(ergebnis, fh, indent=2, ensure_ascii=False)
    print("\nBericht: results/clip_report.json  (%.1f s)" % (time.time() - t0))
    return 0


def voll_kanaele(n: int, fps: float) -> list[tuple[str, str, np.ndarray]]:
    """Der Kanalsatz, den `docs/04` (4.1) beschreibt — als Prüfsignal.

    52 Mimik-Gewichte + Kopf-Pose (vec3 + quat) + 37 Gelenke (quat) +
    Wurzel-Position (vec3) + 30 Fingergelenke (scalar) + Blick (vec3).
    Die Werte sind glatte Sinusverläufe: es geht hier allein um die Frage,
    wie viele Byte so ein Frame kostet.
    """
    t = np.arange(n) / fps
    k: list[tuple[str, str, np.ndarray]] = []
    for i in range(52):
        wert = 0.5 * (1.0 - np.cos(2 * np.pi * (0.3 + 0.02 * i) * t + i))
        k.append(("bs_%02d" % i, "scalar", wert.reshape(-1, 1)))
    k.append(("head_position", "vec3",
              np.stack([0.02 * np.sin(2 * np.pi * 0.4 * t),
                        np.full(n, 1.6),
                        0.02 * np.cos(2 * np.pi * 0.4 * t)], axis=1)))
    k.append(("head_rotation", "quat", _quat_spur(t)))
    for i in range(37):
        k.append(("gelenk_%02d" % i, "quat", _quat_spur(0.5 * t + i)))
    k.append(("root_position", "vec3",
              np.stack([0.03 * np.sin(2 * np.pi * 0.5 * t),
                        np.zeros(n),
                        0.03 * np.cos(2 * np.pi * 0.5 * t)], axis=1)))
    for i in range(30):
        wert = 0.5 * (1.0 - np.cos(2 * np.pi * 0.8 * t + 0.1 * i))
        k.append(("finger_%02d" % i, "scalar", wert.reshape(-1, 1)))
    k.append(("blickrichtung", "vec3", np.stack(
        [0.4 * np.sin(2 * np.pi * 0.3 * t),
         0.2 * np.sin(2 * np.pi * 0.7 * t),
         np.full(n, 1.0)], axis=1)))
    return k


def _quat_spur(phase: np.ndarray) -> np.ndarray:
    """Eine harmlose Drehspur als Quaternion (x, y, z, w)."""
    halb = 0.5 * phase
    achse = np.stack([np.zeros_like(halb), np.ones_like(halb),
                      np.zeros_like(halb)], axis=1)
    s = np.sin(halb)[:, None]
    q = np.concatenate([achse * s, np.cos(halb)[:, None]], axis=1)
    return q / np.linalg.norm(q, axis=1, keepdims=True)


if __name__ == "__main__":
    sys.exit(haupt())
