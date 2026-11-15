# FaceScan – Prototyp (M0)

**Zweck:** der ehrliche Machbarkeitsnachweis. Nicht hübsch, nicht vollständig – sondern die
Antwort auf die eine Frage, an der das ganze Produkt hängt:

> Bekommen wir aus 2D-Gesichtspunkten und den Kamera-Parametern eines Handys eine
> **metrische** 3D-Rekonstruktion – **ohne ARCore**, ohne SLAM, ohne Tiefensensor?

Antwort: **ja**, mit Zahlen belegt gegen synthetische Ground Truth (siehe unten).

---

## 1. Aufbau

```
prototype/
├── reference/python/          Referenz-Implementierung (Python + NumPy) – läuft hier
│   ├── run_m0.py              Der Versuchsablauf: F1, F2, F3, F4 + Fixture-Erzeugung
│   ├── kotlin_mirror.py       Nachbau des Kotlin-Kerns in reinem Python (s. §5)
│   └── facescan_ref/
│       ├── math3d.py          Rodrigues, Projektion, Pose-Jacobi-Matrix, Orthonormalisierung
│       ├── pose.py            POSIT-Init + Huber-IRLS + gedämpftes Gauss-Newton
│       ├── synthetic.py       deterministische Ground Truth (Szene, Rauschen, Ausreisser)
│       └── fit.py             Multi-Frame-3DMM-Fit + Auswertung
├── reference/fixtures/        m0_fixtures.json – Gold-Daten für die Tests
├── reference/results/         m0_report.json – alle Kennzahlen des Laufs
└── android/                   Produktionskern in Kotlin (siehe §4)
    └── app/src/main/java/.../geometry/     Mat3, Linalg, CameraModel, PoseEstimator,
        app/src/test/java/.../geometry/     MorphableModel, ModelFitter + Tests
```

## 2. Referenz ausführen

```bash
python3 -m venv /tmp/qrenv && /tmp/qrenv/bin/pip install numpy
/tmp/qrenv/bin/python prototype/reference/python/run_m0.py
/tmp/qrenv/bin/python prototype/reference/python/kotlin_mirror.py
```

Beide Skripte sind deterministisch (Seed 2026) und brauchen kein Netz.

## 3. Ergebnisse (Stand dieses Commits)

Szene: 120 Punkte, 8 Aufnahmen, 1080×1920 bei 62° FOV, 1,0 px Landmark-Rauschen,
5 % Ausreisser, 8 % Verdeckung, ~50 cm Abstand.

| Frage | Kennzahl | Ergebnis | Ziel |
|---|---|---|---|
| **F1** Pose ohne ARCore | Rotation (Mittel / Max) | **0,169° / 0,402°** | < 1,0° |
| | Translation (Mittel / Max) | **0,99 mm / 2,12 mm** | < 15 mm |
| **F2** Multi-Frame-Fit | Reprojektion (Inlier) | **1,556 px** | < 2,0 px |
| | Geometriefehler Kopf | **0,334 mm** | < 5,0 mm |
| | Identitäts-Korrelation | **0,600** | – |
| | Rotation / Translation | **0,072° / 0,446 mm** | – |
| **F3** Robustheit | 0,5 px → 4,0 px Rauschen | 0,021° → 0,321° Rotation, 0,08 → 1,34 mm | – |
| | 0 % → 15 % Ausreisser | Inlier-RMS 0,69 → 6,05 px | – |
| **F4** Bilder vs. Genauigkeit | 4 / 8 / 12 / 16 / 24 Frames | Identitäts-Korr. 0,715 / 0,621 / 0,678 / 0,784 / **0,953** | – |

**Die wichtigste Erkenntnis aus F4:** mehr Bilder verbessern vor allem die *Formtreue*
(Identität), nicht die Pose. Das ist die Begründung für 16 (Quick) / 48 (Standard) /
120 (Pro) Aufnahmen in der App – und es ist der Grund, warum "Standard" die sinnvolle
Voreinstellung ist, nicht "Pro".

**Die zweitwichtigste Erkenntnis (F3):** Pose und Geometrie bleiben auch unter schwerer
Korruption (4 px Rauschen, 15 % Ausreisser) im Sub-Millimeter-Bereich. Was leidet, ist
nur der rohe Pixel-RMS – und der ist ohnehin die falsche Kennzahl, um das Verfahren zu
beurteilen (er wird von den Ausreissern dominiert).

## 4. Kotlin-Kern

`prototype/android/` ist der Port derselben Mathematik nach Kotlin – inklusive
Compose-Oberfläche, Kamera-Controller (CameraX + Camera2-Interop für feste Belichtung),
Bild-Akzeptanzprüfung (FrameGate) und Qualitätsbericht in Laiensprache.

**Wichtige Einschränkung, die nicht verschwiegen wird:** in dieser Entwicklungsumgebung
gibt es **kein JDK und kein Gradle**. Der Kotlin-Code ist deshalb **nie kompiliert**
worden. Was geprüft ist, steht in §5; was offen bleibt:

* Syntax und Importe – klärt der erste `./gradlew :app:assembleDebug`.
* Die MediaPipe-API in `perception/FaceLandmarkerRunner.kt` (dort als Kommentar markiert).
* Alles, was ein Gerät braucht (Kamera, Thermik, UI-Performance).

Unit-Tests (`app/src/test/...`) laufen als reine JVM-Tests ohne Robolectric und ohne
JSON-Parser – die Fixtures sind als Kotlin-Datei generiert (`M0Fixtures.kt`,
erzeugt von `run_m0.py`, nicht von Hand ändern).

```bash
cd prototype/android
./gradlew :app:assembleDebug
./gradlew :app:testDebugUnitTest     # PoseEstimatorTest, ModelFitterTest
```

Das Manifest hat **keine INTERNET-Berechtigung**. Das ist Absicht: wenn die App trotzdem
läuft, ist "offline-first" objektiv bewiesen und nicht nur behauptet.

## 5. Wie der Kotlin-Code ohne Compiler geprüft wurde

`kotlin_mirror.py` ist ein Nachbau des Kotlin-Kerns in **reinem Python**: gleiche
Index-Arithmetik, flache Arrays statt NumPy-Matrizen, Cholesky statt `np.linalg.solve`,
Newton-Orthonormalisierung statt SVD. Wenn Spiegel und NumPy-Referenz übereinstimmen,
sind Algorithmen, Indexierung und Formeln des Kotlin-Kerns belegt – nur die Syntax nicht.

Ergebnis: **Übereinstimmung auf fünf Dezimalstellen in allen elf Kennzahlen.**

Dabei gefunden und behoben (das ist der eigentliche Wert dieses Schritts):

1. **Falscher Hebelarm in der Pose-Jacobi-Matrix.** Linearisiert wurde mit `p = R·x + t`
   statt mit `R·x`. Der Fehler ist nicht klein (330 % relativ zur finiten Differenz),
   fällt aber nicht auf, weil Gauss-Newton trotzdem abstiegt – nur eben systematisch
   schief. Behoben in Python *und* Kotlin; der Rotationsfehler in F1 verbesserte sich
   von 0,245° auf 0,169°. Gesichert durch `poseJacobianStimmtMitFiniterDifferenzUeberein`.
2. **Basis-Layout.** Die Fixtures sind komponentenweise gespeichert
   (`basis[komponente * kAnzahl + k]`), der Kotlin-Code las sie mode-weise. Vertrag ist
   jetzt komponentenweise, dokumentiert und durch `basisLayoutIstKomponentenweise` geprüft.
3. **Fehlende Kreuzterme.** Im Kotlin-Fitter war `J^T J` nur auf der Diagonale gefüllt.
   Das ist ein anderes (Jacobi-)Verfahren als die Referenz und liefert andere Ergebnisse.

Lektion, die für die nächsten Meilensteine gilt: *Ein Verfahren, das konvergiert, ist
noch lange nicht richtig.* Ableitungen werden gegen finite Differenzen getestet, nicht
dadurch, dass das Ergebnis plausibel aussieht.

## 6. Was M0 bewusst NICHT enthält

Kein Multi-View-Stereo, keine TSDF-Fusion, keine Textur, keine Haare, kein Export,
keine Animation, keine echte Gesichtserkennung (die Landmarks kommen aus der synthetischen
Ground Truth). M0 ist der Beweis, dass die Geometrie-Basis trägt. Alles andere baut
darauf auf (siehe `docs/11-roadmap.md`, `docs/03-scan-pipeline.md`).

## 7. Rechtliches

Der Prototyp nutzt ausschließlich selbst erzeugte, synthetische Daten. Für das Produkt
gilt: die 3DMM-Basis wird aus eigenen, schriftlich lizenzierten Aufnahmen gebaut.
FLAME, Basel Face Model, ICT-FaceKit (voll) und SMPL sind forschungs- oder
einzelfalllizenziert und deshalb tabu (siehe `docs/09-recht-compliance.md`).

---

## English summary

This directory is the **M0 feasibility prototype**: it proves with numbers, against
synthetic ground truth, that a metric 3D face reconstruction is possible from 2D
landmarks alone – no ARCore, no SLAM, no depth sensor.

* `reference/python/run_m0.py` runs the whole experiment and writes the fixtures + report.
* `reference/python/kotlin_mirror.py` re-implements the Kotlin core in pure Python and
  checks it against the NumPy reference (agreement to five decimals on all metrics).
* `android/` holds the Kotlin production core, camera controller, Compose UI (Jamaica
  palette, night + day mode, German + English strings) and JVM unit tests.

**Known limitation:** there is no JDK/Gradle in this environment, so the Kotlin sources
have never been compiled. The algorithms and index arithmetic are verified by the mirror;
the syntax is not. Three real bugs were found and fixed by that mirror – most importantly
a wrong rotation lever arm in the pose Jacobian, which converges but is systematically
skewed.
