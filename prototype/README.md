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
/tmp/qrenv/bin/pip install trimesh usd-core
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
| Export-Rücklese (8 Formate, s. §7) | identisch bis 4e-6 mm | – | bestanden |
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
USDZ, **binäres FBX 7.5** und **Alembic (Ogawa)**. Kein assimp, keine
Bibliothek – nur stdlib und NumPy, damit die Schreiber später 1:1 nach Kotlin
und C++ portiert werden können.

Zu jedem Schreiber gehört ein Leser. Ein Test, der nur „Datei existiert“
prüft, beweist nichts.

| Format | Zweck | Größe | Rücklese |
|---|---|---|---|
| OBJ | Universaltausch | 12,8 MB | identisch bis 5e-7 mm |
| PLY (binär) | Punktwolken/Mesh | 5,2 MB | identisch bis 4e-6 mm |
| GLB (glTF) | Android-AR, Web | 4,9 MB | identisch bis 4e-6 mm |
| STL (binär) | 3D-Druck | 12,6 MB | 257.044 Facetten, 4e-6 mm |
| USDA | USD-Text, Pipeline | 14,3 MB | Indizes identisch, `metersPerUnit=0.001` |
| USDZ | Apple AR Quick Look | 14,3 MB | ZIP, ein Eintrag, unkomprimiert |
| FBX 7.5 (binär) | Blender/Maya/Unity | 9,1 MB | 130.829 Punkte, Polygon-Konvention ok |
| Alembic (ABC) | Houdini/Nuke/Katana | 5,6 MB | `AbcGeom_PolyMesh_v1`, float32, 4e-6 mm |

**Die Gegenprobe mit fremden Lesern** ist der eigentliche Ertrag von M2.
`validate_exports.py` öffnet jede Datei mit einem Programm, das wir nicht
geschrieben haben:

| Format | fremder Leser | Ergebnis |
|---|---|---|
| OBJ, PLY, GLB, STL | trimesh | bestanden |
| USDA, USDZ | `pxr` (Pixars USD-Referenz) | bestanden |
| Alembic (ABC) | echte Alembic 1.8.12 (`tools/abc_check.cpp`) | bestanden |
| FBX 7.5 | assimp | bestanden |

**Sieben echte Fehler, die erst die fremden Leser gefunden haben** – unser
eigener Rücklese-Test hatte alle sieben durchgewinkt:

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

**Bekannte Grenzen von M2:**

* **Alembic-Digests sind Nullen.** Die 16 Byte SpookyHash vor jedem Sample
  dienen nur `abcinfo` und dem Wiederverwenden identischer Samples; beim
  Öffnen prüft sie niemand. Wer sie braucht, muss SpookyHash V2 nachrüsten.
* **USDZ mit `.usda`-Nutzlast ist nicht AR-Quick-Look-fähig.** Apple
  verlangt ein binäres `.usdc`-Krate als primäres Asset. Wir schreiben absichtlich
  Text, weil ein eigener Krate-Schreiber ein Projekt für sich ist (M2b). Für
  Android-AR ist das unerheblich: dort ist **GLB** das Format.
* FBX hat keine Materialien und keine Texturen – nur Vertexfarben.

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

`validate_exports.py` öffnet **19 Dateien** mit trimesh, `pxr`, echter
Alembic-Bibliothek und assimp: **19 von 19 bestanden**.

* **Normalen** in OBJ, PLY, USDA, USDZ, ABC – gelesen von trimesh, pxr und
  Alembic (`N=130829 scope='3'` = `vtx`, längste Normale 1.0000). STL trägt
  bewusst keine (nur die Flächennormale im 50-Byte-Satz).
* **UV + Textur** in allen 12 LOD-Dateien: trimesh dekodiert das eingebettete
  PNG (2048×2048 px), pxr findet `primvars:st` und die vollständige
  Shader-Kette `UsdPrimvarReader_float2 → UsdUVTexture → UsdPreviewSurface`.
* **FBX-Normalen sind die einzige Lücke**: `assimp info` meldet nur Zählwerte,
  und der Test-Build hat den Export abgeschaltet – ein Urteil „fehlt“ wäre
  hier gelogen. Geprüft werden sie von unserem eigenen Leser.

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
