# 02 – Architektur

Stand: 2026-11-15 · Lesereihenfolge: 02 → 03 → 04 → 05 → 06

---

## 1. Schichtenbild

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  UI (Jetpack Compose, Material 3)                                            │
│  onboarding · capture · processing · review · animate · export · settings     │
│  Design-System: Jamaika-Tokens, Night + Day Mode, i18n (DE/EN)               │
├──────────────────────────────────────────────────────────────────────────────┤
│  Domain (Kotlin, rein, testbar)                                              │
│  ScanSession · AvatarProject · QualityReport · License · Entitlement          │
│  UseCases: RunScan, RebuildModel, RetargetPose, ExportAvatar, RecordClip      │
├──────────┬──────────┬───────────┬────────────┬──────────────┬───────────────┤
│ Capture  │Perception│ Geometry  │ Rendering  │ Export       │ Vault         │
│ (Kotlin) │(Kotlin + │ Core      │ (Vulkan /  │ (Kotlin +    │ (Kotlin)      │
│ CameraX +│ TFLite / │ (C++17,   │  GLES 3.1) │  C++)        │ Room + SafeFS │
│ Camera2  │ MediaPipe│ JNI)      │            │              │ Keystore      │
│          │ Tasks)   │           │            │              │               │
├──────────┴──────────┴───────────┴────────────┴──────────────┴───────────────┤
│  Platform: Android 10+ · WorkManager · Foreground Service · Thermal API       │
│            Keystore/StrongBox · SAF · NDK r28+ (16-KB-Page-Size)             │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Regel:** Die Domain-Schicht kennt kein Android. Alles Schwerlastige liegt in C++ und läuft in einem eigenen
Prozess (``:geom`**-Prozess), damit ein OOM im Rekonstruktions-Kern die UI nicht mitreißt.

## 2. Gradle-Module

| Modul | Inhalt | Sprache |
|---|---|---|
| `:app` | Compose-UI, Navigation, DI-Holder, Application | Kotlin |
| `:core:domain` | Modelle, UseCases, State Machines | Kotlin |
| `:core:data` | Room, Vault-IO, `.fscan`-Container, Verschlüsselung | Kotlin |
| `:feature:capture` | CameraX/Camera2, Belichtungssteuerung, Guidance-Overlay | Kotlin |
| `:feature:processing` | Fortschritts-UI, Thermik-/Akku-Steuerung, Checkpointing | Kotlin |
| `:feature:animate` | Live-Tracking-UI, Regler, Clip-Aufnahme | Kotlin |
| `:feature:export` | Format-Assistent, Writer-Anbindung, SAF, Share | Kotlin |
| `:feature:paywall` | Krypto-Flow, QR, Verifikation, Lizenz-Token | Kotlin |
| `:ml:perception` | MediaPipe Tasks Wrapper, TFLite-Delegates, Landmark-Glättung | Kotlin + TFLite |
| `:engine:render` | Vulkan/GLES-Renderer, PBR, Haar-Shader, Screenshot | Kotlin + C++ |
| `:engine:geom` | **C++-Kern**: 3DMM, MVS, TSDF, Meshing, Retopo, Rig, Baking | C++17 (JNI) |
| `:engine:export` | **C++-Writer**: alle Dateiformate | C++17 (JNI) |
| `:engine:thirdparty` | Vendorte Permissiv-Bibliotheken (siehe `09`) | C/C++ |
| `:design` | Design-Tokens, Farben, Typografie, Komponenten | Kotlin (Compose) |

## 3. Tech-Stack mit Begründung

| Ebene | Wahl | Begründung | Verworfen |
|---|---|---|---|
| UI | **Jetpack Compose + Material 3** | Native Performance, gute Accessibility-APIs, kein WebView-Overhead | Flutter (schwerer C++-Ffi-Pfad bei Bildströmen), React Native (Kamera2-Tiefe) |
| Kamera | **CameraX + Camera2-Interop** | CameraX für Lifecycle/UseCases, Camera2 für `MANUAL_SENSOR` (ISO, Shutter), `LENS_INTRINSIC_CALIBRATION`, Burst-Capture | Reines Camera2 (zu viel Boilerplate) |
| Wahrnehmung | **MediaPipe Tasks (Face/Pose/Hand Landmarker, Image Segmenter)** | Apache-2.0, on-device, 478 Landmarks + 52 Blendshapes + 4×4-Pose + Haar-Segmentierung | Eigene Netze (Aufwand), kommerzielle SDKs (Gebühren/Funktionseinschränkungen) |
| Inferenz | **TFLite GPU-Delegate, Fallback NNAPI → XNNPACK (CPU, 4 Threads)** | Breite Geräteabdeckung; NNAPI auf Qualcomm/Hexagon deutlich schneller | Nur GPU (zu viele Geräte ohne zuverlässigen Delegaten) |
| Schwerlast | **C++17 + Vulkan-Compute**, Fallback **OpenGL ES 3.1 Compute** | MVS + TSDF-Fusion sind speicherbandbreiten-limitiert; Vulkan-Compute ist auf Android ab API 27 breit verfügbar | RenderScript (deprecated), reines Java (zu langsam), OpenCL (nicht offiziell) |
| Scheduling | **WorkManager + Foreground Service (Typ `specialUse`/`camera`) + Partial WakeLock** | Lange Jobs (bis 8 min) müssen überleben; Resumability out of the box | Nur Coroutine im ViewModel (stirbt mit dem Prozess) |
| Daten | **Room + App-spezifischer Speicher + SAF-Export** | Strukturierte Metadaten + Dateien unter Nutzerkontrolle | ContentProvider, MediaStore für Projekte |
| Sicherheit | **AES-256-GCM, Schlüssel in Android Keystore (StrongBox wenn vorhanden)** | Standard, hardware-backed | Eigenes Krypto, SQLCipher (extra Abhängigkeit) |
| DI | **Hilt** (nur UI/Domain), C++-Kern ohne DI | Weniger Boilerplate | Koin (Reflection/Startzeit) |
| Build | AGP aktuell, **NDK r28+**, CMake, `-DANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON` | Play-Pflicht: 16-KB-Page-Size; Fristen wurden mehrfach verlängert (zuletzt bis 2027), trotzdem ab Tag 1 erfüllen [2](https://github.com/react/react-native/issues/53649) [3](https://www.reddit.com/r/androiddev/comments/1tqd2t8/google_quietly_extended_the_16kb_page_size/) | Ältere NDKs |

## 4. Threading-/Ausführungsmodell

| Thread/Pool | Aufgabe | Priorität |
|---|---|---|
| `main` | Compose, Eingaben | Höchste |
| `camera` (CameraX-Executor, 1 Thread) | Frame-Callbacks, Kopie in Ringpuffer | Hoch |
| `perception` (2 Threads) | Landmarker/Segmenter-Inferenz | Hoch |
| `render` (1 Thread + GPU) | Vorschau, Ergebnis-Ansicht | Hoch |
| `geom` (N Threads = `min(4, bigCores)`) | MVS, Fusion, Meshing, Baking | `THREAD_PRIORITY_BACKGROUND` (damit UI nicht ruckelt) |
| `io` (4 Threads) | Vault, Export-Schreiben | Niedrig |
| `compute` (Vulkan-Queue) | Shader-Ausführung | – |

**Frame-Pipeline (Aufnahme):**
```
Camera2 (YUV 4:2:0, 1080p/4K, 30 fps Burst)
   → Ringpuffer (Double-Buffer, zero-copy ImageReader, max. 240 Frames)
   → Perception (alle N Frames; Quick: N=2, Pro: N=1)
   → Guidance-Bewertung (Schärfe/Bewegung/Abdeckung) auf dem main-Thread-Overlay
   → Akzeptanzprüfung (Gate) → persistente Ablage im .fscan-Arbeitsverzeichnis (JPEG q=95 oder RAW/HEIF wenn verfügbar)
```
Es werden **nur akzeptierte Frames** gespeichert – das spart 60–80 % Speicher und Rechenzeit.

## 5. Datenfluss (Scan → Export)

```
[1] CAPTURE        Frames + Kamera-Intrinsics + Zeitstempel + IMU-Up-Vektor
      ↓
[2] PERCEPTION     Landmarks(478) · Blendshapes(52) · Kopfpose(4×4) · Haar-Maske · Haut-Maske · Qualität
      ↓
[3] CALIBRATION    Intrinsics-Verfeinerung (Brennweite f, Verzeichnung k1..k3) via Bundle-Adjustment light
      ↓
[4] COARSE FIT     3DMM: Identität α (geteilt) + Expression β_t + Pose T_t + Beleuchtung L_t  (pro Frame)
      ↓
[5] DENSE          Plane-Sweep/PatchMatch MVS → Tiefenkarten + Konfidenz  (Haut/Haar getrennt gewichtet)
      ↓
[6] FUSION         TSDF (Hashed Voxel Grid) → Marching Cubes → Roh-Mesh  (+ Poisson-Variante)
      ↓
[7] HAIR           Haar-TSDF → Haar-Mesh → Orientierungsfeld (Gabor) → Karten (L2) / Strähnen (L3)
      ↓
[8] REGISTER       Non-Rigid ICP: FaceScan-Basiskopf → Scan  (Deformationsgraph, embedded deformation)
      ↓
[9] DETAIL         Displacement-Map (16/32-bit), Normal-Map, Cavity/AO aus hochfrequenten Resten
      ↓
[10] RIG           Skelett (Hals/Kopf/Augen/Kiefer) + 52 Blendshape-Deltas + Gewichte (LBS/DQBS)
      ↓
[11] TEXTURE       UV-Atlas → Multi-View-Baking: Albedo, Normal, Roughness, AO, SSS, Displacement
      ↓
[12] QA            Qualitätsbericht (Reprojektion, Photometrie, Silhouetten-IoU, Watertightness)
      ↓
[13] STORE         .fscan-Projekt (verschlüsselt) + Thumbnail + LODs
      ↓
[14] ANIMATE       Live-Tracking → Blendshape-/Gelenk-Buffer → .fsmc-Clip
      ↓
[15] EXPORT        Szene-IR (Mesh/Rig/Morphs/Maps/Animation) → Format-Writer → SAF-Zielordner
```

Jede Stufe schreibt ein **Checkpoint-Fragment** (`.stage<N>.bin` + JSON-Manifest). Unterbrechung → Resume
bei der letzten abgeschlossenen Stufe.

## 6. Szene-IR (das Austauschformat intern → Export)

Alle Writer arbeiten auf derselben Intermediate Representation. Das ist der wichtigste Baustein der Export-Schicht:

```kotlin
// :core:domain – bewusst framework-frei, 1:1 nach C++ spiegelbar
data class SceneIR(
    val units: Units,                     // METERS | CENTIMETERS | MILLIMETERS
    val upAxis: Axis,                     // Y | Z
    val handedness: Handedness,           // RIGHT | LEFT
    val nodes: List<Node>,                // Hierarchie (Transform, Mesh?, Skeleton?, Camera?)
    val meshes: List<MeshIR>,             // Positionen/Normale/Tangenten/UVs/Indizes/LODs
    val morphTargets: List<MorphIR>,      // Name (ARKit-Namen), Deltas, Gewicht
    val skeleton: SkeletonIR?,            // Gelenke, Hierarchie, Bind-Matrizen, Skin-Weights
    val materials: List<MaterialIR>,      // PBR: albedo/normal/rough/metal/ao/emissive/sss/disp
    val images: List<ImageIR>,            // Pixel + Format + Bit-Tiefe (PNG/JPEG/EXR/WebP)
    val animations: List<AnimationIR>,    // Kanäle: Translation/Rotation/Scale/Morph-Gewichte
    val curves: List<CurveIR>?,           // Haar-Strähnen (Basis-Curves)
    val metadata: ProvenanceIR            // C2PA-Claims, FaceScan-Version, Modell-Hashes, Lizenz
)
```
Jeder Writer ist eine reine Funktion `SceneIR + ExportOptions → ByteArray/File`. Dadurch ist die
Export-Validierung testbar (Golden-Files), und neue Formate sind "nur" ein Writer.

## 7. Offline-First-Regeln (verbindlich für jedes Feature)

1. **Kein Netzwerk im Kernpfad.** `INTERNET` wird nur von `:feature:paywall` und dem optionalen Kurs-Modul
   benutzt. Der Rekonstruktionsprozess läuft in einem Prozess ohne Netzwerk-Stack-Zugriff (SE-Linux-frei
   interpretiert: keine Socket-Nutzung – im Review per Code-Freeze geprüft).
2. **Modelle liegen im APK** (Install-Time-Asset-Pack). Schwere/optionale Modelle als On-Demand-Asset-Pack,
   aber einmal geladen immer offline verfügbar.
3. **Alle Artefakte lokal.** Projekte, Clips, Lizenzen, Quittungen, Logs: app-privater Speicher + expliziter
   Nutzer-Export über SAF.
4. **Kein Konto.** Identität = Gerät + lokaler Schlüssel. Wiederherstellung über signierte Quittung (Tx-Hash).
5. **Offline-Arbeit ist nie blockiert** – auch wenn eine Lizenzprüfung gerade nicht möglich ist (Grace-Periode).
6. **Degradation statt Abbruch:** fehlender GPU-Delegate → CPU-Pfad; zu wenig RAM → Reduced-Profile;
   Hitze → Frame-Reduktion statt Absturz.
7. **Determinismus:** gleiche Eingabe → gleiches Ergebnis (keine Zufalls-Seeds in rekonstruierenden Schritten,
   oder Seed wird im Projekt gespeichert).
8. **Transparenz:** Ein "Datenschutz-Monitor" in den Einstellungen listet, was die App auf welchem Weg
   verlässt (Antwort im Kern: **nichts**).

## 8. Geräteklassen-Profile

| Klasse | Erkennung | Frames (Standard) | MVS-Auflösung | Textur | Haar-Stufe | Erwartete Dauer (Standard) |
|---|---|---|---|---|---|---|
| **Low** | ≤ 4 GB RAM, ≤ 6 Big-Cores | 24 | ¼ (≈ 480 p) | 2K | L1 (Cap) | 240 s |
| **Mid** | 6–8 GB, Mittelklasse-SoC | 48 | ½ (≈ 960 p) | 4K (2K Free) | L2 (Cards) | 180 s |
| **High** | ≥ 12 GB, Flaggschiff-SoC, NNAPI/NPU | 96–120 | ½–¾ | 8K | L3 (Strands) | 120 s |

Erkennung: `ActivityManager.isLowRamDevice()`, `totalMem`, `Build.SOC_MODEL`-Whitelist, Self-Benchmark
beim ersten Start (5-Sekunden-Mikrobenchmark: TFLite-Inferenz, Vulkan-Durchsatz, Speicherbandbreite) →
Ergebnis im Projekt gespeichert und in den Einstellungen überschreibbar ("Qualität erzwingen").

## 9. Performance-Budget (Standard-Scan, Mittelklasse)

| Stufe | Budget | Anmerkung |
|---|---|---|
| Aufnahme | 60 s (Nutzerzeit) | geführt, 48 akzeptierte Frames |
| Perception | 8 s | 48 × (Landmarker + Segmenter), GPU/NNAPI |
| Kalibrierung + Coarse-Fit | 15 s | Gauss-Newton, C++, 4 Threads |
| MVS | 55 s | Vulkan-Compute, ½ Auflösung, 48 × 8 Sweeps |
| Fusion + Meshing | 20 s | TSDF 512³-Äquivalent (hashed), Marching Cubes |
| Haar | 18 s | Haar-TSDF + Orientierungsfeld + Karten |
| Registrierung + Rig | 25 s | NRICP (Deformationsgraph ~1 500 Knoten) |
| Textur-Baking | 30 s | 4K-Atlas, Multi-View-Blending |
| QA + Speichern | 5 s | inkl. Thumbnail + LODs |
| **Summe** | **≈ 236 s** | Ziel ≤ 180 s → Optimierungsauftrag für M2/M3 |

Optimierungshebel (in dieser Reihenfolge): MVS auf ¼-Auflösung mit anschließender photometrischer
Verfeinerung; NRICP auf 2 Level; Baking auf GPU; Perception parallel zur Aufnahme (on-the-fly).

## 10. Thermik, Akku, Unterbrechungen

- **PowerManager**: `getThermalHeadroom(forecastSeconds)` (API 31+) bzw. `OnThermalStatusChangedListener`
  als Fallback. Reaktion:
  `LIGHT` → nichts · `MODERATE` → MVS ½ → ¼, Threads 4 → 3 · `SEVERE` → Job pausieren, Nutzer informieren
  ("Kurz abkühlen lassen – wir machen genau hier weiter", Fortsetzung per Knopfdruck oder automatisch) ·
  `CRITICAL/SHUTDOWN` → Checkpoint + sauberer Stopp.
- **Akkuschutz**: Pro-Modus startet nur bei ≥ 35 % oder angestecktem Ladegerät; Warnung bei < 15 %
  ("Wir speichern jetzt – bitte laden").
- **Unterbrechungen**: Telefonat, App-Wechsel, Bildschirm aus → Job läuft im Vordergrund-Service weiter
  (Benachrichtigung mit Fortschritt + "Abbrechen").
- **Speicherplatz**: vor Start ≥ 2,5 GB frei gefordert (Pro: 5 GB); bei < 500 MB während des Laufs →
  sauberer Abbruch mit Checkpoint.

## 11. Fehlerbehandlung (Grundsätze)

| Fehlerklasse | Verhalten |
|---|---|
| Aufnahme (zu dunkel, verwackelt, Brille) | Sofortige, konkrete Korrekturanweisung im Overlay; Frame verwerfen; kein Abbruch |
| Tracking-Verlust in ≤ 20 % der Frames | Frames verwerfen, Abdeckungsanzeige zeigt Lücke, Nachaufnahme gezielt ("bitte noch einmal die linke Seite") |
| Tracking-Verlust > 20 % | Ergebnis trotzdem erzeugen (3DMM-Only-Fallback), Qualitätsbericht auf "Gelb", Hinweis "Für bessere Details bitte erneut scannen" |
| OOM | Automatischer Neustart der Stufe im Reduced-Profile (kleinere Voxel-Auflösung, ¼-MVS), Fortschritt bleibt erhalten |
| Writer-Fehler | Rollback der Zieldatei, Fehlerprotokoll in Laiensprache, "Als GLB speichern?"-Ausweichangebot |
| Lizenz-/Kauf-Fehler | Nie blockierend: lokaler Entitlement-Cache bleibt gültig, Hinweis mit Tx-Hash und Support-Mail |

## 12. Sicherheit des App-Betriebs

- ProGuard/R8 + Obfuskierung; C++-Symbole gestrippt.
- Kein `android:debuggable` im Release; `android:allowBackup="false"` (biometrische Daten!);
  `android:dataExtractionRules` so konfiguriert, dass der Tresor nicht in Cloud-Backups wandert.
- Keine WebViews (spart Angriffsfläche); Landingpage-Links öffnen im Browser.
- Modell-Dateien mit Prüfsumme (im APK verankert) → Manipulationsschutz.
- Alle nativen Buffer mit Bound-Checks; Fuzzing der Writer gegen kaputte Meshes (siehe `10`).
