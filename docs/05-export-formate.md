# 05 – Export: alle Profi-3D-Formate

Stand: 2026-11-15 · Grundlage: `SceneIR` aus `02-architektur.md` · Layout der Writer in `:engine:export`

---

## 1. Philosophie: nicht "viele Formate", sondern "das richtige Format für dein Ziel"

Der Nutzer wählt **nicht** ein Format, sondern ein Ziel. Der **Format-Assistent** übersetzt:

| "Ich will es nutzen für …" | Empfehlung | Einstellungen (automatisch) |
|---|---|---|
| **Blender** | `.fbx` (mit Rig + Morphs) oder `.abc` (nur Geometrie) + Textur-Set | m, Z-up, Normal OpenGL, PNG 16-bit, Displacement EXR |
| **ZBrush / Bildhauerei** | `.obj` (neutral, hohe Auflösung) + `.abc` als Alternative | m, Y-up, keine Morphs, dichte Mesh-Version |
| **Maya / 3ds Max / Cinema 4D** | `.fbx` (binär) + Textur-Set | cm (wählbar), Y-up, Morphs als BlendShape-Deformer |
| **Houdini** | `.abc` + `.usda` | m, Y-up, Point-Cache + Szenenbeschreibung |
| **Unreal Engine 5** | `.fbx` (Skeletal Mesh + Morph Targets) oder `.usdz`/`.usda` (Interchange) | cm, Z-up, Normal DirectX, 4K |
| **Unity 6** | `.fbx` (Humanoid-Rig-fähig) oder `.glb` | m, Y-up, Normal OpenGL, 2K–4K |
| **Godot / Web / Three.js / Babylon** | `.glb` (alles eingebettet) | m, Y-up, Normal OpenGL, 2K (Free: 2K/20k Tris) |
| **Substance Painter** | `.fbx` oder `.obj` + Textur-Set | m, Y-up, High-Poly + Low-Poly-Set |
| **3D-Druck (Büste)** | `.stl` (binär, watertight, mit Sockel) + optional `.ply` | mm, Z-up, geschlossenes Mesh, Wandstärkenprüfung |
| **VRChat / VTuber / VRM-Apps** | `.vrm` (glTF-basiert) oder `.glb` mit ARKit-Morphs | m, Y-up, 2K, 52 Morphs |
| **Apple / AR Quick Look / visionOS** | `.usdz` | m, Y-up, unkomprimiertes ZIP, 64-Byte-Alignment |
| **Datenaustausch/Archiv** | `.dae`, `.ply`, `.obj`, `.fscan` | m, Y-up |
| **Nur Animation weitergeben** | `.bvh` + `.abc` (Point-Cache) + `.csv` | m, Y-up |
| **Weiterarbeit am Projekt** | `.fscan` (verlustfrei, alles drin) | – |

Der Assistent erklärt jede Empfehlung in einem Satz ("FBX, weil Blender damit Rig und Mimik in einem Schritt
übernimmt.") und lässt sich jederzeit von "Profi-Modus" (alle Formate frei) überstimmen.

## 2. Formatmatrix

| Format | Ext | Tier | Geometrie | Morphs | Rig/Skin | Material/Textur | Animation | Haar (Kurven) | Writer-Aufwand |
|---|---|---|---|---|---|---|---|---|---|
| **glTF 2.0 / GLB** | `.gltf`, `.glb` | Free | ✔ (incl. LODs) | ✔ (core, animierbar über `node.weights`) | ✔ (Skin/Inverse-Bind) | ✔ PBR + eingebettet | ✔ | Karten als Mesh | mittel |
| **Wavefront OBJ** | `.obj` + `.mtl` | Free | ✔ | ✘ (kein Standard) – optional als Zusatzdateien | ✘ | ✔ (MTL) | ✘ | Mesh | **niedrig** |
| **Stanford PLY** | `.ply` | Free | ✔ (+ Vertexfarben) | ✘ | ✘ | Vertexfarben | ✘ | Mesh | **niedrig** |
| **Stereolithography** | `.stl` | Free | ✔ (watertight) | ✘ | ✘ | ✘ | ✘ | ✘ | **niedrig** |
| **Collada** | `.dae` | Creator | ✔ | ✔ (`morph` im Controller) | ✔ | ✔ | ✔ | Mesh | mittel |
| **USD / USDZ** | `.usda`, `.usdz` | Creator | ✔ | ✔ (`UsdSkel` BlendShapes) | ✔ (`UsdSkel`) | ✔ (`UsdPreviewSurface`) | ✔ | ✔ (`BasisCurves`) | hoch |
| **FBX (binär 7.5)** | `.fbx` | Creator | ✔ | ✔ (`BlendShape` + `BlendShapeChannel`) | ✔ (`Skin`/`Cluster`) | ✔ | ✔ | Karten als Mesh | **hoch** |
| **Alembic** | `.abc` | Studio | ✔ (inkl. Point-Cache) | via Cache | ✔ (Xform) | Material-Referenz | ✔ (Cache) | ✔ (`ICurves`) | mittel (Lib) |
| **BVH (Motion)** | `.bvh` | Studio | – | – | ✔ | – | ✔ (Skelett) | – | **niedrig** |
| **VRM (glTF-Extension)** | `.vrm` | Studio | ✔ | ✔ (ARKit-Presets) | ✔ (humanoid) | ✔ (MToon/Standard) | ✔ | Mesh | mittel |
| **CSV/JSON (Motion)** | `.csv`, `.json` | Studio | – | ✔ | ✔ | – | ✔ | – | **niedrig** |
| **FaceScan-Projekt** | `.fscan` | Free | ✔ (alles, verlustfrei) | ✔ | ✔ | ✔ | ✔ | ✔ (alle Stufen) | niedrig |
| **Blender-Bridge** | Add-on | Free | Import von `.fscan` | ✔ | ✔ | ✔ | ✔ | ✔ | mittel (Python) |

**Nicht enthalten (bewusst):** `.blend`, `.max`, `.ma/.mb`, `.c4d`, `.ztl`, `.zpr`, `.spp`, `.tbscene`,
`.lwo`, `.3ds`. Das sind **programmeigene** Formate; sie werden über die Zielsoftware selbst erzeugt.
Die Brücke dorthin ist FBX/ABC/USD/OBJ + unser Blender-Add-on (Kapitel 9).

## 3. Writer-Architektur

```
                    ┌──────────────────────────┐
  .fscan-Projekt →  │  SceneBuilder (C++)      │  → SceneIR (Vollszene)
                    └──────────────────────────┘
                                 ↓
     ┌────────────────────────────┼────────────────────────────┐
     │  Transform-Pass            │  Validate-Pass             │  Attach-Pass
     │  · Einheiten (m/cm/mm)     │  · NaN/Inf-Check           │  · Texturen einbetten|extern
     │  · Achsen (Y/Z-up)         │  · Index-Range-Check       │  · Kanal-Konvertierung (Normal DX/GL)
     │  · Händigkeit              │  · Dreiecks-Degenerierung   │  · Metadaten/Provenance (C2PA)
     │  · Skalierung/Offset       │  · UV-Bounds [0,1]          │  · Kompression (PNG/JPEG/WebP/EXR)
     │  · Morph-Referenzprüfung   │  · Manifest-Konsistenz      │  · LOD-Auswahl
     └────────────────────────────┴────────────────────────────┘
                                 ↓
        IWriter::write(const SceneIR&, const ExportOptions&, Sink&) → Result
        ├── GlbWriter  ObjWriter  PlyWriter  StlWriter  DaeWriter
        ├── UsdWriter  FbxWriter  AbcWriter  BvhWriter  VrmWriter
        └── FscanWriter (Verlustfrei)
```

**Prinzipien:**
1. **Ein IR, viele Writer.** Neue Formate kosten nur einen Writer, nie Änderungen an der Pipeline.
2. **Jeder Writer ist deterministisch** (gleiche Eingabe ⇒ bytegleiche Ausgabe; nötig für Golden-File-Tests
   und für reproduzierbare Prüfsummen in der Provenienz).
3. **Jeder Writer liefert eine Warnliste** ("Morphs in OBJ nicht unterstützt – als 52 Extra-Dateien
   geschrieben") – diese Warnungen erscheinen in der App in Laiensprache.
4. **Kein Writer verlässt das Gerät.** Alles lokal, keine Konvertierungs-API, kein Cloud-Dienst.
5. **Fail-clean:** Fehler ⇒ Zieldatei wird gelöscht (keine halben Dateien), Rückmeldung mit Ausweichvorschlag.

## 4. Formate im Detail

### 4.1 glTF 2.0 / GLB (Basisformat, immer dabei)
- **Struktur:** `scenes/nodes/meshes/accessors/bufferViews/buffers`, GLB = 12-Byte-Header + JSON-Chunk
  (`0x4E4F534A`) + BIN-Chunk (`0x004E4942`), 4-Byte-Alignment mit Padding.
- **Morphs:** `mesh.primitives.targets` (nur `POSITION` + optional `NORMAL`), `mesh.extras.targetNames`
  (ARKit-Namen!), `node.weights` – damit sind Morphs in **jedem** glTF-Viewer nutzbar und per
  `animation.channels` mit `path: "weights"` animierbar.
- **Material:** `KHR_materials_pbrSpecularGlossiness` **nicht** nutzen (deprecated) – stattdessen
  metallisch/rau + `KHR_materials_emissive_strength` falls nötig; `KHR_texture_transform` für Atlas-Offsets.
- **Optionen:** Draco/Meshopt **bewusst nicht** (zusätzliche Dekoder-Pflicht in Zielsoftware, Lizenz- und
  Qualitätsdiskussion) – stattdessen unsere eigene LOD-Kette.
- **Größe:** 20 k Tris/2K (Free) bis 300 k/8K (Studio).

### 4.2 OBJ + MTL
- Eine OBJ-Datei pro LOD. `v`, `vn`, `vt`, `f v/vt/vn`. Materialbibliothek mit allen Maps.
- **Morph-Ersatz:** Option "Blendshapes als OBJ-Satz" ⇒ 52 weitere `.obj` (nur die Deltas). Wird in der
  UI als solches erklärt, weil es genau die häufigste Anfänger-Falle ist.
- Koordinaten: Achsenkonvertierung per Option (siehe 6).

### 4.3 PLY / STL
- **PLY:** binary_little_endian 1.0, Properties `x,y,z`, `nx,ny,nz`, `s,t`, `red,green,blue` (Vertexfarben
  gebacken) – kompatibel mit CloudCompare, MeshLab, Druck-Tools.
- **STL:** binär (80-Byte-Header + uint32 Dreieckszahl + 50 Byte je Dreieck), Einheit mm,
  **watertight-Variante** (Poisson), optional Sockel (Zylinder/Rundfuß, 6 mm), Wandstärkenprüfung
  (Ray-Cast: Min. 1,2 mm) mit Warnung.
- **Vereinfachte Druckfassung** (`meshes/facescan_print_lod.stl` und
  `..._hollow.stl`, seit M2b): Gröbste Fassung, die eine **Formfehlergrenze**
  einhält (p95 ≤ 0,10 mm, p99 ≤ 0,35 mm) und dabei wasserdicht bleibt — im
  Speicher und in der Datei. Massiv 100.732 Dreiecke (87 % gespart), hohl
  189.820 (84 %), statt 774.858 bzw. 1.186.382. Einzelheiten in README, Kap. 7h.
- **Hohlkörper-Variante** (`meshes/facescan_print_hollow.stl`, seit M2b): Schale mit 2,4 mm Wand
  über der Schnitthöhe, **massiver Sockel** (Schwerpunkt unten) und einem **Ablaufloch** (r = 5 mm)
  durch die Standfläche. Volumen 1171 → 542 cm³, also **54 % gespart**. Die Wand wird kalibriert
  und danach mit dem Ray-Cast nachgemessen: median 2,34 mm, p01 1,58 mm, 0,04 % der Kopfoberfläche
  unter der 1,2-mm-Grenze. Einzelheiten in README, Kap. 7g.

### 4.4 Collada (DAE 1.4.1)
- **Im Prototyp geschrieben** (`export_more.write_dae`, seit M2b): `library_geometries` mit
  positions/normals/uv (bzw. Vertexfarben statt UVs) und Dreiecksindizes, `library_images`,
  `library_effects` (`profile_COMMON`, Kette image → sampler2D → surface → lambert),
  `library_materials`, `library_visual_scenes`. Einheiten `meter="0.001"`, `up_axis Y_UP`.
- Relevanz: Austausch mit Programmen, die glTF schlechter können (ältere C4D-Versionen, diverse
  Forschungswerkzeuge) und als menschenlesbares Format für Debugging und Support.
- **Ab M3 (`python/build_rig.py`):** `library_controllers` mit `<skin>` — Gelenknamen,
  `bind_shape_matrix`, inverse Bindematrizen und `vertex_weights`. Das Netz hängt damit an
  acht Gelenken (hips → spine → chest → neck → head → jaw/linksEye/rechtsEye). Geprüft mit
  pycollada (löst die Controller-Kette auf) und assimp (zählt die Knochen, die wirklich Gewicht
  tragen). **Noch nicht:** `<morph>` (`method="NORMALIZED"`) und `library_animations`
  (Sampler/Channel) — die Mimik geht stattdessen in das GLB, das Morph-Ziele von Haus aus kann.

### 4.5 USD / USDZ
- **USDA (ASCII)** wird **von uns geschrieben** (kein USD-SDK nötig – das SDK für Android zu bauen, ist mit
  Boost/TBB/OpenSubdiv ein Projekt für sich).
- Inhalt: `UsdGeomMesh` (mit `primvars:st`, `normals`), `UsdGeomBasisCurves` für Haar-Strähnen
  (`type="cubic"`, `basis="bspline"`, `widths`, `primvars:displayColor`),
  `UsdPreviewSurface` + `UsdUVTexture` für Materialien, `UsdSkel` (`SkelRoot` → `Skeleton` → `SkelBinding`
  → `SkelAnimation`) für Rig und Animation, Blendshapes als `skel:blendShapes`/`skel:blendShapeTargets`.
- **USDZ-Packaging (zwingend, sonst Ablehnung durch Apple-Geräte)** [12](https://dev.to/cy_cy_a73a75ea2dde2b6cf02/your-usdz-will-be-rejected-by-an-iphone-three-packaging-rules-apple-doesnt-negotiate-2960):
  1. Alle Einträge **unkomprimiert** (`ZIP_STORED`, kein Deflate), 2. kein Passwort/Verschlüsselung,
  3. Datenstart jedes Eintrags auf **64-Byte-Grenze** (Padding über ZIP-Extra-Field), 4. Erster Eintrag = der
     USD-Layer, 5. nur relative Pfade, keine `..`.
- **Hinweis für die UI:** "USDZ ist für Apple-Geräte/AR Quick Look – für Blender nimm FBX oder ABC."
- **USDC (binär)**: der USDZ-Root-Layer ist seit M2b ein binäres Crate (`facescan.usdc`,
  Kennung `PXR-USDC`). Geschrieben wird in zwei Schritten: der **Inhalt** kommt aus unserem eigenen
  USDA-Schreiber (kein SDK nötig), die **Serialisierung** macht die USD-Bibliothek
  (`export_more.usda_to_usdc`). Das Crate-Format von Hand zu schreiben, wäre ein eigenes Projekt mit
  eigenem Versionsrisiko und brächte für den Scan nichts. Für den Kotlin-Spiegel gilt dasselbe:
  Inhalt selbst, Crate von einer USD-Bibliothek.
- Ausnahme: `facescan_m1.usdz` behält den **Text**-Root-Layer. Die M1-Tore prüfen den Inhalt mit dem
  eigenen Leser (§7c), und der liest Text. Die AR-Ausgabe sind die vier LOD-Pakete.

### 4.6 FBX (binär) – der anspruchsvollste Writer
- **Warum binär:** Blender unterstützt seit 2.8 **kein FBX-ASCII** mehr (Import entfernt) [11](https://projects.blender.org/blender/blender-addons/issues/79960).
  Ein ASCII-FBX-Writer (wie ihn Assimp anbietet) wäre für unser wichtigstes Zielprogramm nutzlos.
- **Warum eigener Writer:** Das Autodesk-FBX-SDK darf nicht weitergegeben werden; eine Einbindung in eine
  kommerzielle App ist praktisch ausgeschlossen. Wir schreiben **FBX 7.5 binär** nach dem öffentlich
  dokumentierten Layout (Header, Node Records, Property Records, verschachtelte Node-Hierarchie,
  Kompression optional Deflate, Footer mit Versions-Footer + Magic Bytes).
- **Muss-Inhalt für ein animierbares Asset:**
  - `Objects`: `Geometry` (Vertices, Polygons, `LayerElementNormal`, `LayerElementUV`,
    `LayerElementMaterial`), `Model` (Typ `Mesh` / `Null` / `LimbNode` / `Root`),
    `Deformer` (`Skin` + je Knochen ein `Cluster` mit `Indexes`/`Weights`/`TransformLink`),
    `Deformer` (`BlendShape` + je Form ein `BlendShapeChannel` mit `DeformPercent` und je ein
    `Geometry`-SubDeformer mit `Shape`), `Material`, `Texture`, `Video` (Bilddatei-Referenz).
  - `Connections`: `OO` (Model→Root/Eltern), `OP` (Geometry→Model, Material→Model, Texture→Material,
    Video→Texture, BlendShape→Geometry, BlendShapeChannel→BlendShape, Shape→BlendShapeChannel).
  - `Takes`/`AnimationStack` → `AnimationLayer` → `AnimationCurveNode` → `AnimationCurve`
    (Keyframe-Daten: `KeyValueFloat`, `KeyTime`) für Rotation/Translation/Scaling **und** `DeformPercent`
    (Morph-Animation).
  - `GlobalSettings` mit Einheiten (`UnitScaleFactor`, `OriginalUnitScaleFactor`) und Achsen
    (`UpAxis`, `UpAxisSign`, `FrontAxis`, `FrontAxisSign`, `CoordAxis`, `CoordAxisSign`).
  - `Pose`-Objekt (Bind Pose) – sonst stimmen die Gewichte in manchen Programmen nicht.
- **Risiko & Gegenmaßnahme:** Eigene Implementierung ⇒ Pflicht-Validierung gegen eine Matrix aus
  Programmen (siehe 8) und ein automatisierter Round-Trip-Test. Falls ein Defekt auftritt, ist
  **Alembic/ABC der dokumentierte Ausweichweg** (funktioniert in jeder DCC). Diese Fallback-Regel wird in
  der App als "Falls dein Programm das FBX nicht mag – nimm ABC" kommuniziert.

### 4.7 Alembic (ABC)
- **Bibliothek:** libalembic mit **Ogawa**-Backend (kein HDF5 nötig), Abhängigkeit Imath (BSD-3-Clause) [13](https://www.loc.gov/preservation/digital/formats//fdd/fdd000583.shtml) [14](https://github.com/AcademySoftwareFoundation/Imath).
  Lizenzen vor Einbau final verifizieren (siehe `09`).
- Inhalt: `IPolyMesh`/`ISubD` (Geometrie, UVs, Normals, `OFaceSet`), `IXform` (Hierarchie),
  `ICurves` (Haar-Strähnen, mit `widths`, `UVs`), `IObject`-Properties für Metadaten und Materialzuordnung.
- **Point-Cache-Modus:** pro Frame die Vertex-Positionen (inkl. angewandter Morphs) – die robusteste Art,
  Animation zwischen Programmen zu übergeben, weil sie keine Skin-/Morph-Interpretation braucht.
  Dateigröße: ~ (Verts × 3 × 4 Byte × Frames) ⇒ 20 k Verts, 600 Frames ≈ 144 MB (Option: nur Kopf/LOD1).

### 4.8 BVH / CSV / JSON (Motion)
- **BVH:** `HIERARCHY` mit `ROOT/OFFSET/CHANNELS/JOINT/End Site`, dann `MOTION` mit `Frames`, `Frame Time`
  und Euler-Werten (Reihenfolge `ZXY`, konfigurierbar). Kanäle: 6 pro Gelenk (Position für `hips`).
  Blendshapes passen nicht in BVH ⇒ immer als begleitende CSV/JSON schreiben und in der UI benennen.
- **CSV/JSON:** Spalten `frame, time_s, <kanalname> …` – für eigene Skripte, Forschung, Machine Learning.
- **Im Prototyp (M2b, `tools/build_motion.py`):** der Schreiber ist **allgemein** – er bekommt eine
  Hierarchie und eine Wertegruppe, nicht „ein Skelett". Der Inhalt ist die **Aufnahmebahn**: die 16
  Kameraposen, umgerechnet in die Bewegung des Kopfes vor einer festen Kamera („Drehteller").
- **Im Prototyp (M3, `python/build_rig.py`):** derselbe Schreiber, aber mit dem **echten Skelett**:
  acht Gelenke, 27 Kanäle, 120 Frames. Damit ist die Aussage von M2 eingelöst — der Schreiber war
  allgemein genug, es fehlte die Bewegung, nicht das Format. Einheiten **Meter und Grad, Y-up** –
  BVH selbst trägt keine (s. §12.1).

### 4.8b `.fsmc` (Aufnahmeformat, ab M3 fertig)
- **Kein Exportziel**, sondern der eigene Clip-Container (F-405): ZIP mit
  `manifest.json`, `meta.json` (Kanaltabelle mit Byte-Offset, Typ, min/max,
  Stufenzahl), `channels.bin` (int16, delta-kodiert, little-endian),
  optional `audio.m4a` und `provenance.json`. Spec und Maße in
  `docs/04` (4.1).
- **Warum es hier steht:** weil der Prüfer es prüft. `check_fsmc` liest den
  Clip zurück und rechnet nach, ob jeder Kanal auf dem Stufenraster liegt,
  das `meta.json` beschreibt. Ein Clip zu schreiben beweist nichts — erst
  der Rückweg zählt (29/29 in `validate_exports.py`).
- **Gemessene Größe** (voller Kanalsatz, 243 Zahlen je Frame): 0,87 MB/Minute
  roh, **0,32 MB/Minute** gezippt mit Stufen nach Bedarf. Die frühere
  Schätzung von 4,3 MB/Minute war um das 14-fache zu hoch.

### 4.9 VRM 1.0 (Avatar, ab M3 fertig)
- VRM ist **kein eigenes Format**, sondern glTF 2.0 mit angehängter
  Erweiterung `VRMC_vrm`. Es gibt deshalb keinen eigenen Writer: `write_glb`
  schreibt Netz, Skelett und Morph-Ziele, und `build_vrm.py` hängt den
  Erweiterungsblock an. Ein SDK braucht es nicht — die Spezifikation ist
  offen dokumentiert.
- **Pflichtinhalt** (`humanoid.md`, `meta.md`): 15 Knochen
  (`hips`, `spine`, `head` und je Seite `UpperLeg`, `LowerLeg`, `Foot`,
  `UpperArm`, `LowerArm`, `Hand`), dazu `meta.name`, mindestens ein
  `authors`-Eintrag und `licenseUrl = https://vrm.dev/licenses/1.0/`.
- **T-Pose** (`tpose.md`): Blick nach +Z, symmetrisch in X, Füße stehen auf
  Y=0, Arme waagerecht entlang ±X. Letzteres heißt: die **Sohle** auf 0,
  nicht das Fußgelenk — die Spec legt `foot` an den Knöchel.
- **Mimik** (`expressions.md`): jedes Preset ist freigestellt. Wir binden
  sechs: `happy`, `angry`, `surprised`, `blink`, `aa`, `oh`.
- **Blicksteuerung** (`lookAt.md`): `type: "bone"`, dreht die beiden
  Augengelenke. Die zweite Variante (`expression`) bräuchte eigene
  Blick-Morphs, die wir nicht haben.
- Kompatibilität: VRChat, VMagicMirror, Luppet, 3tene, Cluster, V-Katsu.
- **Bekannte Eigenheit:** VRM verlangt Arm- und Beingelenke, eine Büste hat
  keine. Die Gelenke sitzen anatomisch plausibel (1,28 m Körpergröße = 7,8
  Kopfhöhen) und tragen **keine Hautgewichte**. Die Datei ist damit gültig
  und verhält sich doch wie eine Büste. Das steht so in
  `results/vrm_report.json` und in Kap. 7i des Prototyp-README.

## 5. Textur-Set (bei jedem Geometrie-Export dabei)

| Map | Dateiname | Bit | Format | Hinweis |
|---|---|---|---|---|
| Albedo/BaseColor | `<name>_basecolor` | 8 (opt. 16) | PNG (opt. WebP/JPEG) | sRGB |
| Normal | `<name>_normal` | 16 | PNG | OpenGL (+Y) oder DirectX (−Y) konfigurierbar |
| Roughness | `<name>_roughness` | 8 | PNG | linear |
| AO (+Cavity) | `<name>_ao` | 8 | PNG | optional in Roughness-Grünkanal packbar |
| SSS-Maske | `<name>_sss` | 8 | PNG | nur bei "Profi-Textur-Set" |
| Displacement | `<name>_displacement` | 16/32 | PNG 16-bit oder **EXR** | mm, Mittelwert 0 ⇒ **32-bit float mit Offset-Metadatum** |
| Haar-Alpha/Sheen | `<name>_hair_*` | 8 | PNG | bei Haar-Karten |

**Kanal-Packing-Optionen:** `ORM` (AO/Roughness/Metallic in einem Bild, Unreal-Standard),
`ARM` (glTF-Standard). Der Assistent wählt passend zum Ziel.

**EXR:** Wir binden einen kompakten EXR-Writer ein (OpenEXR/Imath sind BSD-3-lizenziert und auf Android
baubar; alternativ ein minimaler 16-bit-PNG-Pfad für Nutzer, die kein EXR wollen).

## 6. Einheiten, Achsen, Händigkeit

| Ziel | Einheit | Up-Achse | Front-Achse | Händigkeit | Normal-Map |
|---|---|---|---|---|---|
| Blender (FBX/OBJ) | m | **Z** | −Y | Rechts | OpenGL |
| Maya | cm | **Y** | Z | Rechts | OpenGL |
| 3ds Max | cm | **Z** | Y | Rechts | OpenGL |
| Unreal | cm | **Z** | X | Links | **DirectX** |
| Unity | m | **Y** | Z | **Links** | OpenGL |
| glTF/Web/Godot | m | **Y** | +Z | Rechts | OpenGL |
| USD/Houdini | m | **Y** | −Z | Rechts | OpenGL |
| 3D-Druck (STL) | mm | **Z** | – | Rechts | – |

**Regel:** Der Nutzer sieht diese Tabelle nie. Er wählt "Blender" – der Assistent setzt alles. Im
Profi-Modus sind Einheit/Up-Achse/Händigkeit/Normal-Konvertierung einzeln einstellbar, mit Live-Vorschau
der Achsen-Gizmo.

## 7. Haar im Export

| Haar-Stufe | OBJ/STL/PLY | glTF/GLB | FBX | USD/USDZ | ABC |
|---|---|---|---|---|---|
| L1 Cap | Mesh | Mesh | Mesh | Mesh | Mesh |
| L2 Cards | Mesh + Alpha-Atlas (Funktioniert überall, aber Alpha-Reihenfolge beachten) | Mesh + `alphaMode: MASK/BLEND` | Mesh + Transparenz-Material | Mesh + `UsdPreviewSurface` mit Opacity | Mesh |
| L3 Strands | **nicht darstellbar** – Warnung + Fallback auf L2 | Als Kurven **nicht** in glTF ⇒ Fallback L2 + Hinweis | Fallback L2 (FBX hat keine Kurven) | ✔ `UsdGeomBasisCurves` | ✔ `ICurves` |

**Wichtig für die Ehrlichkeit der App:** In der Export-Vorschau steht bei L3 + glTF sinngemäß:
"Deine Haar-Strähnen können in diesem Format nicht gespeichert werden – wir exportieren die Haar-Karten
(Stufe 2). Für echte Strähnen nimm USD oder ABC." Genau diese Transparenz verhindert Support-Fälle.

## 8. Validierung (vor jedem Release)

**Round-Trip-Test (automatisch):** Jedes Format wird geschrieben und mit einer zweiten, unabhängigen
Implementierung wieder gelesen (z. B. Python: `trimesh`/`pygltflib` für glTF, `Open3D` für PLY/OBJ,
`usd-core` für USDA, `bpy` für FBX/ABC) und gegen das `SceneIR` verglichen:
- Vertexzahl ± 0, Indexzahl ± 0, Positionen max. Abweichung < 1e-5 (Einheiten),
- Morph-Namen identisch und in identischer Reihenfolge,
- Texturen bitgleich (Prüfsumme),
- bei Animation: Frames × Kanäle identisch, max. Abweichung < 1e-4.

**Zielprogramm-Matrix (manuell, je Release, mit Screenshot-Protokoll):**

| Programm | GLB | FBX | ABC | USDA/USDZ | OBJ | DAE | STL |
|---|---|---|---|---|---|---|---|
| Blender 4.x | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| Maya 2025 | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | – |
| 3ds Max 2026 | ✔ | ✔ | ✔ | – | ✔ | ✔ | – |
| Unreal 5.5 | ✔ | ✔ | ✔ | ✔ (Interchange) | ✔ | – | – |
| Unity 6 | ✔ | ✔ | – | – | ✔ | – | – |
| Houdini 20 | ✔ | ✔ | ✔ | ✔ | ✔ | – | – |
| ZBrush 2025 | – | ✔ | – | – | ✔ | – | – |
| Substance Painter | ✔ | ✔ | – | – | ✔ | – | – |
| Godot 4 | ✔ | ✔ | – | – | ✔ | – | – |
| Apple Quick Look | – | – | – | ✔ | – | – | – |
| PrusaSlicer/Cura | – | – | – | – | – | – | ✔ |

(jeweils "zu prüfen und mit Protokoll zu belegen" – das ist die Release-Checkliste in `10`.)

## 9. Die "Blender-Bridge": FaceScan Link (Add-on)

Für alles, was wir nicht selbst schreiben (`.blend`, `.spp`, proprietäre Formate, Retopologie-Workflows),
liefern wir ein **eigenes Blender-Add-on** (Python, GPL-kompatibel, da add-on):

- Importiert `.fscan` **verlustfrei**: Mesh-LODs, 52 Blendshapes in korrekter Benennung (als Shape Keys),
  Rig, Vertexgruppen, alle Textur-Maps (korrekt verknotet als Principled-BSDF), Haar-Karten und
  Haar-Strähnen (als Curves-Objekt), Motion-Clips als Actions.
- Exportiert aus Blender heraus in alles, was Blender kann (`.blend`, FBX, USD, ABC, glTF, …).
- Enthält Presets: "MetaHuman-Übergabe", "Unreal-Übergabe", "Substance-Übergabe", "3D-Druck".
- Vertrieb: kostenlos auf der Landingpage, Quellcode auf GitHub (GPL), Versions-Kompatibilität mit
  Blender 4.2+ (Extensions-Plattform).

## 10. Umsetzungsreihenfolge der Writer

| Welle | Formate | Begründung |
|---|---|---|
| 1 | `.fscan`, OBJ+MTL, PLY, STL, GLB/glTF | Einfach, deckt 3D-Druck, Web, Godot, Unity, Substance |
| 2 | USDA + USDZ, DAE | Text-/XML-basiert, kein Fremdcode, deckt Apple/Houdini/Alt-DCC | **alle drei fertig** |
| 3 | FBX (binär) | Größter Aufwand, größter Nutzen (Blender/Maya/Max/Unreal/Unity) | **fertig** (7.5 binär) |
| 4 | ABC (libalembic) | Für Houdini/Point-Cache/Haar-Kurven | **fertig** (Ogawa, eigener Schreiber) |
| 5 | BVH, CSV/JSON, VRM | Motion-/VTuber-Spezialfälle | **alle fertig** (BVH mit Skelett ab M3, VRM 1.0 ab M3) |

## 11. Lizenz-Hinweise der eingesetzten Fremd-Bibliotheken (Kurzfassung, Detail in `09`)

| Bibliothek | Lizenz | Nutzung | Prüfstatus |
|---|---|---|---|
| Eigenentwicklung (alle Writer) | proprietär | – | – |
| Imath / OpenEXR | BSD-3-Clause | Vektor-Mathematik, EXR-Writer | vor Einbau final verifizieren |
| Alembic (Ogawa) | BSD-3-Clause (verifizieren) | ABC-Writer | vor Einbau final verifizieren |
| PoissonRecon | MIT | Wasserdichte Mesh-Variante | bestätigt [8](https://github.com/mkazhdan/PoissonRecon) |
| Open3D (optional, nur Tools) | MIT | Test-/Validierungs-Toolchain | bestätigt [15](https://www.open3d.org/paper.pdf) |
| Eigen (MPL-2) | MPL-2 (dateibezogen) | Lineare Algebra im C++-Kern | dynamisch linken, unverändert verwenden |
| **Assimp** | BSD-3-Clause | **nur für Tests/Referenz**, nicht im Produkt (schreibt nur FBX-ASCII) | bestätigt [16](http://www.assimp.org/index.php?id=11:faq) |
| **GPL/AGPL-Code (VCGLib, MeshLab, Blender-Quelltext)** | **verboten** | – | Ausschluss in der Build-Pipeline erzwungen (siehe `09`) |

## 12. Umsetzungsstand M2 (Prototyp, gemessen)

Stand: `prototype/reference/python/facescan_ref/export_more.py`, geprüft mit
`prototype/reference/python/validate_exports.py`.

| Format | Writer | Rücklese (eigen) | Fremdleser |
|---|---|---|---|
| OBJ | `export_mesh.py` | identisch bis 5e-7 mm | trimesh ✔ |
| PLY (binär) | `export_mesh.py` | identisch bis 4e-6 mm | trimesh ✔ |
| GLB | `export_mesh.py` | identisch bis 4e-6 mm | trimesh ✔ |
| STL (binär + ASCII) | `export_more.py` | 257.044 Facetten, 4e-6 mm | trimesh ✔ |
| STL (Hohlkörper) | `tools/build_hollow.py` | wasserdicht, Euler 2, Ablaufloch begehbar, Wand 2,34 mm (median) | trimesh ✔ |
| USDA | `export_more.py` | Indizes identisch | `usd-core` (Pixar) ✔ |
| USDZ | `export_more.py` | 5 Apple-Regeln nachgemessen | `usd-core` ✔ |
| FBX 7.5 (binär) | `export_more.py` | 130.829 Punkte, Polygon-Konvention ✔ | assimp ✔ |
| Alembic (ABC, Ogawa) | `export_more.py` | `AbcGeom_PolyMesh_v1` | Alembic 1.8.12 ✔ |
| DAE (Collada) | `export_more.py` | 130.829 Punkte identisch (0,0 mm), Indizes identisch | assimp ✔, pycollada ✔ |
| BVH (Motion) | `export_more.py` | 16 Frames, 6 Kanäle, größter Sprung 10,0°/Frame | assimp ✔ |
| CSV / JSON (Motion) | `export_more.py` | 16 Frames × 6 Kanäle, identisch bis 5e-7 | stdlib `csv`/`json` ✔ |

**Entscheidung gegen libalembic im Produkt:** §4.7 sah die Bibliothek vor. Im
Prototyp ist der Ogawa-Container selbst geschrieben (~250 Zeilen). Grund: die
Abhängigkeit (Alembic + Imath) kostet mehrere Megabyte Binary und ein
CMake-Build pro Plattform; der Container selbst ist trivial. Für den
Point-Cache-Modus mit vielen Frames (§4.7) ist die Bibliothek trotzdem die
bessere Wahl – das ist eine M3-Entscheidung, hier bewusst offengehalten.

### 12.1 Harte Details, die in keinem Tutorial stehen

Wer diese Writer nach Kotlin oder C++ portiert, braucht diese Liste – sie ist
aus echten Fehlermeldungen fremder Leser entstanden:

**FBX 7.5 (binär)**
1. Property-Typcodes: **Großbuchstabe = ein Wert, Kleinbuchstabe = Array.**
   `Y`(int16) `C`(bool) `I`(int32) `F`(float) `D`(double) `L`(int64)
   `S`(String, 4-Byte-Länge vorab) `R`(Raw). Arrays: `y c i f d l`, je
   gefolgt aus `uint32 Anzahl, uint32 Kodierung, uint32 Bytezahl, Daten`.
2. `EndOffset` ist eine **absolute Dateiposition**, keine Länge.
3. Die Kinderliste wird von einem **25-Byte-Nullknoten abgeschlossen** (bei
   FBX < 7.5: 13 Byte). Der Nullknoten steht **hinter** den Kindern.
4. Knotennamen dürfen **kein 0x00** enthalten. Im `Objects`-Abschnitt heißen
   die Knoten `Geometry` / `Model`; der Objektname steht in Property 1 in der
   Form `Name 0x00 0x01 Klasse`, Property 2 ist das Klassen-Tag (`"Mesh"`).
   Der Trenner ist **0x00 0x01**, nicht 0x00 0x00.
5. `Vertices` und `PolygonVertexIndex` sind **Unterknoten** von `Geometry`.
6. Der **letzte** Index jedes Polygons wird negiert und um 1 verringert
   (aus `i` wird `-i-1`).
7. `Connections` braucht **beide** Kanten: `Geometry → Model` **und**
   `Model → 0` (Wurzel). Ohne die zweite hängt das Modell nirgends.
8. `GlobalSettings`: `UnitScaleFactor = 0.1` (wir schreiben mm, FBX rechnet
   intern in cm) plus Achsen (`UpAxis 1`, `FrontAxis 2`, `CoordAxis 0`).

**Alembic / Ogawa**
9. Dateikopf: `"Ogawa"` + **frozen-Byte 0xff** + `uint16` Version (big-endian,
   Wert 1) + `uint64` Position der Wurzelgruppe. Mit frozen = 0 lehnt die
   echte Bibliothek die Datei ab: *„Ogawa file not cleanly closed while being
   written“*.
10. Kindpositionen in einer Gruppe sind **absolut**; oberstes Bit gesetzt =
    Datenblock, nicht gesetzt = Gruppe. Position 0 = leere Gruppe,
    `1<<63` = leere Daten.
11. Property-Header sind **bitgepackt** in einem `uint32` (Typ, POD, Extent,
    „konstant“, „homogen“, Metadaten-Index, Größen-Hint). Ein falsches Bit und
    der Leser glaubt, es gebe null Samples.
12. `.selfBnds` liegt **innerhalb** von `.geom`, nicht daneben.
13. Der 16-Byte-Digest vor jedem Sample ist ein SpookyHash der Nutzlast. Wir
    schreiben Nullen – kein Leser prüft ihn beim Öffnen, aber `abcinfo` zeigt
    ihn falsch an.

**USD / USDZ**
14. USDZ: alle Einträge `ZIP_STORED`, erster Eintrag = Primär-Asset, und der
    **Datenanfang auf 64-Byte-Grenze**. Die Ausrichtung erreicht man über das
    ZIP-Extra-Field (Pixar `usdzip` benutzt Kennung `0x1986` mit Nullen),
    **nicht** durch Auffüllen mit Nullen.
15. AR Quick Look verlangt als Root-Layer ein binäres `.usdc`-Krate:
    Apple Reality Converter lehnt ein Paket mit Text-Root-Layer ab
    ("the package's root layer must be a usdc file"). Seit M2b schreiben
    die LOD-Pakete deshalb ein Crate (s. §12.3). Nebenbei: das Crate ist
    rund 3,8× kleiner als der Text -- LOD0 von 24,9 MB auf 7,0 MB.
16. Die 64-Byte-Grenze gilt für den Datenanfang **jedes** Eintrags, nicht
    nur des ersten. Wer die Polsterung nur für den ersten Eintrag
    berechnet, legt die Textur im Paket auf eine beliebige Adresse,
    sobald die Nutzlast kein Vielfaches von 64 ist. Gemessen an den
    LOD-Paketen: vor der Korrektur traf es dreimal von vier Dateien nicht
    zu -- und zwar unbemerkt, weil der Prüfer nur den ersten Eintrag
    ansah. Jetzt wird die Polsterung aus der laufenden Position
    berechnet: 64 und 6.836.608 Byte, beides glatt durch 64.
17. USDA: `%g` sind 6 signifikante Stellen. Bei ±108 mm sind das 0,5 µm
    Rauschen – für einen Round-Trip-Test zu grob. `%.17g` schreiben.

**STL**
18. Binäres STL: 80-Byte-Header (mit 0x00 auffüllen, nicht mit Leerzeichen) +
    `uint32` Dreieckszahl + 50 Byte je Dreieck (Normalen-`float3`, drei
    `float3`-Ecken, `uint16` Attribute). Keine Farben, keine Einheiten.
19. STL speichert Punkte **pro Dreieck**, nicht geteilt: ein Leser bekommt
    `3 × Dreiecke` Punkte, nicht `n_v`. Das ist kein Fehler des Schreibers.

**Collada (DAE 1.4.1)**
20. Einheiten und Hochachse stehen im `<asset>`-Block und an **keiner**
    anderen Stelle: `<unit meter="0.001"/>` (wir rechnen in mm) und
    `<up_axis>Y_UP</up_axis>`. Fehlt beides, kommt das Modell 1000-fach zu
    groß und auf der Seite liegend an — der Leser darf 1.0 und `Z_UP`
    annehmen, und Blender tut das.
21. Die Indizes in `<p>` sind **pro Ecke**, nicht pro Dreieck — und welche
    Spalte was bedeutet, steht nicht in `<p>`, sondern in der
    REIHENFOLGE der `<input>`-Zeilen: VERTEX, NORMAL, TEXCOORD auf
    offset 0, 1, 2 heißt neun Zahlen je Dreieck (`v n t` je Ecke). Wer
    `<input>` umsortiert und `<p>` lässt, verdreht Normalen und UVs
    stillschweigend, ohne dass die Datei ungültig wird.
22. Jede `<source>` braucht `<float_array>` **und** einen `<accessor>` mit
    `count` und `stride`. Ohne Accessor ist die Datei schema-gültig, aber
    für die meisten Leser ohne Inhalt.
23. Material und Textur hängen an einem **Symbol**, nicht direkt am
    Material: `<triangles material="face_symbol">` nennt das Symbol,
    `<instance_material symbol="face_symbol" target="#face_material">` löst
    es auf, `<bind_vertex_input semantic="UVSET0" input_semantic="TEXCOORD"
    input_set="0"/>` verbindet es mit der UV-Quelle. Und die
    Material-Bibliothek muss **immer** geschrieben werden, auch ohne
    Textur: steht `<instance_material target="#face_material">` in der
    Datei und `library_materials` nicht, ist das ein Verweis ins Leere.
    assimp schluckt ihn wortlos, pycollada bricht ab
    (*„Material #face_material not found“*) — genau so war der erste
    Entwurf. Ohne Textur tritt eine konstante Farbe an die Stelle der
    Texturkette, und `bind_vertex_input` entfällt.
24. `<p>`-Spalten zwingen jeden Leser zum Aufsplitten: Collada indiziert
    pro Ecke, also teilt der Leser jeden Punkt, dessen Normalen oder UVs
    nicht überall gleich sind. LOD3 mit geteilten Attributen bleibt bei
    3.849 Punkten; mit pro Ecke verschiedenen UVs werden daraus 6.970,
    obwohl die Datei denselben Kopf beschreibt. (assimp meldet 6.970
    Vertices / 5.999 Faces, pycollada 3.849.) Das M1-Netz teilt alle
    Attribute, deshalb bleiben seine 130.829 Punkte beisammen.
25. Collada ist XML und braucht rund 100 Byte je Dreieck: das M1-Netz
    (257.044 Dreiecke) wird 30,5 MB groß, während FBX 12,2 MB und GLB
    6,5 MB daraus macht. Deshalb schreibt die LOD-Kette DAE nur für die
    gröbste Stufe (LOD3, 0,85 MB) — LOD0 käme auf ~30 MB und wäre damit
    teurer als alles andere zusammen.

**BVH / CSV / JSON (Motion)**
26. **BVH kennt keine Kommentare.** Kein `#`, kein `//` – nur
    Schlüsselwörter. Die erste Fassung schrieb eine Kopfzeile mit der
    Einheit hinein; assimp lehnte die Datei ab: *„Expected root node
    \"ROOT\"“* – die Zeile steht direkt nach `HIERARCHY`, wo assimp das
    Wurzelgelenk erwartet.
27. **BVH trägt keine Einheit.** Kein Feld, kein Kopf, nichts – der
    Importierende entscheidet, ob eine Zahl Meter oder Zentimeter ist.
    Wir schreiben Meter und Grad (§6: m, Y-up) und dokumentieren es hier
    sowie im begleitenden JSON, das sehr wohl ein Feld dafür hat.
28. **Die Euler-Reihenfolge steht in den `CHANNELS`-Zeilen**, nicht
    global: `Zrotation Xrotation Yrotation` heißt, die drei Zahlen sind
    in genau dieser Reihenfolge zu lesen.
29. **`Frames` und die Zahl der Datenzeilen müssen übereinstimmen.** BVH
    hat keine Längenangabe pro Block; der Leser hört nach `Frames` Zeilen
    auf. Eine Zahl zu wenig, und alle folgenden Kanäle sind um eine
    Stelle verschoben – ohne jede Fehlermeldung.
30. **Euler-Winkel müssen entwrappt werden.** Die Zerlegung liefert
    ±180°, und zwischen zwei Frames kann dabei ein Sprung von −175° auf
    +175° stehen: 10° Unterschied, abgespielt aber als 350°
    Rückwärtsdrall, weil BVH zwischen zwei Frames linear interpoliert und
    nichts von Winkeln weiß. Bei der Aufnahmebahn: größter Sprung 350,0°
    → nach dem Entwrapen 10,0°.

**Hohlkörper (3D-Druck)**
31. **Eine Schale läßt sich NICHT als Niveaufläche des Poisson-Feldes
    schreiben.** Das Feld ist bis auf eine Übergangsbreite von knapp
    1,5 mm gesättigt — `|grad u|` fällt dort praktisch auf null. Der
    Abstand `|u| / |grad u|` stimmt bei 0,5 mm Tiefe noch (0,59 statt
    0,50 mm), liefert bei 1,0 mm schon 1,46 mm und bei 2,0 mm rund
    14 mm. Der Abstand muß deshalb über das Gitter kommen.
32. **Der Abstand zum nächsten Randknoten ist um eine halbe Gitterkante
    zu klein**, weil der Randknoten eine halbe Zelle VOR der Isofläche
    sitzt. Nachgemessen: bei 1,0 mm Tiefe 0,54 mm, mit der halben Kante
    1,00 mm; bei 2,0 mm 1,50 → 1,96 mm. Es bleibt eine Streuung von gut
    ±0,3 mm — die Wandstärke wird kalibriert, nicht gesetzt.
33. **Der massive Sockel verschleppt jeden Median.** 42 % der
    Oberflächenproben liegen auf dem Sockel, und dort mißt der Strahl
    35 mm statt 2 mm. Die Wand wird deshalb nur am Kopf gemessen.
34. **Die Nadelschwelle ist keine Konstante.** Vier Gitterkanten sind für
    einen massiven Körper richtig; bei einem Hohlkörper ist die Wand
    selbst dünn, und dieselbe Schwelle verwirft die Hälfte aller
    Messungen als Artefakt.
35. **Das Minimum wandert mit dem Schritt des Strahls** (0,91 mm bei
    halber, 0,64 mm bei viertel Gitterkante) — es handelt von einer
    Haarspitze, nicht von der Wand. Verläßlich ist der **Anteil** der
    Proben unter der Grenze, nicht die kleinste Einzelmessung.
36. **Ohne Ablaufloch wirft das Aufräumen den Hohlraum weg.** Der
    Marcher erzeugt dann zwei Schalen, `largest_component` behält die
    äußere, und heraus kommt ein massiver Kopf, an dem niemand den
    Fehler sieht. Und: **Euler = 2 heißt hier nicht „massive Kugel"** —
    eine Schale mit einem Loch hat ebenfalls χ = 2 (Außenkugel und
    Innenkugel je ohne eine Kreisscheibe, plus der Zylinder dazwischen:
    1 + 1 + 0). Die Verbindung nach außen prüft man deshalb mit einem
    Strahl, nicht mit der Euler-Charakteristik.

**Vereinfachen für den Druck**
37. **Der Zusammenfasser darf eine Kante nur entfernen, wenn er ALLE
    Dreiecke um ihre beiden Punkte kennt.** In `_MeshState._unlink`
    stand das `discard` außerhalb der Abfrage, ob die Kante wirklich
    keinem Dreieck mehr gehört — ein Punkt verlor damit jede Kante, die
    noch ein anderes Dreieck benutzte. Die Liste der Dreiecke um einen
    Punkt wurde Zug um Zug kürzer, und beim Zusammenfassen blieben
    Dreiecke übrig, die niemand mehr kannte. Die hingen danach nur noch
    an einer Kante am Rest: **8.660 Randkanten, 1.805 nicht-
    manigfaltige Kanten und 255 Einzelteile aus einem Stück** nach einer
    harmlosen Vereinfachung von 775 k auf 300 k Dreiecke.
38. **Es braucht die Nachbarschaftsbedingung**: `lk(u) ∩ lk(w) = lk(uw)`.
    Ohne sie entsteht beim Zusammenfassen eine Kante mit VIER Nachbarn —
    zwei Flächenblätter, die sich nur in dieser Kante berühren. Danach
    ist das Netz nicht mehr wasserdicht, obwohl es genauso aussieht wie
    vorher (26 solcher Kanten blieben nach der ersten Korrektur).
39. **Geprüft werden muß um BEIDE Punkte herum, nicht nur um den
    sterbenden.** Die Dreiecke am ÜBERLEBENDEN Punkt wandern mit, wenn
    er auf die neue Lage rückt, und ändern sich genauso. Wer nur um `u`
    herum prüft, läßt jedes Dreieck wachsen, das zufällig immer am
    überlebenden Punkt hängt — Zug um Zug, unbegrenzt. Und der Umbau
    darf trotzdem nur die Dreiecke am sterbenden Punkt anfassen: beides
    in einen Topf zu werfen, tötet mitwandernde Dreiecke zweimal und
    reißt Löcher (Euler −4407 nach dem ersten Schritt).
40. **Eine EBENE Fläche vereinfacht sich kostenlos — und pflastert damit
    jedes Loch zu, das in ihr liegt.** Jedes Dreieck in einer Ebene
    liegt genau auf ihr, die Quadrik merkt nichts. Der Boden des
    Hohlraums ist so eine Ebene, mit dem Ablaufloch in der Mitte: drei
    Punkte im Abstand von 120° ergeben ein Riesendreieck über dem Loch,
    und der Hohlraum ist danach ein geschlossenes Gefäß. Punkte am Loch
    festzuhalten hilft nicht — die drei Ecken des zudeckenden Dreiecks
    dürfen weit weg liegen. Ein **Sperrgebiet** hilft: keine Kante darf
    in diese Kiste hineinragen. Gemessen: Loch 4,6 mm statt 2,1 mm.
41. **Das Netz im Speicher ist dicht, die DATEI nicht.** STL speichert
    Positionen als 32-Bit-Zahl, und das Optimum der Quadrik fällt sehr
    oft fast genau auf einen schon vorhandenen Punkt: zwei Punkte, im
    Speicher um 1e-14 mm verschieden, sind in der Datei IDENTISCH. 14
    solcher Paare genügten, und aus einem Netz mit 0 Randkanten und
    Euler 2 kam aus der Datei ein Netz mit Euler 17 und
    `is_watertight = False` zurück. Zusammenfassen NACH dem Runden heilt
    das nicht (es blieben Kanten mit vier Nachbarn), also wird die
    Kollision vermieden — und zwar NUR dann: jede neue Lage auf 32 Bit
    zu runden, sieht harmlos aus (8e-6 mm) und kostet doch 40 %
    Formfehler, weil es den ganzen weiteren Ablauf ändert.
42. **Der Formfehler an den Vertices gemessen ist eine Tautologie.** Die
    Vertices eines vereinfachten Netzes sind lauter Punkte des
    Originals — ihr Abstand zum Original ist null, egal wie grob das
    Netz inzwischen ist (p95 0,0015 mm bei 300 k statt 775 k).
    Flächengewichtet auf der Oberfläche gemessen sind es 0,082 mm.
43. **Das Maximum ist keine Grenze.** Es sitzt an einer Haarspitze oder
    an der scharfen Kante unten am Sockel und wandert mit der Stichprobe
    (1,55 mm hier, 2,94 mm da). Gezählt wird, welcher ANTEIL der Fläche
    über einer Grenze liegt.
44. **Die Kette ist pessimistischer als der frische Lauf.** Dieselbe
    Dreieckszahl, frisch aus dem Original gerechnet statt Stufe für
    Stufe: p95 0,087 statt 0,098 mm. Gesucht wird deshalb in zwei
    Gängen — die Kette findet den Bereich, der frische Lauf die Stufe.
45. **Die Trägheitsachse taugt nicht als „oben" bei einem Kopf.** Ein Kopf
    ist fast so breit wie hoch (hier 220 mm zu 213 mm); die drei
    Hauptachsen liegen deshalb dicht beieinander und tauschen bei kleinen
    Formänderungen schon die Plätze. Gemessen: 78 Grad Abweichung zur
    echten Hochachse. Verlässlich sind die Schnittfläche unten und — als
    Gegenprobe — der Modell-Fit mit geneigter Achse.
46. **Die Maske darf sich während der Optimierung nicht bewegen.** Wird die
    Gesichtsmaske bei jedem Probeschritt neu aus dem gerade geprüften Rahmen
    bestimmt, jagt die Optimierung ein Ziel, das sich unter ihr verändert.
    Auf unserem Netz blieb sie 4 Grad und 2,4 mm neben der Wahrheit stehen.
    Richtig ist das ICP-Prinzip: Korrespondenzen festlegen, lösen, neu
    zuordnen.
47. **Gittersuche statt Bergwanderung.** Dieselbe Zielfunktion, aber vom
    Schwerpunkt aus nur bergab gelaufen, bleibt in einem Nebenminimum
    (Restfehler 0,44 mm). Von grob nach fein verengt findet sie das globale
    Minimum exakt: Blickrichtung auf 0,0 Grad, Kopfmitte auf 0,4 mm,
    Maßstab auf 0,13 %.
48. **Über alle 360 Grad gesucht gewinnt der Hinterkopf, nicht das Gesicht.**
    Er ist schön glatt und passt deshalb besser zum glatten Modell als Nase,
    Kinn und Augenpartie. Das Vorzeichen „vorn gegen hinten" muss deshalb
    der maskenfreie Fit entscheiden, der den ganzen Kopf im Blick hat.
49. **Collada-Matrizen stehen zeilenweise, glTF-Morphs sind Verschiebungen.**
    Zwei Einzelfehler mit derselben Folge: Bei Collada dreht spaltenweise
    geschriebene Matrix das Vorzeichen jeder Bewegung um; im glTF fliegt das
    Modell beim Lächeln um den Faktor 1000 auseinander, wenn die Ziele in
    Millimetern stehen und die Positionen in Metern.
50. **Eine Gesichtsmaske, die Haar enthält, passt das Haar an.** Erst als
    Stirn und Schläfen aus der Maske fielen, sprang der Restfehler von
    0,90 mm auf 0,44 mm.
51. **Links und rechts sind eine Benennungsfalle.** VRM zaehlt von der Seite
    des Avatars (+X ist links, so steht es in `lookAt.md`), waehrend
    `headmesh` seine Messpunkte von der Seite des Betrachters benennt. Wer
    die Namen einfach uebernimmt, vertauscht die Augengelenke. Richtig ist
    die Zuordnung nach Vorzeichen der Koordinate.
52. **`humanoid.humanBones` zeigt auf KNOTEN, nicht auf Gelenke.** Der Index
    zaehlt im glTF-Knoten-Array. Um eins verschoben laedt die Datei
    anstandslos, aber jeder Knochen sitzt auf dem falschen Gelenk. Die
    Gegenprobe ist billig: heisst der Knoten so wie der Knochen?
53. **Die Sohle steht auf Y=0, nicht das Fussgelenk.** `tpose.md` verlangt
    Bodenfreiheit in der Erscheinung, die Spec legt `foot` aber an den
    Knoechel. Wer den Knoechel auf 0 setzt, versenkt die Fuesse bis zu den
    Knien im Boden.
54. **glTF-Matrizen stehen spaltenweise, Gelenkknoten rechnen relativ.**
    Zwei getrennte Fallstricke beim selben Export: die Matrix braucht die
    umgekehrte WELTPosition des Gelenks, die Knotenverschiebung dagegen den
    Weg vom Elterngelenk. Beides zu verwechseln ergibt ein Skelett, das im
    Viewer als Knaeuel ankommt.

### 12.2 Offen
* **Die restlichen 46 ARKit-Formen.** Wir liefern sechs (`jawOpen`,
  `mouthSmile`, `eyeBlink`, `browInnerUp`, `browDown`, `mouthPucker`), weil
  das 3DMM sechs Ausdrucksrichtungen besitzt. Die anderen aus diesen sechs
  abzuleiten (etwa `mouthSmileLeft` durch Halbieren von `mouthSmile`) wäre
  erfunden: echte Gesichter lächeln nicht spiegelsymmetrisch. 52 Formen
  brauchen ein 3DMM mit 52 Ausdrucksbasen — eine Frage des Modells, nicht
  des Exports. Die Struktur nimmt sie auf, sobald sie da sind.

### 12.3 In M3 erledigt (Stand: siehe prototype/README.md, Kap. 7i)
* **Rig und Animation** — `facescan_ref/rig.py`. Rahmen (oben, Blickrichtung,
  Kopfmitte, Maßstab) aus dem Netz selbst bestimmt und gegen die bekannte
  Wahrheit geprüft: Blickrichtung exakt, Kopfmitte 0,4 mm, Maßstab 0,13 %,
  Landmarken 0,16 … 1,13 mm. Acht Gelenke nach VRM benannt, Hautgewichte
  über die Netzkanten geglättet (Summe je Punkt genau 1, größter Sprung
  zwischen Nachbarpunkten 0,05). Export in drei Formate, alle von fremden
  Lesern geprüft: DAE mit `library_controllers` (assimp: 5 Knochen), BVH mit
  echtem Skelett statt der Aufnahmebahn (assimp: 1 Animation, 8 Kanäle), GLB
  mit sechs Morph-Zielen in ARKit-Benennung.
* **VRM 1.0** — `python/build_vrm.py` → `meshes/facescan.vrm`. 23 Gelenke,
  alle 15 Pflichtknochen, T-Pose mit der Sohle auf Y=0, sechs Preset-
  Ausdrücke, `lookAt` über die Augengelenke. Die gemessenen Kopf-Gelenke
  (Hals bis Augen) werden unverändert übernommen, Rumpf und Gliedmaßen sind
  aus der gemessenen Kopfhöhe abgeleitet — kein festes Maß. Arme und Beine
  tragen keine Hautgewichte; die Datei ist gültig VRM und bewegt doch nur
  den Kopf. Geprüft gegen die Spec-Texte (Knoten- statt Knochenindizes,
  Pflichtknochen, T-Pose, Morph-Bindungen).
* **`.fsmc`-Motion-Clip** — `python/build_clip.py` → `meshes/facescan_clip.fsmc`.
  Aufnahmeformat nach F-405: 17 Kanäle, 48 Zahlen je Frame, 120 Frames @
  30 fps, Gelenke als Quaternionen, Blickrichtung aus der Augendrehung
  gerechnet. Der Rundweg liegt bei 4,9e-04 — genau einer halben
  Quantisierungsstufe, wie die Rundung es verlangt. Der Prüfer rechnet das
  aus den Metadaten nach, statt dem Schreiber zu glauben. Drei Randfälle
  sind abgedeckt und gemessen: voller Wertebereichssprung in jedem Frame
  (erzwingt 60 von 60 Schlüsselframes), konstanter Kanal (Spanne null) und
  ein einzelner Frame.


### 12.3b In M2b erledigt (Stand: siehe prototype/README.md, Kap. 7b)
* **Quadric Decimation** — LOD-Kette 300 k / 80 k / 20 k / 6 k
  (Garland-Heckbert, mitgeführte UVs), Formfehler 0,035 … 0,396 mm gegen das
  Master-Netz. Zusätzlich: Normalen und UVs werden beim Vereinfachen
  mitgetragen, Materialgrenzen über eine Farbstrafe geschützt.
* **UV-Atlas** — `facescan_ref/atlas.py` mit xatlas (bevorzugt) und
  Zylinderprojektion (Rückfall, auf dem Messrechner der schnellere Weg;
  Begründung in README 7b). Damit tragen GLB, OBJ und USDZ echte UVs und eine
  gemeinsame 2048²-Textur statt Vertexfarben.
* **Textur-Bake** — `facescan_ref/bake.py`: pro Texel cos²-gewichtet aus allen
  sichtbaren Kameras gemischt, Verdeckungstest asymmetrisch (ein Punkt darf
  hinter der Messung liegen, aber nicht davor — sonst fällt das
  Visual-Hull-Haarvolumen durch die Prüfung).
* **Normalen in allen Formaten** außer STL (da stehen sie pro Dreieck im
  50-Byte-Satz und jeder Slicer rechnet sie neu).
* **Wasserdichte Variante** — `facescan_ref/repair.py` und
  `tools/build_watertight.py`: Loch-Füllung (Advancing Front, kleinster
  Innenwinkel zuerst, Grenze 3 mm), Taubin-Glättung (λ=0,5 / µ=−0,53, Ränder
  fest) und Poisson Surface Reconstruction auf einem regelmäßigen
  192³-Gitter statt Octree-Tiefe 10–12 (im Frequenzraum gelöst, 5,5 s).
  Ergebnis: 227.867 Punkte / 455.730 Dreiecke, 0 Randkanten, 0
  nicht-manigfaltige Kanten, 1 Komponente, Euler-Charakteristik 2, Volumen
  735,9 cm³. Gegenprobe mit trimesh: `is_watertight = True`,
  `euler_number = 2`. Zwei Fehler, die vorher im Weg standen und die in
  keinem Paper erwähnt werden: das Iso-Level darf nicht exakt auf einen
  Gitterknoten fallen (sonst erzeugen mehrere Tetraeder dasselbe Dreieck und
  die Umlaufrichtung kippt — 528 Kanten mit gleichsinnigen Nachbarn), und
  Poisson erzeugt zu jeder Rauschmessung in der Luft eine eigene kleine
  geschlossene Blase (10 Stück, neun davon Rauschen; nur die größte bleibt).
  Einzelheiten und Messwerte in README, Kap. 7d.
* **Sockel und Druckprüfung** — `facescan_ref/printcheck.py` und
  `tools/build_print.py`. Der Sockel wird **am Indikatorfeld** angesetzt
  (Kegelstumpf unterhalb der Schnitthöhe), nicht am Netz geschnitten:
  danach läuft derselbe Marcher noch einmal und Kopf und Sockel sind ein
  Körper. Schnitthöhe nach Regel, nicht nach Gefühl: die tiefste Stelle, an
  der der Querschnitt 25 % seines Maximums erreicht (z = 0,8 mm, 33,4 cm²).
  Ergebnis `meshes/facescan_print.stl`: 387.431 Punkte / 774.858 Dreiecke,
  1171,2 cm³, 134,5 mm hoch, von trimesh mit `is_watertight = True` und
  `euler_number = 2` gelesen. Gemessene Prüfungen: Standfläche 152,1 cm²
  (Kopf allein: 0,00 cm², steht nicht), Ebenheit der Standfläche 0,00 mm,
  Schwerpunkt 18,6 mm neben der Mitte bei 51,2 mm Abstand zum Rand,
  kleinste lokale Dicke 1,82 mm, Überhänge steiler als 45° auf 27,9 % der
  Fläche. Gegen die Kugel (r = 30 mm) nachgerechnet: 59,97 mm gemessene
  Dicke bei 60,00 mm Soll. Einzelheiten in README, Kap. 7e.
* **Hohlkörper für den 3D-Druck** — `tools/build_hollow.py`
  (Schreiber `printcheck.shell_field` und `drill_hole`). Die Büste wird
  zur Schale: 2,4 mm Wand über der Schnitthöhe, **massiver Sockel**
  (damit der Schwerpunkt unten bleibt, wo ihn die Kippsicherheit
  braucht) und ein Ablaufloch von 10 mm durch die Standfläche — ohne das
  wäre der Hohlraum ein Gefäß, aus dem kein Harz und kein Pulver wieder
  herauskommt. Gefaltet wird das **Feld**, nicht das Netz: ein Netz um
  2 mm nach innen zu schieben, überlappt sich an Haaren und Ohren
  selbst, eine Isofläche kann sich nie selbst schneiden. Ergebnis
  `meshes/facescan_print_hollow.stl`: 593.193 Punkte / 1.186.382
  Dreiecke, **wasserdicht** (eigener Prüfer und trimesh: 0 Randkanten,
  1 Komponente, Euler 2), Volumen 1171,2 → **541,8 cm³ (54 % gespart)**.
  Wandstärke nachgemessen mit dem Ray-Cast: median 2,34 mm, p05 1,82 mm,
  p01 1,58 mm; 0,04 % der Kopfoberfläche liegen unter der 1,2-mm-Grenze
  aus §4.3. Daß der Hohlraum wirklich mit der Außenwelt verbunden ist,
  prüft ein Strahl vom Boden durch das Loch bis in den Hohlraum — alle
  200 Proben außen. Einzelheiten in README, Kap. 7g.
* **Drucknetz vereinfacht** — `tools/build_print_lod.py`. Gesucht wird
  die gröbste Fassung, die eine **Formfehlergrenze** einhält, nicht eine,
  die eine bestimmte Dreieckszahl hat: p95 ≤ 0,10 mm (ein Viertel der
  kleinsten Düse), p99 ≤ 0,35 mm, höchstens 1 % der Fläche über 0,5 mm,
  beim Hohlkörper zusätzlich Wand p01 ≥ 1,2 mm und Ablaufloch ≥ 4 mm —
  und das Netz muß dicht bleiben, im Speicher UND in der Datei. Ergebnis
  `facescan_print_lod.stl`: 50.368 Punkte / **100.732 Dreiecke (87 %
  gespart)**, 4,9 MB, p95 0,090 mm. `facescan_print_lod_hollow.stl`:
  94.912 / **189.820 (84 % gespart)**, 9,3 MB, p95 0,094 mm, Wand p01
  1,60 mm, Loch 4,6 mm frei, Ablauf offen. Beide von trimesh aus der
  Datei mit `is_watertight = True` und `euler_number = 2` gelesen. Was
  dabei im Weg stand, sind fünf Fehler im Zusammenfasser selbst
  (§12.1, 37–44); einer davon — die mitwandernden Dreiecke am
  überlebenden Punkt — hat auch die Anzeige-LODs betroffen.
* **Aufnahmebahn als BVH, CSV und JSON** — `tools/build_motion.py`,
  Schreiber und Leser in `export_more.py`. Was M2 an Bewegung hat, ist
  nicht der Rig (der kommt mit M3), sondern die Aufnahme selbst: 16
  Kameraposen auf einem Bogen. Die Pose (R, t) mit `p_cam = R p + t` ist
  genau die Transformation, die der Kopf relativ zur Kamera erfährt –
  umgerechnet heißt das: feste Kamera, drehender Kopf, durch genau die
  16 Lagen, aus denen gemessen wurde. BVH 1,1 kB / CSV 1,2 kB / JSON
  1,6 kB, Rücklese identisch bis 5e-7 (Schreibgenauigkeit `%.6f`).
  assimp liest das BVH: 1 Animation, 2 Knoten, das Gelenk `Head` im
  Knotenbaum gefunden. Zwei Fehler unterwegs, beide von assimp bzw. von
  den Zahlen selbst gefunden: eine Kommentarzeile im BVH (assimp:
  *„Expected root node ROOT“*) und der Euler-Sprung um 350° zwischen
  Frame 8 und 9 (entwrappt, s. §12.1, Punkt 30).
* **Collada (DAE) als neuntes Exportformat** —
  `export_more.write_dae` / `read_dae`. Schreibt Collada 1.4.1 mit
  `unit meter="0.001"`, `up_axis Y_UP`, Quellen für Positionen, Normalen
  und UVs (beim M1-Netz Vertexfarben statt UVs), jeder Quelle mit
  `<float_array>` **und** `<accessor>`, und der Materialkette
  `image → sampler2D → surface → lambert`. Zwei Leser bestätigen es:
  assimp (M1: 130.829 Vertices / 257.044 Faces; LOD3: 6.970 / 5.999) und
  pycollada — pycollada ist der strengere von beiden, es löst die
  Materialkette wirklich auf und hat den Verweis ins Leere des ersten
  Entwurfs gefunden (s. §12.1, Punkt 23). Rücklese mit dem eigenen Leser:
  Punkte identisch bis 0,0 mm, Indizes identisch, Farben identisch
  (0,0e+00/255). Dateigrößen: M1 30,5 MB (257.044 Dreiecke, XML eben —
  deshalb schreibt die LOD-Kette DAE nur für LOD3, 0,85 MB).
  Gegenprobe insgesamt: **24 von 24 Dateien** bestanden, 22 davon von
  einem fremden Leser gelesen (`validate_exports.py`).
* **USDZ mit binärem Crate** — `export_more.write_usdz(..., crate=True)`
  schreibt als Root-Layer ein `.usdc` statt Text, damit Apple-Geräte das
  Paket annehmen (Reality Converter: „the package's root layer must be a
  usdc file"). Der Inhalt kommt weiter aus dem eigenen USDA-Schreiber,
  serialisiert wird von der USD-Bibliothek. Alle vier LOD-Pakete sind
  umgestellt, nachgemessen: `facescan.usdc` mit Kennung `PXR-USDC`,
  Datenanfänge bei 64 und 6.836.608 Byte (beide glatt durch 64), alle
  Einträge `ZIP_STORED`, CRC ok. Dateigröße LOD0 24,9 MB → 7,0 MB,
  LOD3 0,84 MB → 0,43 MB. Gegenprobe mit pxr: 19 von 19 Formate, die vier
  USDZ mit `primvars:st`, PNG im ZIP und der vollständigen Shader-Kette.
