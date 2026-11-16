# 03 – Scan-Pipeline (Kern-IP)

Stand: 2026-11-15 · Liest sich am besten nach `02-architektur.md`.

> **Leitidee:** Wir scannen nicht "blind" wie klassische Photogrammetrie. Wir wissen durch das Gesichts-Tracking
> zu jedem Zeitpunkt, wo die Kamera ist, wie das Gesicht geformt ist und welchen Gesichtsausdruck die Person hat.
> Damit wird aus einem schweren Rekonstruktionsproblem eine **stückweise, gut gestellte** Optimierung.

---

## 0. Warum dieser Ansatz (Abgrenzung zu Alternativen)

| Ansatz | Bewertung für unser Ziel |
|---|---|
| Klassische Photogrammetrie (SfM + MVS, z. B. COLMAP) | Braucht Textur im Gesicht (haut = fast texturfrei), liefert kaputte Geometrie bei Glatze/Haar, langsam, Ceres+SIFT auf Android schwer. **Nicht als Basis geeignet**, nur als Referenz im Test. |
| Reiner Tiefensensor (ToF/LiDAR) | Nicht auf allen Geräten, zu grob (mm-Rauschen), keine Poren/Haare. Nur als Extra-Hypothese. |
| Reines 3DMM-Fitting | Schnell & robust, aber "gummiartig", keine individuellen Details (Narben, Poren, Haar). **Unser Gerüst**, nicht das Endergebnis. |
| Neurale Single-View-Rekonstruktion | Braucht große Modelle, Halluzinationen, Lizenzfragen bei Gewichten. **Nicht für v1** (nur als optionaler Detail-Prior später). |
| **Unser Hybrid** (3DMM-Gerüst + geführtes MVS + TSDF-Fusion + getrennte Haar-Pipeline + NRICP-Registrierung) | Robust bei texturarmer Haut, detailreich wo Details sind, animierbar, on-device machbar. |

---

## 1. Stufe CAPTURE – geführte Aufnahme

### 1.1 Kamera-Setup (CameraX + Camera2-Interop)

| Parameter | Wert | Grund |
|---|---|---|
| Auflösung | Quick 1080p · Standard 1080p–4K · Pro 4K (Rückkamera) | Detail vs. Zeit |
| Fokus | **Manuell, fixiert** (scharf auf Nase beim Start, dann `LENS_FOCUS_DISTANCE` einfrieren) | Vermeidet Fokus-Pumpen ⇒ konstante Intrinsics, bessere MVS-Konsistenz |
| Belichtung | Manuell: ISO minimal mit noch akzeptablem Rauschen (ISO ≤ 400), Verschlusszeit so kurz wie möglich (≥ 1/125 s) | Bewegungsunschärfe ist der größte Feind |
| Weißabgleich | Fix (Tageslicht 5500 K oder gemessener Wert) | Konstante Albedo über alle Frames |
| Zoom | Fest (Primär- oder Tele-Kamera, kein Wechsel) | Konstante Brennweite |
| Stabilisierung (OIS/EIS) | **Aus** | EIS verändert die Projektion pro Frame (Crop) ⇒ Intrinsics-Verlust |
| Format | JPEG q95 (schnell) · Pro: RAW/DNG wenn `RAW_SENSOR` verfügbar | RAW erlaubt bessere Albedo-Schätzung und HDR-Fusion |
| Belichtungsreihe | 3 Bilder (−1/0/+1 EV) je akzeptierter Pose | Albedo ohne Schatten/Highlights (→ Textur-Baking) |
| Framerate | 30 fps Burst, Akzeptanz-Gate pro Frame | Kurze Aufnahmezeit |

**Intrinsics:** `CameraCharacteristics.LENS_INTRINSIC_CALIBRATION` (Brennweite, Hauptpunkt, Skew) +
`LENS_DISTORTION` (Android 11+) bzw. eigenes OpenCV-Kalibrierprofil pro Modell als Fallback. Wir
**entzerren vor jeder Verarbeitung** und rekalibrieren `f` in Stufe 3 nach.

### 1.2 Führung (Guidance)

Overlay-Elemente (Compose + Canvas, 60 fps, unabhängig von der Rekonstruktion):

1. **Ziel-Silhouette** (weicher Kopf-Umriss) mit Live-Kopfpose – der Nutzer "legt" sein Gesicht in die Schablone.
2. **Fortschrittsbogen** mit abgedeckten Winkeln (Yaw −75°…+75°, Pitch −25°…+30°).
3. **Qualitätsampel** (grün/gelb/rot) mit je einem konkreten Satz:
   - "Perfekt – bleib so." · "Etwas langsamer." · "Zu dunkel – geh ans Fenster." · "Kopf etwas höher."
4. **Auto-Start/Auto-Pause**: Aufnahme läuft automatisch, wenn Pose ruhig (Landmark-Varianz < Schwelle über 5 Frames)
   und Ausleuchtung ( Histogramm-Mittelwert im Fenster) stimmt.
5. **Sprachführung** (on-device TTS, DE/EN) + haptisches Tick bei jedem akzeptierten Frame.
6. **Not-Aus** ("Abbrechen") immer sichtbar; Fortschritt bleibt erhalten.

### 1.3 Akzeptanz-Gate pro Frame (on-device, < 5 ms)

| Prüfung | Metrik | Schwelle |
|---|---|---|
| Schärfe | Varianz des Laplacians im Gesichtsfenster | ≥ 120 (norm.) |
| Bewegungsunschärfe | Landmark-Verschiebung zwischen 2 aufeinanderfolgenden Kamerabildern | ≤ 1,5 px |
| Ausleuchtung | Mittlere Helligkeit + Clipping-Anteil (Hautregion) | 90–190 (0–255), Clipping < 2 % |
| Pose-Neuheit | Winkelabstand zu bereits akzeptierten Frames | ≥ 4° (Quick) / 3° (Standard) / 2° (Pro) |
| Mimik | `jawOpen`, `eyeBlink` | neutral (außer im Guided-Expression-Teil) |
| Sichtbarkeit | Anteil sichtbarer Landmarks (`visibility`) | ≥ 0,95 |
| Haar-Sichtbarkeit | Anteil Haar-Maske im Bild | ≥ 3 % (sonst Hinweis "Haare mit ins Bild") |

### 1.4 Aufnahme-Skripte

| Modus | Ablauf (Sekunden) | Frames |
|---|---|---|
| **Quick** | 0–3 Neutral · 3–13 Bogen links→rechts (−60°…+60°) · 13–18 leicht hoch/runter | ≈ 16 |
| **Standard** | 0–3 Neutral · 3–25 Bogen (−75°…+75°) · 25–35 Hinterkopf-Hilfe (Spiegel/2. Person) · 35–45 Guided Expressions (10) · 45–55 Haar-Spezial (Scheitel, Nacken, Spitzen) · 55–60 Nachlauf | ≈ 48 |
| **Pro** | Wie Standard + 3 Distanzen (50/35/70 cm) + RAW + 4K + Tele-Pass für Poren + Augen-/Mund-Innen-Pass | ≈ 120 |

**Hinterkopf:** Ohne Zweitperson ist der Hinterkopf nicht sichtbar. Lösung (alle drei werden angeboten):
(a) Spiegel-Assistent (Handy vor Spiegel, App spiegelt die Führung), (b) "Helfer-Modus" (zweite Person führt
das Handy, Audio-Ansagen), (c) **Statistischer Abschluss**: der 3DMM + die Haar-Modell-Verteilung schließen
die Rückseite plausibel (im Qualitätsbericht als "geschätzt" markiert).

---

## 2. Stufe PERCEPTION – was pro Frame gerechnet wird

| Aufgabe | Modell | Output | Quelle |
|---|---|---|---|
| Gesichts-Landmarks | Face Landmarker (`face_landmarker.task`) | **478** Punkte, normalisiert (x,y ∈ [0,1], z relativ zur Kopfmitte) | [1](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker) |
| Mimik | Blendshape-Modell (im Task enthalten, `outputFaceBlendshapes=true`) | **52** Scores ∈ [0,1], ARKit-Namen (browDownLeft, jawOpen, eyeBlinkRight …) | [1](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker) |
| Kopfpose | `outputFacialTransformationMatrixes=true` | 4×4-Matrix canonical→Kamera (metrisch) | [1](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker) |
| Haar-Maske | Image Segmenter (`hair_segmenter.tflite`, 2 Klassen, ~780 KB), Confidence-Mask (float) | Wahrscheinlichkeit pro Pixel | [4](https://gitlab.nrp-nautilus.io/ar-noc/mediapipe/-/tree/master/mediapipe/models) [5](https://theneuralbase.com/mediapipe/learn/intermediate/hair-segmentation/) |
| Haut-/Gesichts-Maske | Konvexe Hülle der Landmarks + Haar-Maske-Komplement + Farbmodell (YCbCr-Haut-Cluster, pro Person kalibriert) | Binär + Gewicht | eigenes Verfahren |
| Körperpose (später) | Pose Landmarker (33 Punkte, Weltkoordinaten in Metern) + Hand Landmarker (2 × 21) | Siehe `04` | [6](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker) |

Wichtig: **"`*Left`/`*Right` beziehen sich auf die Person, nicht den Betrachter"** – bei gespiegelten
Frontkamera-Bildern vertauschen sie sich. Wir verarbeiten **immer ungespiegelt** und spiegeln nur die Anzeige.
Das ist eine der häufigsten Fehlerquellen bei Blendshape-Pipelines und wird durch einen Unit-Test abgesichert.

Temporale Glättung der Landmarks: **One-Euro-Filter** (pro Koordinate, `minCutoff=1.0`, `beta=0.1`,
`dCutoff=1.0`) – bei der *Aufnahme* nur zur Stabilitätsbewertung, nicht für die Geometrie (die nutzt Rohdaten).

---

## 3. Stufe CALIBRATION – Posen sauber machen

**Ziel:** Robuste, metrische Kamerapose je Frame.

1. **Initialisierung** aus der MediaPipe-Transformationsmatrix (Rotation R₀, Translation t₀).
2. **EPnP + RANSAC** über die 478 3D-Landmarks des kanonischen Modells ↔ 2D-Landmarks im Bild.
   - Robustheit: RANSAC mit 200 Iterationen, Reprojektionsschwelle 3 px.
   - Outlier: Augenlider, Lippenränder und Haar-übergreifende Punkte werden niedriger gewichtet.
3. **Intrinsics-Verfeinerung (leichtes Bundle-Adjustment)**: über alle Frames gemeinsam werden
   `f_x, f_y` (als ein gemeinsamer Wert `f` bei quadratischen Pixeln), `c_x, c_y` und `k1, k2`
   nachoptimiert; Posen bleiben dabei zunächst fix. 50 Gauss-Newton-Schritte auf ~1 500 Residuen – < 1 s.
4. **Plausibilitätstest**: Die geschätzte Gesichtsbreite (aus Landmark-Abstand × Skalierung) muss beim
   Erwachsenen 12–16 cm ergeben. Abweichung > 15 % ⇒ Skalierungs-Korrektur und Warnung im Bericht
   (schützt vor falschen Intrinsics auf Exoten-Geräten).
5. **Rolling-Shutter-Korrektur**: Bei verworfenen, aber schnellen Bewegungen wird die Pose pro Bildzeile
   linear interpoliert (nur im Pro-Modus relevant).

**Ergebnis:** `{R_t, t_t}` metrisch in Millimetern, Intrinsics `K`, Verzeichnungskoeffizienten.
**Up-Vektor** aus dem Beschleunigungssensor (Median über die Aufnahme) ⇒ Achsenausrichtung für den Export.

---

## 4. Stufe COARSE – Multi-Frame-3DMM-Fit

### 4.1 Modell

Wir benutzen **unser eigenes 3DMM** (`FaceScanMM`), aufgebaut aus eigenen, lizenzierten Aufnahmen (siehe `09`
– FLAME und Basel sind forschungs-lizenziert, daher tabu für ein kommerzielles Produkt). Aufbau:

```
S(α, β, δ) = S̄ + A_id · α + A_exp · β + N(δ)        # Geometrie
A(γ)       = Ā + A_tex · γ                           # Albedo (per Vertex)
```
- `S̄`: mittleres Gesicht, **in der Topologie unseres Basiskopfs** (≈ 12 k Vertices, registriert).
- `A_id`: 128 Identitäts-Basen, `A_exp`: 76 Ausdrucks-Basen (PCA auf registrierten Scans).
- `N(δ)`: optionale Verfeinerung (siehe Stufe 5/9).
- Beleuchtung: **sphärische Harmonische 3. Ordnung** (9 Koeffizienten, RGB) + ein konstanter Term.
- Kamera: aus Stufe 3 (fix während des 3DMM-Fits; wird in der Endrunde mitverfeinert).

### 4.2 Zielfunktion (pro Durchlauf)

```
E = Σ_t Σ_p∈M_t  w_p · ρ(  I_t(π(K, R_t, t_t, S_t)_p) − B(SH(L_t, n_p) · A_p)  )
  + λ_id ‖α‖²  + λ_exp Σ_t ‖β_t‖²  + λ_smooth Σ_t ‖β_t − β_{t−1}‖²  + λ_lm Σ_t Σ_i ‖π(v_i) − l_{t,i}‖²
```
- `ρ`: Huber-Loss (robust gegen Haare/Schatten/Brillenränder) – **entscheidend** für Haar-Ränder.
- `M_t`: **Haut-Maske** – Haar-Pixel werden aus dem photometrischen Term ausgeschlossen (sie befolgen kein
  Lambert-Modell), fließen aber in den Silhouetten-Term ein.
- Landmark-Term `λ_lm`: hält die Lösung am Tracking (verhindert Drift bei texturarmer Haut).
- Optimierung: Gauss-Newton mit **reduzierten Parametern** (Identität einmal, Pose/Expr/Licht pro Frame),
  gelöst mit Schur-Complement; C++ mit Eigen (nur Kopf, dynamisch gelinkt – MPL-2, dateibezogen, ok).

### 4.3 Ablauf (Coarse-to-Fine)

| Schritt | Inhalt | Dauer (Ziel) |
|---|---|---|
| C1 | Neutral-Frames: Identität + Pose fitten | 3 s |
| C2 | Alle Frames: Pose/Expression/Licht, Identität fix | 5 s |
| C3 | Gemeinsam: Identität + alles, 2 Gauss-Newton-Runden | 5 s |
| C4 | Haar-Silhouetten-Term (schwach gewichtet) | 2 s |

**Ergebnis:** metrisch korrektes, ausdrucksbereinigtes **neutrales Gesicht**, pro Frame die Expression,
plus eine Albedo-Schätzung als Startpunkt fürs Textur-Baking.

---

## 5. Stufe DENSE – Multi-View-Stereo mit bekannten Posen

Weil die Posen bekannt sind, entfällt das teure Features-Matching. Wir fahren **Plane-Sweep + PatchMatch**
auf der GPU.

### 5.1 Referenz-View-Auswahl
Für jede der N≈40 Referenz-Frames wählen wir die **8 besten Nachbar-Views**: Basislinie 8–20 cm,
Winkel 10–35°, minimale Mimik-Änderung (Blendshape-Distanz), maximale Schärfe.

### 5.2 Kostenfunktion (PatchMatch-Stereo, 4 Iterationen)
- Patch 5×5, **Weighted Census + ZNCC** (robust bei Wiederholungen/Haut ohne Textur).
- Tiefenhypothesen: 96–160 Ebenen in **inverser Tiefe** (gleichmäßige Verteilung im Disparitätsraum),
  Bereich aus dem 3DMM-Mesh ± 45 mm (Gesicht) bzw. ± 120 mm (Haar-Volumen, eigener Sweep).
- **Geometrischer Prior:** Der 3DMM-Tiefenwert wirkt als weicher Prior `λ_prior·(d − d_3DMM)²` mit
  `λ_prior` klein – das stabilisiert texturarme Stellen (Wangen, Stirn), ohne Details zu glätten.
- **Mehrskalig:** ¼ → ½ → ¾ Auflösung, je 3 Iterationen; Upsampling der Tiefe mit Median-Filter.
- Ausführung: Vulkan-Compute-Shader (`r16f`-Texturen für Tiefen/Normalen, `rgba8` für Bilder),
  Fallback GLES 3.1-Compute; Workgroup 8×8, geteilte Bildkacheln im Shared Memory
  (Speicherbandbreite ist der Flaschenhals – siehe MobiDepth-Erkenntnisse zu mobilem Stereo-Matching [7](https://www.microsoft.com/en-us/research/wp-content/uploads/2022/09/mobicom22-final138.pdf)).

### 5.3 Tiefenkarten-Verfeinerung
1. **Left-Right-Check** (|d_L − d_R| ≤ 1 Ebene).
2. **Konsistenz über ≥ 3 Views**.
3. **Konfidenz**: ZNCC-Peak-Verhältnis + Nachbar-Varianz.
4. **Kantenerhaltende Filterung** (bilaterales / "Weighted-Median"-Filter) – **nur für Haut**; Haare bekommen
   einen separaten, deutlich schwächeren Durchlauf, weil sonst Strähnen verschwinden.
5. Optional: **Shape-from-Shading-Verfeinerung**: Die Differenz zwischen gerendertem 3DMM-Shading und echtem
   Bild liefert ein Residuum, aus dem feine Poren/Normalen-Details (0,1–0,3 mm) gewonnen werden
   (photometrische Stereo-Näherung über die Belichtungsreihe). Ergebnis → **Detail-Normal-Map** (Stufe 9).

---

## 6. Stufe FUSION – Volumen und Mesh

### 6.1 Zwei getrennte Volumina
| Volumen | Quelle | Voxel | Glättung | Zweck |
|---|---|---|---|---|
| `TSDF_skin` | Haut-Maske gewichtete Tiefenkarten | 0,5 mm | mittel (truncation 3 mm, Gewichtskurve nach Konfidenz) | Hautgeometrie |
| `TSDF_hair` | Haar-Maske gewichtete Tiefenkarten | 0,8 mm | **minimal** (nur Ausreißer-Entfernung; Volumen darf "flauschig" bleiben) | Haar-Volumen |

- Datenstruktur: **Hashed Voxel Grid** (`std::unordered_map<Vec3i, Voxel>` auf 8³-Blöcken), damit wir nicht
  512³ allozieren müssen. Arbeitsbereich: Bounding-Box um Kopf + 150 mm Rand.
- Integration: Standard-TSDF mit Gewicht `w = conf / (σ_z²)`, `σ` aus Tiefenunsicherheit (wächst quadratisch
  mit Entfernung und Basislinien-Verhältnis).
- **Haar-spezifisch:** Haar-Tiefenkarten sind systematisch zu nah (die Kamera sieht die Vorderseite der
  Strähnen). Wir integrieren sie deshalb mit einem **einseitigen** Truncation-Band (nur in Blickrichtung
  negativ) und einer Breite von 25 mm – das erzeugt ein plausibles Volumen statt einer Schale.
- Optional: `DEPTH16`-Frames (falls vorhanden) als dritte Hypothese mit kleinem Gewicht.

### 6.2 Meshing
- **Marching Cubes** (Standard-Tabellen, GPU-fähig) → Roh-Mesh (Ziel: 1,5–3 Mio. Dreiecke für Pro).
- **Nachbearbeitung:** Entfernung kleiner Komponenten (< 500 Dreiecke), Loch-Füllung
  (< 3 mm Rand → "Advancing Front"; größer → Poisson-Variante), leichte Taubin-Glättung (Haut, 3 Iterationen).
- **Watertight-Variante** (für 3D-Druck/Boolean): **Poisson Surface Reconstruction** (MIT-lizenziert [8](https://github.com/mkazhdan/PoissonRecon) [9](https://github.com/isl-org/Open3D-PoissonRecon)),
  Tiefe 10–12, mit Normalschätzung aus den Tiefenkarten.
- **LODs:** Quadric-Edge-Collapse (garland-heckbert) auf 300 k / 80 k / 20 k / 6 k Dreiecke.

**Gemessener Stand des Prototyps** (`prototype/tools/build_master.py`,
`build_lod.py`): Rohnetz 1.463.676 Dreiecke (Haut 0,75 mm, Haar 1,2 mm),
2771,7 cm². Die LOD-Kette wird aus dem Master gerechnet und trägt die UVs mit:

| Stufe | Dreiecke | Formfehler gegen Master | p95 | max |
|---|---|---|---|---|
| LOD0 | 299.998 | 0,035 mm | 0,165 mm | 1,29 mm |
| LOD1 | 80.000 | 0,152 mm | 0,536 mm | 1,59 mm |
| LOD2 | 20.000 | 0,285 mm | 0,784 mm | 4,19 mm |
| LOD3 | 5.999 | 0,396 mm | 1,071 mm | 6,64 mm |

Gemessen mit `metrics.surface_deviation` (**Punkt-zu-Dreieck**, nicht
Punkt-zu-Punkt). Punktwolken-Chamfer ist hier die falsche Zahl: er misst die
Punktdichte, nicht die Form, und meldet für LOD3 1,78 mm, wo die Oberfläche
tatsächlich 0,40 mm abweicht.

Zwei Details, die beim Vereinfachen entscheiden:
1. **Dreiecke zyklisch drehen, nicht sortieren.** Sortierte Index-Tripel
   verlieren die Umlaufrichtung; danach steht ein Teil der Dreiecke auf links,
   und davon merkt man nichts, bis ein UV-Werkzeug die Nachbarschaft nicht
   mehr erkennt (20.753 Charts aus 25.000 Dreiecken).
2. **UVs mitführen und Kanten über Chart-Grenzen bestrafen** (`uv_weight`).
   Sonst zieht sich die Textur über den Abstand zwischen zwei Charts.

**Wasserdichte Variante** (`prototype/reference/tools/build_watertight.py`,
`facescan_ref/repair.py`) — gemessen, nicht geschätzt:

| Schritt | Ergebnis |
|---|---|
| Hautnetz | 40.409 Punkte / 76.208 Dreiecke, 132 Komponenten, 4.712 Randkanten |
| Loch-Füllung ≤ 3 mm | 45 von 345 Schleifen geschlossen (59 Dreiecke); 300 zu groß, größte 2.402 mm Umfang |
| Taubin, 3 Iterationen | Fläche −18,3 %, Abstand zum Original 0,109 mm im Mittel |
| Poisson | 227.867 Punkte / 455.730 Dreiecke, geschlossen, Euler 2, Volumen 735,9 cm³ |
| Gegenprobe trimesh | `is_watertight = True`, `euler_number = 2` |
| Abstand Hautnetz → Ergebnis | 0,201 mm im Mittel |

Zwei Abweichungen von der Vorgabe oben, bewusst und dokumentiert: wir rechnen
Poisson auf einem **regelmäßigen 192³-Gitter** statt auf einem Octree der Tiefe
10–12 (Tiefe 10 wären 1024³ Voxel = 4,3 GByte; auf einem Telefon undenkbar).
Und die Loch-Füllung schließt nur 45 von 345 Schleifen — der Rest ist mit
5.135 mm offenem Rand viel zu groß, um ihn zu *erfinden*; genau diese Fälle
gehen in die Poisson-Variante, wie oben vorgesehen. Die Taubin-Glättung nimmt
der Fläche 18,3 %, schrumpft die Form aber nicht: der Abstand zum Original
bleibt bei 0,109 mm, verloren geht das Treppenmuster des Voxelgitters.

Für den Druck kommt ein **Sockel** dazu, und zwar als Änderung am
Indikatorfeld, nicht als Schnitt am Netz: unterhalb der Schnitthöhe gilt
nur noch ein Kegelstumpf als innen, danach läuft derselbe Marcher noch
einmal. Die Schnitthöhe folgt einer Regel (tiefste Stelle mit ≥ 25 % des
größten Querschnitts: z = 0,8 mm), nicht einem geratenen Wert. Ergebnis:
774.858 Dreiecke, 1171,2 cm³, Standfläche 152,1 cm², kleinste lokale Dicke
1,82 mm. Der Kopf allein hat **0,00 cm²** Standfläche — das ist der ganze
Unterschied zwischen „geschlossen" und „druckbar".

---

## 7. Stufe HAIR – Haar-Rekonstruktion (eigenes Kapitel, weil es der schwierigste Teil ist)

### 7.1 Was realistisch erreichbar ist (ehrliche Einordnung)

| Stufe | Ergebnis | Tauglich für | Rechenzeit |
|---|---|---|---|
| **L1 Haar-Cap** | Geschlossenes Haar-Volumen als Mesh (wie eine gut gemachte "Haarkappe" mit Volumen) | Spiele-Avatare, VR, 3D-Druck, Silhouette | 15 s |
| **L2 Cards** | L1 + 60–250 transparente Haar-Karten mit Strömungsrichtung + Alpha-Textur | Echtzeit-Engines, Blender-Eevee, Unreal, Unity | +10 s |
| **L3 Strands** | L2 + echte Kurven (2 k–50 k Strähnen) inkl. Root-/Tip-Attribute | Blender (Partikel/Curves), Houdini, Unreal Groom, Offline-Renderer | +30 s (High-End) |

Echte, einzelne Haare aus Handy-Fotos zu rekonstruieren, ist weltweit ungelöst (selbst Light-Stage-Systeme
liefern Strähnenbündel). Wir liefern deshalb **gestufte, ehrliche Qualität** und kommunizieren das in der App
genau so ("Haar-Stufe 2 von 3 – für Film-Details nimm Stufe 3").

### 7.2 Haar-Volumen → Scalp (Kopfhaut)
1. Aus `TSDF_hair` Marching Cubes → Haar-Mesh.
2. **Scalp-Schätzung:** Wir wissen aus dem 3DMM, wo der Schädel ist. Die Kopfhaut = Schädeloberfläche
   (aus dem basismodell) nach außen versetzt um 3–5 mm, begrenzt durch die Haar-Maske in allen Views
   (Sichtbarkeits-Voting: ein Scalp-Punkt gehört zur Kopfhaut, wenn er in keiner View *hinter* Haar-Maske
   liegt, aber von Haar umgeben ist). Der **Haaransatz (Hairline)** wird als Schnittkurve zwischen
   Scalp-Oberfläche und dem Rand der Haar-Maske (über alle Views rückprojiziert) bestimmt – mit
   Median-Glättung.
3. Das Ergebnis ist eine geschlossene **Scalp-Region** (Fläche + UVs) als Wurzelbasis für L2/L3.

### 7.3 Orientierungsfeld (Strömungsrichtung der Haare)
- **Gabor-Filterbank** (12 Orientierungen × 3 Skalen) auf den aufnahmeeitigen Bildern, ausgewertet
  **nur innerhalb der Haar-Maske**, gewichtet mit Schärfe und Blickwinkel ("wie tangential schauen wir drauf").
- Rückprojektion auf die Haar-Oberfläche: jede Oberflächenposition sammelt die Orientierungen aller Views,
  in denen sie sichtbar war; die 2D-Orientierung wird in die Tangentialebene projiziert.
- **Glättung als Richtungsfeld** (Vektorfeld auf der Oberfläche, iterative Laplacian-Glättung mit
  Renormierung) → glattes, plausibles Strömungsfeld, auch an Stellen, die nie sichtbar waren (Hinterkopf:
  Fortsetzung durch Symmetrie-Prior + Längenprior, markiert als "geschätzt").
- Aus dem Feld entstehen: **Haarlängen-Parameter** (aus der Ausdehnung des Haar-TSDF entlang der Strömung),
  **Volumen-/Dicke-Parameter** (aus der TSDF-Dichte), **Wirbel (Cowlicks)** werden automatisch erkannt
  (Feld-Singularitäten) und als Seed-Punkte gesetzt.

### 7.4 L2 – Haar-Karten (Cards)
1. **Strähnen-Bündelung:** 60–250 Guidesträhnen wachsen vom Scalp entlang des Orientierungsfelds mit
   Schrittweite 2 mm, leichtem Rauschen (± 4°) und Kollisionsvermeidung (Abstoßung vom Kopf-Mesh,
   minimale Kopf-Distanz 4 mm, Selbstkollision über ein grobes 3D-Dichtefeld).
2. **Karten-Generierung:** Jede Strähnen-Gruppe (3–12 Guides) wird zu einer Karte: dünnes
   Flächenstück (2–6 Kanten entlang der Strähne, Breite 6–25 mm), ausgerichtet nach **View-abhängigem
   Billboard** oder **geometrisch fixiert** (Export-Option; fixiert ist für Nachbearbeitung besser).
3. **Textur:** Alle Karten liegen in **einem gemeinsamen Atlas**. Für jede Karte wird aus allen Views der
   beste Ausschnitt projiziert (max. Schärfe, minimale Verdeckung, Blickwinkel ≈ 90° zur Karte), die Alpha
   kommt aus der Haar-Maske (mit weichem Rand 2 px und "Strähnigkeit" aus der Gabor-Antwort).
   Randbereiche: Dithering + Alpha-Deckkraft-Reduktion für weiche Übergänge.
4. **Shader in der App:** Karten mit Alpha-Hashed-Transparenz + Anisotropie-Näherung (Kajiya-Kay) + AO.

### 7.5 L3 – Strähnen (Strands)
- Guide-Strähnen (300–1 500) + interpolierte Kinder (Faktor 10–40) ⇒ 2 k–50 k Kurven.
- Jede Kurve: 12–48 Kontrollpunkte, Attribute: `width` (Root→Tip: 0,09 → 0,03 mm), `clump`, `twist`,
  `roughness`, `color_variation` (aus den Bildern je Strähne gemittelt).
- Kollision: Guides werden gegen Kopf und Schultern geprüft (Signed-Distance-Feld aus dem Mesh,
  1-mm-Auflösung, nur für diesen Schritt).
- Export: **Alembic-Kurven** (`Ogawa`-Container, `ICurves`-Geometrie) + **USD BasisCurves** (USDA)
  + optional **Blender-`.abc`** (direkt als Hair-Curves importierbar).

### 7.6 Sonderfälle (müssen im Test-Set sein)
Glatze/kurz geschoren · Locken (3C–4C) · Dreadlocks · Zopf/Pferdeschwanz (hängende, schwingende Teile) ·
Glatze mit Bart (Bart = eigenes Haar-System, gleiche Pipeline) · Kopfbedeckung (Hinweis "abnehmen") ·
Haar-Glanz/Specular (durch Belichtungsreihe reduziert) · gefärbte Haare (Farbmaske statt Grauwert).

---

## 8. Stufe REGISTER – Retopologie, Rig, Blendshapes

**Ziel:** Aus dem "gescannten" Mesh ein **animierbares** Modell machen: feste Topologie, saubere Kanten und
52 Blendshapes. Das ist die Voraussetzung für alles, was danach kommt (Animation, Export, Nachbearbeitung).

### 8.1 Der FaceScan-Basiskopf
- Eigene, in Blender/per Skript erstellte **Topologie** (kein fremdes Modell, keine Fremdlizenz):
  - Kopf/Hals/Ansatz: ~9 k Vertices, **quad-dominant** (Subdivision-ready), Kantenflüsse nach
    Animations-Standard (Augen-, Mund-, Nasolabial-Ringe), UVs fix.
  - Dazu: Augäpfel (2 × 1,2 k), Hornhaut/Tränenfilm als separate Shell, Zähne oben/unten (2 × 2 k),
    Zunge (800), Mundinnenraum ("mouth socket", 1,5 k) – dieselbe Konstruktion wie bei professionellen
    Digital-Human-Setups.
- **Skelett:** `root → neck → head → (eye_L, eye_R, jaw)`; Gewichte anfangs prozedural (Rigid-Binding nach
  Regionen + 2 Glättungsdurchgänge), später nachkalibriert.
- **Warum eigene Topologie?** (a) keine Lizenzrisiken (FLAME/BFM/ICT-FaceKit sind forschungs- bzw.
  mehrdeutig lizenziert – siehe `09`), (b) Kontrolle über Kantenfluss und Namenskonvention
  (ARKit-Blendshape-Namen), (c) Asset-Wert des Unternehmens.

### 8.2 Non-Rigid ICP (NRICP)
```
1. Starre Ausrichtung: 7 Landmark-Paare (Nasenwurzel, Kinn, beide Traguspunkte, Augenwinkel) → Similarity-Transform
2. Grobe Deformation: Embedded-Deformation-Graph (Knoten = every ~40. Vertex des Basiskopfs, ≈ 1 500 Knoten),
   Optimierung von Rotation+Translation je Knoten mit ARAP-Regularisierung (weight 10 → 1 über 6 Level)
3. Feine Deformation: Vertex-weise Verschiebung mit Laplacian-Glättung + Landmark-Term (λ=0.5)
4. Korrespondenz-Erneuerung je Level: Next-Best-Point-Suche im KD-Baum, bidirektional,
   Ablehnung wenn: Normalenwinkel > 30°, Distanz > 3·Median, Haar-Punkt ↔ Haut-Punkt
5. Konvergenz: 6 Level × 12 Iterationen, < 20 s auf Mittelklasse
```
Aus der Registrierung entstehen:
- **Displacement-Map** (16- oder 32-bit, EXR/PNG): Abstand registrierte Basiskopf-Oberfläche → Scan,
  entlang der Basisnormale. Enthält Nase, Falten, Narben, Poren.
- **Detail-Normal-Map** (aus der hochfrequenten Restabweichung, die das Displacement-Raster nicht fassen kann).

### 8.3 Blendshapes (52 ARKit-Formen) personalisiert
Zwei Quellen, kombiniert:
1. **Gemessene Expressionen (primär):** In der Aufnahme hat die Person 10–12 definierte Ausdrücke gemacht
   (Guided Expressions). Für jeden Ausdruck registrieren wir den Basiskopf auf diesen Scan (NRICP mit fester
   Identität) ⇒ **echte, gemessene** Deltas für z. B. `mouthSmileLeft/Right`, `jawOpen`, `eyeBlink*`,
   `browInnerUp`, `browDown*`, `mouthFunnel`, `mouthPucker`, `cheekPuff`, `noseSneer`.
2. **Deformations-Transfer (Ergänzung):** Für die nicht gemessenen der 52 Formen übertragen wir Deltas von
   einem Template-Satz (nur mit rechtlich geklärter Quelle – entweder **selbst modelliert** oder aus einem
   eindeutig MIT-lizenzierten Satz nach anwaltlicher Prüfung; Standard-Ansatz: Sumner & Popović
   "Deformation Transfer", Algorithmus frei [10](https://github.com/fernandotonon/QtMeshEditor/issues/889)).
   Übertragung: Template ↔ Basiskopf-Korrespondenz (NRICP), dann Dreiecks-weise Übertragung der
   Deformationsgradienten und Rücklösung (Poisson) auf dem Basiskopf.
3. **Korrektur-Shapes** (eigene Extras, zusätzlich zu ARKit): `eyeLook*`-Korrekturen, `jawOpen`-Mundwinkel-
   Korrektur, "Lid-Follow" (Augenlider folgen dem Augapfel), Zunge-Kontrolle.
4. **Kalibrierung der Bereiche:** Der Nutzer macht bei der Einrichtung einmal " maximal lächeln / Augen zu /
   Brauen hoch" ⇒ die Blendshape-Gewichte werden auf 1,0 normalisiert (sonst wirkt alles zu schwach).

**Namenskonvention:** Exakt die 52 ARKit-Namen (`eyeBlinkLeft`, `jawOpen`, `mouthSmileRight`, …) ⇒
direkte Kompatibilität mit Unreal LiveLink, Unity ARKit-Face-Plugin, Ready-Player-Me-Workflows, VRM,
iClone, Blender-ARKit-Tools.

---

## 9. Stufe TEXTURE – UV und Baking

| Map | Inhalt | Format | Auflösung (Free/Creator/Studio) |
|---|---|---|---|
| Albedo (BaseColor) | shading-bereinigte Farbe (aus Belichtungsreihe + SH-Beleuchtungsschätzung) | PNG 8-bit (optional 16-bit) | 2K / 4K / 8K |
| Normal | aus Displacement + Detail (OpenGL-Konvention, umschaltbar) | PNG 16-bit | 2K / 4K / 8K |
| Roughness | aus Specular-Analyse der Belichtungsreihe (Stirn/Nase öliger als Wange) | PNG 8-bit | 2K / 4K / 4K |
| AO / Cavity | Ambient Occlusion + Cavity, ray-getraced auf der GPU (128 Rays/UV-Pixel) | PNG 8-bit | 2K / 4K / 4K |
| SSS-Maske | Regionen mit starker Streuung (Nase, Ohren, Lippen) | PNG 8-bit | 2K / 4K / 4K |
| Displacement | Registrierungs-Rest (mm), **EXR 32-bit float** oder PNG 16-bit | EXR/PNG | 2K / 4K / 8K |
| Specular/Sheen (Haar) | Glanz-Maske für Karten/Strähnen | PNG 8-bit | 1K / 2K / 4K |

**UV-Atlas:** Wir nutzen **feste UVs des Basiskopfs** (das ist der Sinn der Registrierung!) – keine
automatische, wechselnde UV-Erzeugung. Das garantiert: gleiche UVs über alle Avatare ⇒ Texturen
austauschbar, Morph-freundlich, keine Naht-Probleme beim Animieren. Für die **Haar-Karten** wird ein
separater, automatisch gepackter Atlas erzeugt.

**Baking-Verfahren:**
1. Für jeden UV-Pixel (Tile-basiert, 32×32 Tiles, 4 px Rand zur Naht-Vermeidung):
   - Position + Normale über die Basiskopf-Oberfläche, verschoben entlang der Displacement-Map.
   - Sichtbarkeitstest in jeder View (Backface, Verdeckung via Ray-Cast gegen das Scan-Mesh mit
     **Bias 1,5 mm**, Randabstand, Mimik-Kompatibilität).
   - Farbwert aus **allen** sichtbaren Views, gewichtet mit **cos²(Blickwinkel)**.
2. **Warum gewichten statt auswählen** (und das ist der Punkt, an dem der erste Prototyp
   gescheitert ist): Nimmt man pro Pixel oder pro Patch nur die *beste* View, entsteht eine harte
   Grenze zwischen den Zuständigkeitsbereichen der Kameras – die "Blocken", die man im Modell
   sieht. Nachträgliches Weichzeichnen (3×3-Blur, Mehrheitsentscheid) kann das nur verwischen,
   nicht beheben, weil die Information "wie sähe es aus Kamera 7 aus?" an dieser Stelle bereits
   weggeworfen wurde. Bei cos²-gewichteter Mischung geht die Zuständigkeit dagegen **stetig** von
   einer Kamera zur nächsten über – es gibt keine Kante, die man glätten müsste. Multi-Band-
   Blending (3 Bänder) bleibt als Option für den Fall, dass die Aufnahmen unterschiedlich
   belichtet sind; bei einheitlicher Belichtung ist die cos²-Mischung überlegen, weil sie keine
   Frequenzen verschiebt.
3. **Lückenfüllung:** Push-Pull-Pyramide (hartnäckig, schnell, GPU-freundlich) über höchstens 3 % Fläche.
   Bei mehr: Qualitätsbericht "Gelb" + Hinweis auf Nachaufnahme.
4. **Shading-Bereinigung:** `Albedo ≈ I / (SH·N)` mit der in Stufe 4 geschätzten Beleuchtung – entfernt den
   "eingebackenen" Schatten. Stärke als Regler ("Natürlich ↔ Neutral") in der UI.

---

## 10. Stufe QA – Qualitätsbericht

| Kennzahl | Berechnung | Grün | Gelb | Rot |
|---|---|---|---|---|
| Formtreue | Median der Landmark-Reprojektion nach Optimierung | < 1,5 px | < 3 px | ≥ 3 px |
| Detailgüte | Mittlere photometrische Konsistenz der Tiefenkarten | > 0,85 | > 0,70 | ≤ 0,70 |
| Haar-Passung | Silhouetten-IoU Haar-Maske vs. Haar-Render | > 0,85 | > 0,70 | ≤ 0,70 |
| Abdeckung | Anteil der Kopf-Oberfläche mit ≥ 3 gültigen Views | > 0,95 | > 0,80 | ≤ 0,80 |
| Texture-Holes | Anteil gefüllter UV-Fläche | < 1 % | < 3 % | ≥ 3 % |

Darstellung in der App: **fünf Ampeln** mit je einem Laien-Satz und (aufklappbar) dem Profi-Wert, z. B.
"Formtreue: sehr gut (1,2 px Abweichung)". Aus "Rot"-Zeilen entstehen automatisch konkrete Tipps
("Scanne noch einmal deine linke Seite – die war nur 2 Sekunden im Bild").

---

## 11. Parameter, die empirisch kalibriert werden müssen (M0/M1)

| Parameter | Startwert | Kalibriermethode |
|---|---|---|
| Voxelgröße Haut | 0,5 mm | Rastertest 0,3/0,5/0,8 mm auf 10 Personen |
| Truncation Haar | 25 mm einseitig | Visuelle Bewertung durch 3D-Artist |
| `λ_prior` MVS | 0,05 | Gitter-Suche auf Ground-Truth-Set |
| Tiefenebenen | 128 | Qualitäts-/Zeit-Kurve |
| NRICP-Level/Iterationen | 6 / 12 | Konvergenzplot |
| Landmark-Gewicht `λ_lm` | 0,5 | Vergleich gegen kalibrierte Scans (Referenz aus Studio-Scan) |
| Gabor-Skalen | 3 (σ = 1,2/2,4/4,8 px) | Bewertung an 6 Frisur-Typen |
| Haar-Karten-Anzahl | 120 | Sichtbarkeits-/Performance-Test |

**Ground Truth:** In M0 beschaffen wir (a) 20 eigene Studio-Scans (Referenz-Scanner oder bezahlter Dienst) und
(b) 20 Handy-Scans derselben Personen. Daraus: Fehlermaße (Chamfer-Distanz, Landmark-Abstand), mit denen alle
Parameter objektiv statt nach Gefühl eingestellt werden. Ohne dieses Set ist keine Qualitätssteuerung möglich.

---

## 12. Pseudocode: Orchestrierung (Kotlin-Seite)

```kotlin
suspend fun runScan(session: ScanSession, profile: DeviceProfile): AvatarProject = withCheckpoints {
    val frames   = captureStage(session)                 // Frames + Intrinsics + IMU
    val perFrame = perceptionStage(frames)               // Landmarks, Blendshapes, Posen, Masken
    val calib    = calibrateStage(frames, perFrame)      // EPnP + leichtes BA
    val coarse   = coarseFitStage(frames, perFrame, calib)   // 3DMM (Identität/Expr/Licht)
    val dense    = mvsStage(frames, perFrame, calib, coarse) // Tiefenkarten (Haut + Haar)
    val volume   = fuseStage(dense)                      // TSDF_skin + TSDF_hair
    val rawMesh  = meshStage(volume)                     // Marching Cubes + LODs
    val hair     = hairStage(rawMesh.hair, perFrame, profile.hairLevel)  // L1/L2/L3
    val reg      = registerStage(rawMesh.skin, baseHead) // NRICP
    val detail   = detailStage(reg, rawMesh.skin)        // Displacement + Detail-Normal
    val rig      = rigStage(reg, perFrame)               // Skelett, Gewichte, 52 Blendshapes
    val textures = bakeStage(reg, detail, frames, calib) // Albedo/Normal/Rough/AO/SSS/Disp
    val qa       = qualityStage(reg, dense, perFrame, textures)
    persistProject(frames, reg, hair, rig, textures, qa, session)  // .fscan
}
```
Jede `…Stage` ist: `suspend`, checkpointet, fortschrittsmeldend, thermikbewusst und einzeln testbar.
