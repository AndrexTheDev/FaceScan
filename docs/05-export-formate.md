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

### 4.4 Collada (DAE 1.4.1)
- `library_geometries` (positions/normals/uv/indices), `library_controllers` mit `<skin>` (Joints,
  `bind_shape_matrix`, `vertex_weights`) und `<morph>` (mit `method="NORMALIZED"`), `library_visual_scenes`,
  `library_animations` (Sampler/Channel).
- Relevanz: Austausch mit Programmen, die glTF schlechter können (ältere C4D-Versionen, diverse
  Forschungswerkzeuge) und als menschenlesbares Format für Debugging und Support.

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
- **USDC (binär)** ist für v2 vorgesehen (eigenes Schreiben des binären Formats ist aufwendig; Alternative:
  USD-SDK in einem Desktop-Begleitprogramm).

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

### 4.9 VRM (optional, Studio)
- VRM 0.x/1.0 ist eine glTF-2.0-Erweiterung (`VRMC_vrm`, `VRMC_node_constraint`,
  `VRMC_springBone`, `VRMC_materials_mtoon`). Wir schreiben sie selbst (kein SDK nötig; die Spezifikation
  ist offen dokumentiert). Direkte Kompatibilität mit VRChat, VMagicMirror, Luppet, 3tene, Cluster, V-Katsu.
- Reihenfolge: **nach** glTF implementieren (VRM baut darauf auf).

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
| 2 | USDA + USDZ, DAE | Text-/XML-basiert, kein Fremdcode, deckt Apple/Houdini/Alt-DCC |
| 3 | FBX (binär) | Größter Aufwand, größter Nutzen (Blender/Maya/Max/Unreal/Unity) |
| 4 | ABC (libalembic) | Für Houdini/Point-Cache/Haar-Kurven |
| 5 | BVH, CSV/JSON, VRM | Motion-/VTuber-Spezialfälle |

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
