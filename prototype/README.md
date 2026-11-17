# FaceScan – Prototyp (M0 + M1 + M2)

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
│   ├── run_m0.py              M0: Pose + Modell-Fit (F1–F4) + Fixture-Erzeugung
│   ├── run_m1.py              M1: Rendern → Fusion → Mesh → Haare → Kennzahlen → Export
│   ├── validate_exports.py    Gegenprobe mit FREMDEN Lesern (trimesh, pxr, Alembic, assimp)
│   ├── kotlin_mirror.py       Nachbau des Kotlin-Kerns in reinem Python (s. §5)
│   └── facescan_ref/
│       ├── math3d.py          Rodrigues, Projektion, Pose-Jacobi-Matrix, Orthonormalisierung
│       ├── pose.py            POSIT-Init + Huber-IRLS + gedämpftes Gauss-Newton
│       ├── synthetic.py       deterministische Ground Truth (Punkte, Rauschen, Ausreisser)
│       ├── fit.py             Multi-Frame-3DMM-Fit + Auswertung
│       ├── headmesh.py        M1-Ground-Truth: Kopf + Haar als Mesh, analytisch prüfbar
│       ├── raster.py          Z-Buffer: Tiefe + Material-Label + Farbe
│       ├── fusion.py          TSDF-Volumen + Marching-Tetrahedra
│       ├── hair.py            Haare L1: Visual Hull, Freiraum, Dickenfeld
│       ├── refine.py          Stufe 12: Vertices auf die Tiefenbilder ziehen
│       ├── metrics.py         Chamfer, IoU, Texturvollständigkeit, Gittersuche
│       └── export_mesh.py     OBJ / PLY / GLB + Rücklese-Prüfer
├── reference/fixtures/        m0_fixtures.json – Gold-Daten für die Kotlin-Tests
├── reference/results/         m0_report.json, m1_report.json – alle Kennzahlen
├── reference/meshes/          erzeugte Modelle (nicht in Git, s. .gitignore)
└── android/                   Produktionskern in Kotlin (siehe §4)
    └── app/src/main/java/.../geometry/     Mat3, Linalg, CameraModel, PoseEstimator,
        app/src/test/java/.../geometry/     MorphableModel, ModelFitter + Tests
```

## 2. Referenz ausführen

```bash
python3 -m venv /tmp/qrenv && /tmp/qrenv/bin/pip install numpy
/tmp/qrenv/bin/python prototype/reference/python/run_m0.py     # ~15 s
/tmp/qrenv/bin/python prototype/reference/python/kotlin_mirror.py
/tmp/qrenv/bin/python prototype/reference/python/run_m1.py     # ~2 min
```

Beide Skripte sind deterministisch (Seed 2026) und brauchen kein Netz.

Gegenprobe der Exporte mit fremden Lesern (optional, s. §7):

```bash
/tmp/qrenv/bin/pip install trimesh usd-core pycollada
/tmp/qrenv/bin/python prototype/reference/python/validate_exports.py
```

M2b – Master-Mesh, UV-Atlas, LOD-Kette und Textur-Bake (s. §7b):

```bash
/tmp/qrenv/bin/pip install xatlas          # optional, nur für den Atlas
/tmp/qrenv/bin/python prototype/reference/tools/build_master.py               # ~4 min
/tmp/qrenv/bin/python prototype/reference/tools/build_master.py --uv=cylindrical
/tmp/qrenv/bin/python prototype/reference/tools/build_lod.py                  # ~4 min
```

`build_master.py` sichert das Rohnetz nach `meshes/master_raw.npz`, bevor der
teure Atlas-Schritt beginnt – ein zweiter Lauf rechnet die Rekonstruktion
nicht noch einmal. `build_lod.py` holt die LOD-Kette aus `meshes/lod_state.npz`,
wenn sie schon liegt.

M2b, Teil 2 – die wasserdichte Variante für den 3D-Druck (s. §7d):

```bash
/tmp/qrenv/bin/python prototype/reference/tools/build_watertight.py          # ~3 min
/tmp/qrenv/bin/python prototype/reference/tools/build_watertight.py --fresh  # alles neu
```

Das Skript legt `meshes/watertight_skin.npz` (Hautnetz nach Stufe 2) und
`meshes/watertight_poisson.npz` (Poisson-Feld vor dem Aufräumen) daneben; wer
nur an Stufe 3 etwas ändert, rechnet damit in Sekunden statt in Minuten weiter.

M2b, Teil 3 – Sockel und Druckprüfung (s. §7e):

```bash
/tmp/qrenv/bin/python prototype/reference/tools/build_print.py           # ~100 s
```

M2b, Teil 4 – die Aufnahmebahn als BVH, CSV und JSON (s. §7f):

```bash
/tmp/qrenv/bin/python prototype/reference/tools/build_motion.py          # <1 s
```

M2b, Teil 5 – der Hohlkörper (s. §7g). Braucht das Feld aus `build_print.py`:

```bash
/tmp/qrenv/bin/python prototype/reference/tools/build_hollow.py          # ~70 s
```

M2b, Teil 6 – das Drucknetz vereinfachen (s. §7h), ebenfalls mit dem Feld:

```bash
/tmp/qrenv/bin/python prototype/reference/tools/build_print_lod.py       # ~20 min
/tmp/qrenv/bin/python prototype/reference/python/build_rig.py            # ~5 s
/tmp/qrenv/bin/python prototype/reference/python/build_vrm.py            # ~25 s
```

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

## 6. M1: vom Bild zum texturierten Mesh

`prototype/reference/python/run_m1.py` baut die komplette Geometrie-Kette gegen
dieselbe Art von Ground Truth – nur jetzt mit einer echten Oberfläche statt Punkten:

```
  Kopf/Haar als Mesh  ->  Z-Buffer-Rendern (Tiefe + Material-Label + Farbe)
                      ->  TSDF-Fusion (Haut)        -> Marching-Tetrahedra -> Mesh
                      ->  Visual Hull (Haare L1)    -> Marching-Tetrahedra -> Kappe
                      ->  Verfeinerung an den Tiefenbildern
                      ->  Chamfer / IoU / Textur / Export mit Rücklese-Test
```

Neue Module: `headmesh.py` (prozeduraler Kopf + Haar, mit Details, die kein
Modell ausdrücken kann), `raster.py`, `fusion.py`, `hair.py`, `refine.py`,
`metrics.py`, `export_mesh.py`.

**Ergebnis (16 Bilder, 540×960, 1,5 mm Voxel):**

| Kennzahl | Ergebnis | Ziel (docs/10) | Status |
|---|---|---|---|
| Chamfer-Abstand Haut | **0,745 mm** (p95 1,56) | ≤ 0,8 mm | bestanden |
| Haar-IoU (Volumen, L1) | **0,871** (Treffer 0,884 / Abdeckung 0,983) | ≥ 0,85 | bestanden |
| Textur-Vollständigkeit | **99,9 %** (≥ 3 Sichtungen: 96,3 %) | ≥ 95 % | bestanden |
| Export-Rücklese (9 Formate, s. §7) | identisch bis 4e-6 mm | – | bestanden |
| Entartete Dreiecke | 0 | 0 | bestanden |

**Was unterwegs schiefging und behoben wurde** (das ist der eigentliche Ertrag):

1. **Visual Hull mit der falschen Silhouette.** Zuerst wurde die *Haar*-Maske
   als Silhouette benutzt. Ein Haarvoxel am Hinterkopf fällt aber aus jeder
   vorderen Kamera auf ein *Haut*-Pixel (der Kopf verdeckt es) – der halbe
   Hinterkopf wurde weggeschnitten. IoU 0,31 → mit der **Objekt**-Silhouette
   0,87.
2. **Projektive TSDF ist systematisch schief.** Die TSDF misst entlang des
   Blickstrahls, nicht senkrecht zur Fläche. Bei streifendem Blick ist der
   Fehler um 1/cos größer. Abhilfe: Gewichtung mit dem Einfallswinkel
   (`TsdfVolume.incidence_weights`) **und** Verfeinerung der Vertices an den
   Tiefenbildern (`refine.py`). Chamfer 1,37 mm → 0,75 mm.
3. **Die „Wand“ am Rand des beobachteten Bereichs.** Ein TSDF-Volumen schließt
   seine Oberfläche dort ab, wo keine Daten mehr kommen. Diese Wand ist kein
   Gesicht – sie hat den Chamfer auf 1,4 mm hochgezogen und einzelne Punkte
   bis auf 54 mm. Erkennung: Nur Dreiecke behalten, deren Ecken **alle**
   wirklich gesehen wurden, und streifende Blicke (cos < 0,35) nicht zählen.
4. **Chamfer muss wissen, was sichtbar war.** Über die Fläche unter den Haaren
   eine Zahl auszurechnen ist Etikettenschwindel. Die Auswertung läuft jetzt
   zweistufig: Rekonstruktion → *sichtbare* Wahrheit, Wahrheit (≥ 5 Sichtungen)
   → Rekonstruktion.
5. **Marching Tetrahedra statt Marching Cubes**, weil 5 der 15 MC-Grundfälle
   mehrdeutig sind und Löcher erzeugen. Geprüft: die 6 Tetraeder füllen den
   Würfel exakt aus (Volumen 1,0) und schließen konform aneinander an.
6. **GLB-JSON muss mit Leerzeichen (0x20) aufgefüllt werden**, nicht mit Nullen
   – sonst lehnen strenge Parser die Datei ab.

**Bekannte Grenzen von M1:**
* Das Haar-Mesh ist ein Volumen auf 3-mm-Gitter (180k Dreiecke) – ohne
  Entrümpelung (Quadric Decimation, M2) noch zu groß fürs Handy.
* Der **Hinterkopf bleibt extrapoliert**: bei ±75° sieht ihn keine Kamera. Die
  IoU ist deshalb identisch für „beobachtet“ und „gesamt“ – der Unterschied
  steckt in der Dickenschranke, nicht in der Sichtbarkeit.
* Vertexfarben statt UV-Atlas: die Atlas-Packung (xatlas) kommt in M2, sie ist
  unabhängig von der Korrektheit der Schreiber.
* Export noch ohne FBX, USD/USDA/USDZ, Alembic, STL → nachgeholt in **M2 (§7)**.

## 7. M2: die restlichen Exportformate

`facescan_ref/export_more.py` schreibt und liest STL (binär und ASCII), USDA,
USDZ, **Collada (DAE 1.4.1)**, **binäres FBX 7.5** und **Alembic (Ogawa)**. Kein
assimp, keine Bibliothek – nur stdlib und NumPy, damit die Schreiber später 1:1
nach Kotlin und C++ portiert werden können.

Zu jedem Schreiber gehört ein Leser. Ein Test, der nur „Datei existiert“
prüft, beweist nichts.

| Format | Zweck | Größe | Rücklese |
|---|---|---|---|
| OBJ | Universaltausch | 22,2 MB | identisch bis 5e-7 mm |
| PLY (binär) | Punktwolken/Mesh | 6,7 MB | identisch bis 4e-6 mm |
| GLB (glTF) | Android-AR, Web | 6,5 MB | identisch bis 4e-6 mm |
| STL (binär) | 3D-Druck | 12,6 MB | 257.044 Facetten, 4e-6 mm |
| USDA | USD-Text, Pipeline | 17,6 MB | Indizes identisch, `metersPerUnit=0.001` |
| USDZ | Apple AR Quick Look | 17,6 MB | ZIP, ein Eintrag, unkomprimiert |
| DAE (Collada) | Alt-DCC, Support | 30,5 MB | Punkte identisch (0,0 mm), Indizes identisch |
| FBX 7.5 (binär) | Blender/Maya/Unity | 12,2 MB | 130.829 Punkte, Polygon-Konvention ok |
| Alembic (ABC) | Houdini/Nuke/Katana | 7,1 MB | `AbcGeom_PolyMesh_v1`, float32, 4e-6 mm |

Collada ist XML – deshalb ist `facescan_m1.dae` mit 30,5 MB die mit Abstand
größte Datei im Satz (rund 100 Byte je Dreieck, dagegen 26 Byte in FBX und
25 in GLB). Die LOD-Kette schreibt DAE deshalb nur für die gröbste Stufe
(`head_lod3.dae`, 0,85 MB); LOD0 käme auf rund 30 MB.

**Die Gegenprobe mit fremden Lesern** ist der eigentliche Ertrag von M2.
`validate_exports.py` öffnet jede Datei mit einem Programm, das wir nicht
geschrieben haben:

| Format | fremder Leser | Ergebnis |
|---|---|---|
| OBJ, PLY, GLB, STL | trimesh | bestanden |
| USDA, USDZ | `pxr` (Pixars USD-Referenz) | bestanden |
| Alembic (ABC) | echte Alembic 1.8.12 (`tools/abc_check.cpp`) | bestanden |
| FBX 7.5 | assimp | bestanden |
| DAE (Collada) | assimp **und** pycollada | bestanden |

**Acht echte Fehler, die erst die fremden Leser gefunden haben** – unser
eigener Rücklese-Test hatte alle acht durchgewinkt:

1. **FBX: `d` ist ein Array, `D` ist ein Double.** Großbuchstabe = ein Wert,
   Kleinbuchstabe = Array (Anzahl, Kodierung, Bytezahl, Daten). Wir hatten für
   alle skalaren Properties „i“ und „d“ geschrieben. assimp las daraufhin drei
   uint32 aus den Nutzdaten und landete im Nirgendwo:
   `FBX-Tokenize (offset 0x4b) cannot ReadWord, out of bounds`.
2. **FBX: der 25-Byte-Nullknoten steht HINTER den Kindern, nicht davor.** Mit
   einem Platzhalter vorn liest assimp ihn als Knoten mit EndOffset 0, rutscht
   8 Bytes weiter und synchronisiert irgendwann mitten in einem echten Knoten
   wieder auf: `block offset is out of range`.
3. **FBX: Knotennamen dürfen kein 0x00 enthalten.** Die Objekte im
   `Objects`-Abschnitt heißen schlicht `Geometry` / `Model`; der Name steckt in
   Property 1 und ist `Name 0x00 0x01 Klasse` – der Trenner ist **0x00 0x01**,
   nicht 0x00 0x00. Sonst: `unexpected NUL character in string`.
4. **FBX: `Vertices` und `PolygonVertexIndex` sind Unterknoten**, nicht
   Properties des Geometry-Knotens.
5. **Alembic: Byte 5 des Ogawa-Kopfes muss 0xff sein** („frozen“). Mit 0 lehnt
   die echte Bibliothek die Datei ab: *„Ogawa file not cleanly closed while
   being written“* – der Schutz gegen halb geschriebene Dateien.
6. **USDA: `%g` sind 6 signifikante Stellen.** Bei ±108 mm sind das 0,5 µm
   Rauschen; der Rücklese-Test schlug fehl, weil wir 4e-6 mm verlangten. Jetzt
   `%.17g`.
7. **STL: der Leser verglich in der falschen Reihenfolge.** Erst alle a, dann
   alle b, dann alle c statt a,b,c je Dreieck – ein Artefakt des Lesers, nicht
   des Schreibers, aber es hat eine Zeit lang einen echten Fehler vorgetäuscht.
8. **Collada: ein Material, das es nicht gibt.** Der erste Entwurf schrieb
   `<instance_material target="#face_material">` in jedem Fall, aber
   `library_materials` nur dann, wenn eine Textur dabei war. Ohne Textur
   zeigte der Verweis also ins Leere: assimp las die Datei kommentarlos,
   pycollada brach ab – *„Material #face_material not found“*. Seitdem wird
   die Material-Bibliothek immer geschrieben; ohne Textur tritt eine
   konstante Farbe an die Stelle der Texturkette.

**Bekannte Grenzen von M2:**

* **Alembic-Digests sind Nullen.** Die 16 Byte SpookyHash vor jedem Sample
  dienen nur `abcinfo` und dem Wiederverwenden identischer Samples; beim
  Öffnen prüft sie niemand. Wer sie braucht, muss SpookyHash V2 nachrüsten.
* **USDZ mit `.usda`-Nutzlast ist nicht AR-Quick-Look-fähig.** Apple
  verlangt ein binäres `.usdc`-Krate als primäres Asset. Wir schreiben absichtlich
  Text, weil ein eigener Krate-Schreiber ein Projekt für sich ist (M2b). Für
  Android-AR ist das unerheblich: dort ist **GLB** das Format.
* FBX hat keine Materialien und keine Texturen – nur Vertexfarben.
* **DAE ohne Rig und ohne Animation.** `library_controllers` (`<skin>`,
  `<morph>`) und `library_animations` fehlen – dafür fehlt in M2 die
  Bewegung selbst; beides kommt mit M3. Geometrie, Normalen,
  UVs/Vertexfarben und die Texturkette sind vollständig.

### 7b. M2b: Master-Mesh, globaler UV-Atlas, LOD-Kette, Textur-Bake

`tools/build_master.py` und `tools/build_lod.py` liefern das nach, was in
`docs/03` (6.2) für die Pro-Stufe steht und in M2 noch fehlte.

**Master-Mesh** (`facescan_master_uv.obj`, 156 MB): TSDF auf **0,75 mm** statt
1,5 mm (Haut) plus Haar-Volumen auf 1,2 mm ⇒ **742.081 Punkte / 1.463.676
Dreiecke**, 2771,7 cm², 0 entartete Dreiecke. 855 Inseln unter 500 Dreiecken
sind entfernt (`docs/03`, 6.2).

**Globaler UV-Atlas.** `facescan_ref/atlas.py` bindet **xatlas** ein und fällt
auf eine **Zylinderprojektion** zurück. Warum der Rückfall hier greift, ist
selbst ein Ergebnis:

* Auf dem 1,46-Mio.-Netz braucht xatlas **> 20 Minuten**. Ursache ist nicht
  die Menge, sondern die **Haut**: `refine_by_depth` erzeugt Sliver-Dreiecke
  bis 6·10⁻⁶ mm² (Median 0,096 mm²). Ein so schlecht konditioniertes Netz
  bringt den LSCM-Löser nicht zur Konvergenz. Die Haare mit ihren
  gleichmäßigen 0,18-mm²-Dreiecken laufen dagegen mit 0,06 ms je Dreieck.
* Das Haar-Volumen zerfällt für xatlas in ~34.000 Charts aus 100.000
  Dreiecken – jede 90°-Kante des Voxel-Netzes erzwingt eine Chart-Grenze.
  Auslastung ist mit 0,73 trotzdem gut, aber die Nahtlänge ist enorm.

Die Zylinderprojektion ist deshalb kein Notbehelf, sondern für einen Kopf die
**Standard-Parameterisierung** (`docs/03`, 11): `v` aus der Höhe statt aus dem
Polarwinkel ⇒ keine Polsingularität am Haarwirbel, und die Naht liegt bei
180°, also hinten unter den Haaren. 3,92 Texel/mm = **0,255 mm je Texel**.

**LOD-Kette** (Garland-Heckbert, `meshopt.quadric_decimate`). Formfehler
gemessen gegen das Master-Netz mit `metrics.surface_deviation`
(Punkt-zu-Dreieck, nicht Punkt-zu-Punkt):

| Stufe | Dreiecke | Punkte | Formfehler | p95 | max | entartet | GLB | OBJ | USDZ |
|---|---|---|---|---|---|---|---|---|---|
| LOD0 | 299.998 | 161.792 | **0,035 mm** | 0,165 | 1,29 | 3.152 | 8,6 MB | 30,1 MB | 24,9 MB |
| LOD1 | 80.000 | 45.182 | **0,152 mm** | 0,536 | 1,59 | 4 | 2,6 MB | 7,8 MB | 7,1 MB |
| LOD2 | 20.000 | 12.023 | **0,285 mm** | 0,784 | 4,19 | 0 | 0,9 MB | 1,9 MB | 2,0 MB |
| LOD3 | 5.999 | 3.849 | **0,396 mm** | 1,071 | 6,64 | 0 | 0,5 MB | 0,6 MB | 0,8 MB |

Die UVs wandern über alle Stufen mit (`uv_weight`), weil sonst Kanten über
Chart-Abstände hinweg zusammengefasst würden und die Textur über die Lücke
zöge.

**Globaler Bake** (`facescan_ref/bake.py`). Statt pro Vertex die beste Kamera
zu wählen, wird **pro Texel** aus allen sichtbaren Kameras cos²-gewichtet
gemischt. Ergebnisse für die 2048²-Textur:

* 96,4 % der Atlasfläche sind belegt, im Mittel tragen **3,3 Kameras** je
  Texel bei, 42,8 % der Texel sogar drei oder mehr.
* Sichtbare Farbsprünge zwischen benachbarten Texeln (> 20/765):
  **0,76 % → 0,54 %** gegenüber dem alten Vertex-Weg.
* **21,4 % der Atlasfläche tragen echte Farbe**, 78,6 % sind aufgefüllt.
  Das ist keine Messung mehr, sondern Extrapolation aus dem nächsten
  sichtbaren Texel – die 16 Aufnahmen decken nur ±75° Gierwinkel ab, der
  Hinterkopf war in keinem Bild. `docs/03` (7.1) sagt genau das voraus; die
  App weist diese Bereiche als „geschätzt“ aus.

Der Gewinn gegenüber dem alten Weg ist **kleiner als erwartet**, und das ist
ehrlich zu sagen: `texture_completeness` hat bereits über alle sichtbaren
Kameras gemittelt. Was der Bake bringt, ist die vierfach feinere Farbe
(0,255 mm je Texel statt ~1 mm je Vertex) und die cos²-Wichtung statt der
Gleichgewichtung – nicht die Rettung vor einem kaputten Verfahren.

**Ein Fehler, den erst dieser Schritt gefunden hat:** `_MeshState` in
`meshopt.py` legte Dreiecke **sortiert** ab (`np.sort`) statt **zyklisch
gedreht**. Sortieren verliert die Umlaufrichtung. Der Dezimierer lieferte
also Netze, in denen ein Teil der Dreiecke auf links stand – und zwar durch
jeden Test hindurch, der nur Koordinaten und Indizes vergleicht. Erst
xatlas hat es gesehen: **20.753 Charts aus 25.000 Dreiecken**, weil es die
Nachbarschaft nicht mehr erkannte. Jetzt: `canon3()` dreht, `winding_errors()`
prüft, `orient_mesh()` heilt (235.526 falsch laufende Kanten im Rohnetz → 0).

### 7c. Gegenprobe mit fremden Lesern (M2 + M2b)

`validate_exports.py` öffnet **24 Dateien** mit trimesh, `pxr`, echter
Alembic-Bibliothek, assimp und pycollada: **24 von 24 bestanden**, 22 davon
von einem fremden Leser gelesen (CSV und JSON prüft die Standardbibliothek –
eine Tabelle zu lesen, ist keine Frage des Programms).

* **Normalen** in OBJ, PLY, USDA, USDZ, ABC – gelesen von trimesh, pxr und
  Alembic (`N=130829 scope='3'` = `vtx`, längste Normale 1.0000). STL trägt
  bewusst keine (nur die Flächennormale im 50-Byte-Satz).
* **UV + Textur** in allen 13 LOD-Dateien: trimesh dekodiert das eingebettete
  PNG (2048×2048 px), pxr findet `primvars:st` und die vollständige
  Shader-Kette `UsdPrimvarReader_float2 → UsdUVTexture → UsdPreviewSurface`.
* **FBX-Normalen sind die einzige Lücke**: `assimp info` meldet nur Zählwerte,
  und der Test-Build hat den Export abgeschaltet – ein Urteil „fehlt“ wäre
  hier gelogen. Geprüft werden sie von unserem eigenen Leser.
* **DAE (Collada)** wird von **zwei** fremden Lesern geprüft, weil die beiden
  unterschiedlich streng sind: assimp zählt die Geometrie (M1 130.829
  Vertices / 257.044 Faces, LOD3 6.970 / 5.999), pycollada löst zusätzlich
  die Materialkette `image → sampler2D → surface → lambert` auf und meldet
  jeden Verweis, der ins Leere zeigt. pycollada ist als einziges Paket eine
  reine Python-Abhängigkeit (`pip install pycollada`); fehlt es, sagt der
  Prüfer das offen, statt die Lücke als bestanden zu melden.

**USDZ mit binärem Crate (`facescan.usdc`)** – seit diesem Stand schreiben
alle vier LOD-Pakete als Root-Layer ein Crate statt Text, weil Apple-Geräte
ein Paket mit Text-Root-Layer ablehnen (Reality Converter: „the package's
root layer must be a usdc file“). Der Inhalt kommt weiter aus dem eigenen
USDA-Schreiber; die Serialisierung übernimmt die USD-Bibliothek
(`export_more.usda_to_usdc`). Das Crate-Format von Hand zu schreiben, wäre
ein eigenes Projekt mit eigenem Versionsrisiko – und brächte für den Scan
nichts. pxr liest die Pakete unverändert: `facescan.usdc` mit Kennung
`PXR-USDC`, `primvars:st`, PNG im ZIP und die vollständige Shader-Kette.

| Paket | vorher (Text) | jetzt (Crate) |
|---|---|---|
| `head_lod0.usdz` | 24,9 MB | **7,0 MB** |
| `head_lod1.usdz` | 6,9 MB | **2,1 MB** |
| `head_lod2.usdz` | 2,4 MB | **0,76 MB** |
| `head_lod3.usdz` | 0,84 MB | **0,43 MB** |

Ausnahme: `facescan_m1.usdz` behält den **Text**-Root-Layer. Die M1-Tore
prüfen den Inhalt mit dem eigenen Leser, und der liest Text; die AR-Ausgabe
sind die vier LOD-Pakete.

**Collada (DAE 1.4.1)** – `export_more.write_dae` schreibt
`unit meter="0.001"` und `up_axis Y_UP` im `<asset>`-Block (nicht am Knoten:
sonst kommt der Kopf 1000-fach zu groß und liegend an), Quellen für
Positionen, Normalen und UVs – beim M1-Netz Vertexfarben statt UVs – und
jede Quelle mit `<float_array>` **und** `<accessor>`. Die Indizes in `<p>`
stehen pro Ecke, und ihre Spaltenreihenfolge folgt den `<input>`-Zeilen
(VERTEX, NORMAL, TEXCOORD auf offset 0, 1, 2 = neun Zahlen je Dreieck).
Rücklese mit dem eigenen Leser: Punkte und Indizes identisch, Farben
identisch (0,0e+00/255). Die LOD-Kette schreibt nur LOD3 als DAE
(0,85 MB), aus dem oben genannten Grund.

Dabei aufgefallen und korrigiert: die 64-Byte-Ausrichtung galt bisher nur
für den **ersten** Eintrag im ZIP. Die Polsterung über das Extra-Field
wurde aus der Länge des Dateinamens berechnet statt aus der laufenden
Position – damit landete die Textur im Paket auf einer beliebigen Adresse,
sobald die Nutzlast kein Vielfaches von 64 war. Gemessen an den vier
LOD-Paketen traf es dreimal von vier Dateien nicht zu, und zwar unbemerkt:
der Prüfer sah nur auf den ersten Eintrag. Jetzt liegen die Datenanfänge
bei 64 und 6.836.608 Byte (LOD0), beide glatt durch 64.

Und ein Fehler im **eigenen** Leser, den nur der Abgleich mit den fremden
aufdeckte: `read_dae` suchte die `<source>`-Blöcke mit einem regulären
Ausdruck, und `id="\w+"` passt nicht auf `positions-array` – `\w` kennt den
Bindestrich nicht. Die Quellenliste blieb deshalb immer leer, ohne
Fehlermeldung. Jetzt liest `read_dae` die Datei mit
`xml.etree.ElementTree`; ein XML-Format liest man mit einem XML-Parser.

### 7d. M2b, Teil 2: die wasserdichte Variante (`build_watertight.py`)

Das Netz aus Marching Tetrahedra ist **offen**: wo keine Kamera hinsah, endet
die Fläche einfach. Für 3D-Druck und Boolesche Operationen braucht es eine
geschlossene Hülle. `tools/build_watertight.py` rechnet sie in den drei
Schritten, die docs/03 (6.2) vorgibt; die Werkzeuge dazu liegen in
`facescan_ref/repair.py`.

| Schritt | gemessen |
|---|---|
| Hautnetz (TSDF 1,5 mm) | 40.409 Punkte / 76.208 Dreiecke, 132 Komponenten, 4.712 Randkanten |
| 1) Loch-Füllung ≤ 3 mm | von 345 Schleifen 45 geschlossen (59 Dreiecke); 300 zu groß, größte 2.402 mm Umfang; 5.135 mm Rand bleiben offen |
| 2) Taubin, 3 Iterationen | Fläche 270,0 → 220,7 cm² (−18,3 %), Abstand zum Original **0,109 mm** im Mittel (max 1,08) |
| 3) Poisson, 192³-Gitter | 227.867 Punkte / 455.730 Dreiecke, **0 Randkanten, 0 nicht-manigfaltige Kanten, 1 Komponente, Euler-Charakteristik 2** |
| Gegenprobe trimesh | `is_watertight = True`, `euler_number = 2`, Volumen 735,9 cm³ (eigene Rechnung: 735,9 cm³) |
| Abstand Hautnetz → Ergebnis | 0,201 mm im Mittel |

Drei Dinge daran sind nicht selbstverständlich, und alle drei haben im ersten
Lauf zu einem falschen Ergebnis geführt:

1. **Das Iso-Level darf nicht auf einen Gitterknoten fallen.** Tut es das,
   liegt der Schnittpunkt genau auf dem Knoten, und mehrere Tetraeder
   desselben Würfels erzeugen dasselbe Dreieck. Gemessen: 528 Kanten, deren
   zwei Nachbarn **gleichsinnig** durchlaufen werden – topologisch sind das
   gedrehte Dreiecke. `poisson_grid` schiebt deshalb alle Feldwerte, die
   betragsmäßig unter 1e-5 der Amplitude liegen, aus dem Nullbereich heraus
   (34 von 7 Mio. Knoten), und `meshopt.orient_mesh` richtet danach die
   Umlaufrichtung per Breitensuche aus (528 → 0). Vorher blieb das Netz an
   106 Stellen offen, obwohl die Kanten zählten, als wäre alles dicht.
2. **Poisson erzeugt Inseln.** Wo eine Kamera mal ein paar Pixel weit in die
   Luft gemessen hat, entsteht eine eigene kleine geschlossene Blase: 10
   Stück, neun davon Rauschen (zusammen 900 Dreiecke, größte 236). Wir
   behalten die größte. Vor dem Aufräumen stand da ein „Formfehler" von 6,1 mm
   im Mittel (p95 30 mm) – das war der Abstand zu den Rauschblasen, nicht zur
   Form.
3. **Welche Richtung man misst, entscheidet über die Aussage.** Der Abstand
   Ergebnis → Hautnetz ist 6,7 mm und damit wertlos: er misst die Rückseite
   der geschlossenen Blase, also genau die Oberfläche, die es in den Aufnahmen
   nicht gab. Nur Hautnetz → Ergebnis (0,201 mm) ist eine Aussage über die
   Rekonstruktion. Beide Richtungen zu einem Mittelwert zu verrechnen, hieße,
   das Verfahren dafür zu bestrafen, dass es eine fehlende Rückseite
   geschlossen hat.

Zwei Ehrlichkeiten dazu, die man sonst beim Lesen der Tabelle verpasst:

* `docs/03` nennt Octree-Tiefe 10–12. **Wir rechnen auf einem regelmäßigen
  192³-Gitter** (Kantenlänge 0,91 mm) und weisen das als Kennzahl aus, statt
  eine Tiefe vorzutäuschen, die wir nicht rechnen. Tiefe 10 wären 1024³ Voxel.
  Das Verfahren ist dasselbe (Kazhdan et al. 2006), nur die Datenstruktur ist
  einfacher – und die Poisson-Gleichung löst sich im Frequenzraum, weil das
  Gitter regelmäßig ist (eine Division pro Frequenz, 5,5 s statt Tausender
  Jacobi-Iterationen).
* Die Taubin-Glättung nimmt der Fläche 18,3 %. Das ist kein Schrumpf, sondern
  das Treppenmuster des Voxelgitters, das verschwindet – eine Treppe hat mehr
  Fläche als die Rampe, die sie annähert. Die Zahl, die wirklich zählt, ist
  der Abstand zum Original: **0,109 mm**. Nachgemessen am Ikosaeder
  (r = 50 mm, 642 Punkte / 1280 Dreiecke; exakte Kugel 523.598,8 mm³,
  Startnetz 519.085,6 mm³): nach 3 Iterationen reines Laplace 468.071 mm³
  (−9,8 %) gegen Taubin 520.480 mm³ (+0,3 %); nach 20 Iterationen Laplace
  261.936 mm³ (−49,5 %) gegen Taubin 528.518 mm³ (+1,8 %). Taubin schrumpft
  nicht, es rundet die Fläche zur Kugel – deshalb der negative
  Schrumpffaktor µ = −0,53.

Wie viel davon ergänzt ist, zeigt `tools/preview_watertight.py`
(`results/watertight_preview.png`, vier Ansichten, offenes Netz links,
geschlossenes rechts; Rückseiten sind verworfen, damit Löcher als Löcher
erscheinen). Deckung der Bildfläche, beide Netze im selben Maßstab:

| Ansicht | offenes Hautnetz | geschlossene Variante |
|---|---|---|
| von vorn | 28,3 % | 30,7 % |
| seitlich | 20,8 % | 27,1 % |
| von hinten | **0,9 %** | 28,4 % |
| von hinten oben | **1,0 %** | 30,2 % |

Von vorn sind es 8 % Unterschied, von hinten 97 %: die Rückseite des Kopfes
ist im wörtlichen Sinne **ergänzt**, nicht gemessen. Wer das Ergebnis
druckt, druckt dort eine glatte Vermutung. Das ist die ehrliche Beschreibung
dessen, was ein 16-Kamera-Orbit mit ±75° Gier hergeben kann – und der Grund,
warum die Rückseite nicht als Formfehler in die Kennzahlen eingeht.

Offen an dieser Stelle: eine Sockel- und Wandstärkenprüfung für den Druck
(das Netz ist geschlossen, aber nichts prüft bisher, ob eine Wand stark genug
ist), und 8 Dreiecke liegen mit einer kürzesten Kante von 1,4e-5 mm unter der
Nachweisschwelle für Fläche – sie stören die Wasserdichtheit nicht, ein
Slicer kann aber darüber stolpern.

### 7e. M2b, Teil 3: Sockel und Druckprüfung (`build_print.py`)

Ein geschlossenes Netz ist noch kein druckbares. Es hat keine Standfläche,
und niemand hat gemessen, ob irgendwo ein Nasenflügel dünner ist als eine
Düse breit. `tools/build_print.py` setzt den Sockel an und rechnet die drei
Prüfungen, die docs/05 (12.2) verlangt. `facescan_ref/printcheck.py`
enthält die Messungen.

**Der Sockel entsteht am Feld, nicht am Netz.** Unterhalb der Schnitthöhe
wird das Indikatorfeld durch einen Kegelstumpf ersetzt; danach läuft
derselbe Marcher noch einmal. Dadurch verschmelzen Kopf und Sockel zu
*einem* Körper – ohne Boolesche Operation, ohne Naht, ohne Netzreparatur.
Ein Netz zu zerschneiden hieße, danach Löcher zu flicken und
Umlaufrichtungen zu reparieren.

| Schritt | gemessen |
|---|---|
| Querschnittsprofil | Kopf reicht von z = −31,1 mm bis 99,3 mm, größter Querschnitt 121 cm² bei z = 36 mm |
| Schnitthöhe (Regel: tiefste Stelle mit ≥ 25 % des Maximums) | z = 0,8 mm, Querschnitt dort 33,4 cm² |
| Achse | der Halsausschnitt sitzt **34,1 mm neben der Gittermitte** – der Kopf steht schief im Gitter |
| Sockel | r = 58,0 mm auf 70,0 mm, 35 mm hoch, Standfläche bei z = −34,2 mm |
| Ergebnis | 387.431 Punkte / 774.858 Dreiecke, Volumen 1171,2 cm³, 134,5 mm hoch |
| Gegenprobe trimesh | `is_watertight = True`, `euler_number = 2`, Volumen 1171,2 cm³ |

Prüfungen, Kopf gegen Büste:

| Prüfung | Kopf | Büste |
|---|---|---|
| Standfläche | **0,00 cm²** – steht nicht | 152,1 cm², Ebenheit 0,00 mm |
| Schwerpunkt neben der Mitte / Rand der Standfläche | – | 18,6 mm / 51,2 mm → **steht** |
| kleinste lokale Dicke (ohne Nadeldreiecke) | 1,83 mm | 1,82 mm |
| p01 / p05 / median der Dicke | 8,4 / 35,2 / 83,4 mm | 2,0 / 12,9 / 81,7 mm |
| Überhänge steiler als 45° | 111,3 cm² (24,4 %) | 227,1 cm² (27,9 %) |

Vier Dinge, die beim ersten Lauf schiefgegangen sind und die man sonst
nirgends nachlesen kann:

1. **Der Sockel braucht mehr Platz, als das Gitter hergibt.** Der Kopf ist
   55 mm dick an der Schnittebene, aber 34 mm neben der Gittermitte –
   zusammen 89 mm, bei 87 mm Platz bis zum Rand. Der erste Sockel lief über
   den Gitterrand, wurde abgeschnitten und das Ergebnis war offen (1.076
   Randkanten). Gelöst durch seitliches **Erweitern des Feldes** (21 Zellen,
   192³ → 234×234×192) statt die Rekonstruktion auf einem gröberen Gitter
   zu wiederholen – die Kantenlänge von 0,91 mm bleibt dabei, was sie war.
2. **Die Achse ist die Schnittebene, nicht das Gitter.** Wer den Sockel auf
   die Gittermitte stellt, bekommt bei schief stehendem Kopf einen Sockel
   von 70 mm Radius für einen 30 mm dicken Hals.
3. **Der Radius wird am Netz gemessen, nicht am Feld.** Das Feld enthält zu
   jeder Rauschmessung in der Luft eine kleine Insel, und der *weiteste*
   Innenknoten einer Schicht war beim ersten Versuch so eine Insel: 75 statt
   30 mm.
4. **Flächennormalen sind flächengewichtet** (`meshopt.face_normals`, Länge
   = 2 × Fläche). Wer damit einen Strahl um `s` Millimeter weiterlaufen
   läßt, kommt nur halb so weit und mißt die doppelte Dicke. Auf der Kugel
   r = 30 mm hat das 120 statt 60 mm ergeben – unauffällig genug, um es für
   eine echte Messung zu halten. Geprüft wird gegen die Kugel: 59,97 mm bei
   einem Soll von 60,00 mm.

Offen bleibt: die Schreib- und LOD-Seite ist fertig, und auch die Bewegung
sitzt — Rig, Blendshapes und VRM sind in M3 dazugekommen. → siehe Kap. 7i.
Was fehlt, sind allein die restlichen 46 ARKit-Mimiken (§12.2).

### 7i. M3: Rig, Animation und VRM (`build_rig.py`, `build_vrm.py`)

Ein Netz aus 300.000 Dreiecken ist starr. Damit der Kopf nicken, den Mund
öffnen oder in eine Richtung schauen kann, braucht er ein Skelett und je Punkt
die Angabe, wie stark welches Gelenk ihn bewegt. `facescan_ref/rig.py`
bestimmt beides **aus dem Netz selbst** — und prüft es gegen die bekannte
Wahrheit, denn das synthetische Kopfmodell liegt im Ursprung, unverdreht, im
Maßstab 1.

| geprüft | Ergebnis |
|---|---|
| Blickrichtung | **exakt** (Fit-Minimum bei −90,0°) |
| Kopfmitte | **0,4 mm** neben der Wahrheit |
| Maßstab | 1,0013 (0,13 % Abweichung) |
| Restfehler Modell ↔ Scan | 0,43 mm (Median) |
| Landmarken (Nase, Kinn, Augen …) | 0,16 … 1,13 mm |
| Hautgewichte | Summe je Punkt genau 1, größter Sprung zwischen Nachbarpunkten 0,05 |

Zu jeder Achse gibt es **zwei unabhängige Schätzungen**, die sich prüfen:
„oben" aus der Schnittfläche unten und aus dem Modell-Fit mit geneigter
Achse; „vorn" aus dem Modell-Fit und aus dem gemessenen Nasenüberstand
(5° auseinander); seitlich aus der Spiegelsymmetrie. Die Trägheitsachse
taugt dabei ausdrücklich **nicht** — ein Kopf ist fast so breit wie hoch
(220 zu 213 mm), die Hauptachsen liegen deshalb zu dicht beieinander
(gemessen: 78° Abweichung).

Drei Fallen, die hier drinstecken und anderswo gern übersehen werden:

1. **Die Maske darf sich beim Optimieren nicht bewegen.** Wird die
   Gesichtsmaske bei jedem Probeschritt neu bestimmt, jagt die Optimierung
   ein Ziel, das sich unter ihr verändert — sie blieb 4° und 2,4 mm neben der
   Wahrheit stehen. Richtig: Korrespondenzen festlegen, lösen, neu zuordnen
   (wie bei ICP).
2. **Über alle 360° gesucht gewinnt der Hinterkopf.** Er ist glatt und passt
   deshalb besser zum glatten Modell als Nase und Kinn. Das Vorzeichen
   „vorn gegen hinten" muß der maskenfreie Fit entscheiden.
3. **Collada-Matrizen stehen zeilenweise, glTF-Morphs sind Verschiebungen.**
   Wer Morph-Ziele als Zielpositionen schreibt oder die Einheit verwechselt,
   bekommt ein Modell, das beim Lächeln auseinanderfliegt.

Ergebnis: acht Gelenke (`hips → spine → chest → neck → head → jaw/leftEye/
rightEye`, nach VRM benannt) und drei Dateien, alle von fremden Lesern
geprüft:

| Datei | Inhalt | Prüfung |
|---|---|---|
| `facescan_rig.dae` | `library_controllers` mit `<skin>` | pycollada löst die Kette auf, assimp zählt **5 Knochen** |
| `facescan_rig.bvh` | echtes Skelett statt Aufnahmebahn, 120 Frames | assimp: **1 Animation, 8 Kanäle** |
| `facescan_rig.glb` | **6 Morph-Ziele** in ARKit-Benennung | 5,0 mm größte Verschiebung, min/max stimmt |

Bei der Mimik bleibt der Prototyp ehrlich: ARKit kennt 52 Formen, geliefert
werden die **sechs**, zu denen das 3DMM eine Ausdrucksrichtung besitzt
(`jawOpen`, `mouthSmile`, `eyeBlink`, `browInnerUp`, `browDown`,
`mouthPucker`). Die restlichen 46 aus diesen abzuleiten wäre erfunden — echte
Gesichter lächeln nicht spiegelsymmetrisch.

**VRM 1.0 (`build_vrm.py` → `meshes/facescan.vrm`, 21 MB)** ist der letzte
der vier M3-Posten. VRM ist kein eigenes Format, sondern glTF 2.0 mit
angehängter Erweiterung `VRMC_vrm` — es braucht also keinen eigenen Writer,
nur denselben GLB-Schreiber plus den Erweiterungsblock.

Das Skelett wächst von 8 auf **23 Gelenke**, und zwar so, dass nichts
gemessenes verlorengeht: Hals bis Augen werden unverändert übernommen, Rumpf
und Gliedmaßen sind aus der gemessenen Kopfhöhe abgeleitet (Kinn bis
Scheitel), nicht aus festen Zentimetern. Ergebnis: 1,28 m Körpergröße = 7,8
Kopfhöhen, Füße auf Y=0, Arme waagerecht — die T-Pose, die `tpose.md`
verlangt. Damit ist die Büste gültig VRM.

Und hier die Entscheidung, die man kennen muß, bevor man die Datei benutzt:
VRM verlangt 15 Pflichtknochen, **darunter Arme und Beine**. Eine Büste hat
keine. Die Gelenke sitzen anatomisch plausibel und tragen **keine
Hautgewichte** — Gewicht tragen genau drei Gelenke (`neck`, `head`, `jaw`).
Die Datei ist damit gültig und verhält sich doch wie eine Büste: die Arme
bewegen sich, es sieht nur niemand. Das ist ehrlicher als erfundene Beine
unter dem Hals.

Weil die Sohle auf Y=0 steht und nicht die Büste, schwebt der Kopf auf
1,11 m Höhe. Wer die Büste auf dem Tisch haben will, zieht die Verschiebung
von **1186 mm** wieder ab; sie steht in `results/vrm_report.json`.

| VRM-Prüfung | Ergebnis |
|---|---|
| Pflichtknochen (15) | alle vorhanden, **keiner fehlt** |
| `humanBones` → Knoten | jeder Knochenname steht auf dem gleichnamigen Knoten |
| T-Pose | Sohle auf **Y = 0,000 m**, Arme seitlich, Höhenunterschied 9 mm |
| `meta` | Name, Autor, `licenseUrl = https://vrm.dev/licenses/1.0/` |
| Ausdrücke | 6 Presets (`happy`, `angry`, `surprised`, `blink`, `aa`, `oh`) |
| `lookAt` | `bone` — dreht die beiden Augengelenke |

Vier neue Fallen, alle in `docs/05` (Fundstellen 51–54) festgehalten:
`humanBones` zählt **Knoten, nicht Gelenke** (um eins verschoben lädt die
Datei anstandslos, sitzt aber falsch); die **Sohle** steht auf 0, nicht das
Fußgelenk; **+X ist links** (Seite des Avatars), was `headmesh` umgekehrt
benennt und uns einmal die Augengelenke vertauscht hat; und glTF-Matrizen
stehen spaltenweise, während Gelenkknoten ihre Verschiebung **relativ zum
Elterngelenk** rechnen.

Damit ist M3 vollständig: DAE mit Haut, BVH mit Skelett, GLB mit Mimik, VRM
als Ganzes. Offen bleibt nur noch eins — die restlichen 46 ARKit-Formen, und
die sind eine Frage des 3D-Modells, nicht des Exports (§12.2).

### 7h. M2b, Teil 6: das Drucknetz vereinfachen (`build_print_lod.py`)

`docs/05` (12.2) verlangte zuletzt eine vereinfachte Druckfassung **mit einer
Formfehlergrenze**. Gesucht wird deshalb nicht die Fassung mit einer bestimmten
Dreieckszahl, sondern die **gröbste, die eine Grenze einhält** — und die Zahl,
die am Ende herauskommt, sagt etwas über das Ergebnis.

| Grenze | massiv | hohl |
|---|---|---|
| p95 Formfehler ≤ 0,10 mm | 0,090 | 0,094 |
| p99 ≤ 0,35 mm | 0,288 | 0,290 |
| Fläche über 0,5 mm ≤ 1 % | 0,19 % | 0,19 % |
| Wand p01 ≥ 1,2 mm | – | 1,60 |
| Ablaufloch ≥ 4 mm frei | – | 4,6 |
| dicht im Speicher | 0 Randkanten, Euler 2 | 0 Randkanten, Euler 2 |
| dicht in der DATEI (trimesh) | `True`, Euler 2 | `True`, Euler 2 |

Ergebnis `meshes/facescan_print_lod.stl`: 50.368 Punkte / **100.732 Dreiecke,
87 % gespart** (4,9 MB statt 38,7). `meshes/facescan_print_lod_hollow.stl`:
94.912 / **189.820, 84 % gespart** (9,3 MB statt 59,3). Volumen 1171,5 statt
1171,2 cm³, Standfläche 151,0 cm², Überhang 27,9 % — alles wie am massiven
Netz gemessen, nur 0,5 mm Ebenheit der Standfläche statt 0,00 mm: die scharfe
Kante unten am Sockel wird beim Vereinfachen rund, und die Meßzahl greift
jetzt die Schräge der Randdreiecke mit. Das gedruckte Teil steht trotzdem,
weil der Slicer an der Platte schneidet.

Fünf Fehler lagen im Weg, und alle fünf saßen im Zusammenfasser selbst:

1. **`_MeshState._unlink` hat Kanten aus der Nachbarliste eines Punktes
   entfernt, die noch ein anderes Dreieck benutzte** — `discard` stand
   außerhalb der Abfrage, ob die Kante wirklich keinem Dreieck mehr gehört.
   Die Liste der Dreiecke um einen Punkt wurde Zug um Zug kürzer, und beim
   Zusammenfassen blieben Dreiecke übrig, die niemand mehr kannte: **8.660
   Randkanten, 1.805 nicht-manigfaltige Kanten und 255 Einzelteile aus einem
   Stück** nach einer harmlosen Vereinfachung von 775 k auf 300 k.
2. **Die Nachbarschaftsbedingung fehlte.** Ohne `lk(u) ∩ lk(w) = lk(uw)`
   entsteht eine Kante mit vier Nachbarn, und das Netz ist nicht mehr dicht,
   obwohl es genauso aussieht wie vorher.
3. **Geprüft wurde nur um den sterbenden Punkt herum.** Die Dreiecke am
   ÜBERLEBENDEN Punkt wandern mit und ändern sich genauso — wer sie nicht
   prüft, läßt jedes Dreieck wachsen, das zufällig immer dort hängt. Genau so
   ist dem Ablaufloch der Boden über den Kopf gezogen worden. Beim Umbau
   dürfen dagegen nur die Dreiecke am sterbenden Punkt angefasst werden;
   beides in einen Topf zu werfen, tötet Mitwanderer zweimal (Euler −4407).
4. **Eine ebene Fläche vereinfacht sich kostenlos** und pflastert damit jedes
   Loch zu, das in ihr liegt. Der Boden des Hohlraums ist eine waagerechte
   Scheibe mit dem Ablaufloch in der Mitte; drei Punkte im Abstand von 120°
   ergeben ein Riesendreieck darüber, und der Hohlraum ist ein geschlossenes
   Gefäß — wasserdicht und undrainiert. Punkte am Loch festzuhalten hilft
   nicht (die drei Ecken dürfen weit weg liegen); ein **Sperrgebiet** hilft.
5. **Und die Datei:** STL speichert 32-Bit-Zahlen, und das Optimum der Quadrik
   fällt oft fast genau auf einen schon vorhandenen Punkt — zwei Punkte, im
   Speicher 1e-14 mm verschieden, sind in der Datei identisch. 14 Paare
   genügten für Euler 17 und `is_watertight = False`. Gerückt wird nur, wo es
   sein muß: jede Lage auf 32 Bit zu runden, kostet 40 % Formfehler, weil es
   den ganzen weiteren Ablauf ändert.

Zwei Meßfehler kamen dazu: der Formfehler an den VERTICES ist eine Tautologie
(die Vertices eines vereinfachten Netzes sind Punkte des Originals — p95
0,0015 mm, egal wie grob; flächengewichtet sind es 0,082 mm), und das Maximum
ist als Grenze unbrauchbar, weil es an einer Haarspitze sitzt und mit der
Stichprobe wandert. Gezählt wird der ANTEIL über einer Grenze.

### 7g. M2b, Teil 5: der Hohlkörper (`build_hollow.py`)

`docs/05` (12.2) verlangte zuletzt eine **Wandstärkenprüfung am Hohlkörper**
– die letzte offene Stelle im Druckpfad. Dafür muß es erst einen Hohlkörper
geben: `facescan_print_hollow.stl`, eine Schale mit 2,4 mm Wand, massivem
Sockel und einem Ablaufloch von 10 mm durch die Standfläche.

| geprüft | gemessen |
|---|---|
| Volumen | 1171,2 cm³ massiv → **541,8 cm³ hohl**, 54 % gespart |
| Wandstärke (Ray-Cast, 9.812 Proben am Kopf) | median **2,34 mm**, p05 1,82, p01 **1,58** mm |
| Wand unter der 1,2-mm-Grenze | **0,04 %** der Kopfoberfläche (4 von 9.812 Proben) |
| Wasserdicht (eigener Prüfer) | 0 Randkanten, 0 nicht-manigfaltig, 1 Komponente, Euler 2 |
| Wasserdicht (trimesh) | `is_watertight = True`, `euler_number = 2`, Volumen 541,8 cm³ |
| Ablaufloch | Strahl vom Boden durch das Loch in den Hohlraum: 200 von 200 Proben außen |

Vier Entscheidungen, und jede hat einen Grund:

1. **Gefaltet wird das Feld, nicht das Netz.** `printcheck.shell_field` setzt
   `phi = max(field − level, abstand − wand)`. Außen ist damit `phi` genau das
   ursprüngliche Feld – die sichtbare Oberfläche bleibt bitgleich die der
   massiven Büste. Ein Netz um 2,4 mm nach innen zu schieben, überlappt sich
   an Haaren und Ohren selbst, weil der Versatz dort größer ist als die örtliche
   Dicke. Eine Isofläche kann sich nie selbst schneiden: wo kein Platz ist,
   schnürt der Hohlraum ab.
2. **Der Sockel bleibt massiv.** Er ist der Teil, auf dem das Gewicht steht;
   hohl würde die Büste oben schwerer und kippeliger. Das Aushöhlen gilt nur
   oberhalb der Schnitthöhe.
3. **Ohne Ablaufloch ist ein Hohlkörper ein Gefäß.** Harz bleibt darin und das
   Teil reißt später auf; Pulver bekommt niemand heraus. Das Loch liegt in der
   Standfläche, wo es nachher niemand sieht.
4. **Die Wand wird kalibriert, nicht gesetzt.** Der Abstand kommt vom Gitter
   (`band_distance`), und nachgemessen wird per Strahl. 2,4 mm ist die dünnste
   Wand, deren 1-%-Quantil noch über der 1,2-mm-Grenze liegt.

Fünf Dinge, die beim ersten Lauf schiefgegangen sind:

1. **Das Feld läßt sich nicht falten.** Der erste Versuch war eine Isofläche im
   Abstand `delta / |grad f|` – elegant und falsch: das Poisson-Feld ist bis auf
   etwa 1,5 mm gesättigt, `|grad f|` fällt dort praktisch auf null. Bei 0,5 mm
   Tiefe stimmt die Schätzung noch (0,59 statt 0,50 mm), bei 2,0 mm liefert sie
   14 mm. Der Abstand muß über das Gitter kommen.
2. **Der Randknoten sitzt eine halbe Gitterkante VOR der Fläche.** Der reine
   Knotenabstand mißt bei 1,0 mm Tiefe 0,54 mm und bei 2,0 mm 1,50 mm. Mit der
   halben Kante: 1,00 und 1,96 mm.
3. **Der massive Sockel verschleppt jeden Median.** 42 % der Proben liegen auf
   dem Sockel und messen dort 35 mm. Die Wand wird nur am Kopf gemessen.
4. **Die Nadelschwelle kann keine Konstante sein.** Vier Gitterkanten sind für
   einen massiven Körper richtig; hier verwirft sie 48 % der Messungen, weil die
   Wand selbst dünn ist.
5. **Euler = 2 heißt hier nicht „massive Kugel".** Eine Schale mit einem Loch
   hat dieselbe Euler-Charakteristik. Die Verbindung nach außen prüft deshalb
   ein Strahl, nicht die Topologie.

### 7f. M2b, Teil 4: die Aufnahmebahn als BVH, CSV und JSON (`build_motion.py`)

docs/05 (4.8) verlangt drei Motion-Formate. Was M2 an Bewegung hat, ist nicht
der Rig – der kommt mit M3 – sondern **die Aufnahme selbst**: 16 Kameraposen
auf einem Bogen um den Kopf. Und eine Kamerapose (R, t) mit `p_cam = R p + t`
ist genau die Transformation, die der Kopf relativ zur Kamera erfährt.
Umgerechnet heißt das: die Kamera steht fest und der Kopf dreht sich auf einem
Drehteller, durch genau die 16 Lagen, aus denen gemessen wurde. Das ist keine
Näherung, sondern dieselbe Bewegung aus der anderen Richtung betrachtet.

Der Schreiber (`export_more.write_bvh`) ist bewusst **allgemein** gehalten: er
bekommt eine Hierarchie und eine Wertegruppe, nicht „ein Skelett". M3 kann den
fertigen Rig hindurchschieben, ohne ihn anzufassen.

| Datei | Größe | Rücklese | fremder Leser |
|---|---|---|---|
| `facescan_m1_capture.bvh` | 1,1 kB | 16 Frames, 6 Kanäle, identisch bis 5e-7 | assimp: 1 Animation, Gelenk `Head` im Knotenbaum |
| `facescan_m1_capture.csv` | 1,2 kB | 16 Frames × 6 Kanäle, identisch bis 5e-7 | stdlib `csv` |
| `facescan_m1_capture.json` | 1,6 kB | dto., Einheiten im Dokument | stdlib `json` |

Zwei Fehler, die erst unterwegs auffielen:

1. **BVH kennt keine Kommentare.** Die erste Fassung schrieb eine Kopfzeile mit
   der Einheit hinein – assimp lehnte die Datei ab: *„Expected root node
   ROOT“*. Die Zeile steht direkt nach `HIERARCHY`, wo das Wurzelgelenk erwartet
   wird. Die Einheit steht jetzt in `docs/05` und im begleitenden JSON, das sehr
   wohl ein Feld dafür hat. (BVH selbst trägt keine: der Importierende
   entscheidet, ob eine Zahl Meter oder Zentimeter ist. Wir schreiben Meter und
   Grad.)
2. **Euler-Winkel springen.** Die Zerlegung liefert ±180°, und zwischen Frame 8
   und 9 stand −175° neben +175°: 10° Unterschied, abgespielt aber als 350°
   Rückwärtsdrall, weil BVH zwischen zwei Frames linear interpoliert und nichts
   von Winkeln weiß. Entwrappt (größter Schritt 10,0° statt 350,0°) steht die
   Bewegung richtig herum da.

## 8. Was M0, M1 und M2 bewusst NICHT enthalten

Keine echte Gesichtserkennung (Landmarks und Tiefen kommen aus der synthetischen
Ground Truth), keine Animation, kein Mocap, keine Freemium-/Krypto-Kasse, kein
Gerätetest. M0 + M1 beweisen, dass die **Geometrie-Basis** trägt: Pose, Modell-Fit,
Tiefenfusion, Haar-Volumen und die ersten drei Exportformate. Alles andere baut darauf
auf (siehe `docs/11-roadmap.md`, `docs/03-scan-pipeline.md`).

Export-Formate: **fertig** = OBJ, PLY (binär), GLB (binäres glTF), STL,
USDA, USDZ, Alembic (ABC), binäres FBX 7.5. **Offen** = USDZ mit `.usdc`
für AR Quick Look, Quadric Decimation, UV-Atlas.

## 9. Rechtliches

Der Prototyp nutzt ausschließlich selbst erzeugte, synthetische Daten. Für das Produkt
gilt: die 3DMM-Basis wird aus eigenen, schriftlich lizenzierten Aufnahmen gebaut.
FLAME, Basel Face Model, ICT-FaceKit (voll) und SMPL sind forschungs- oder
einzelfalllizenziert und deshalb tabu (siehe `docs/09-recht-compliance.md`).

---

## English summary

This directory is the **M0 feasibility prototype**: it proves with numbers, against
synthetic ground truth, that a metric 3D face reconstruction is possible from 2D
landmarks alone – no ARCore, no SLAM, no depth sensor.

* `reference/python/run_m0.py` runs the pose/fit experiment (M0) and writes fixtures + report.
* `reference/python/run_m1.py` runs the full geometry chain (M1): render → TSDF fusion →
  mesh → hair volume → metrics → OBJ/PLY/GLB export with read-back verification.
* `reference/python/kotlin_mirror.py` re-implements the Kotlin core in pure Python and
  checks it against the NumPy reference (agreement to five decimals on all metrics).
* `android/` holds the Kotlin production core, camera controller, Compose UI (Jamaica
  palette, night + day mode, German + English strings) and JVM unit tests.

**M1 results:** Chamfer distance 0.745 mm (target ≤ 0.8), hair IoU 0.871 (target ≥ 0.85),
texture completeness 99.9 %, and exports that read back identical to 4e-6 mm. All five
acceptance gates pass.

**M2 results (export formats):** added writers *and readers* for STL (binary/ASCII),
USDA, USDZ, binary FBX 7.5 and Alembic/Ogawa. All 8 formats (OBJ, PLY, GLB, STL, USDA,
USDZ, FBX, ABC) round-trip identical. `validate_exports.py` re-opens every file with a
reader we did not write: trimesh, Pixar's `pxr`, real Alembic 1.8.12 and assimp — 7 of 7
confirmed. That external check found seven real bugs our own reader had passed, most
importantly the FBX case-sensitivity of property type codes (`D` = one double, `d` = an
array) and the Alembic "frozen" byte.

**Known limitation:** there is no JDK/Gradle in this environment, so the Kotlin sources
have never been compiled. The algorithms and index arithmetic are verified by the mirror;
the syntax is not. Three real bugs were found and fixed by that mirror – most importantly
a wrong rotation lever arm in the pose Jacobian, which converges but is systematically
skewed.
