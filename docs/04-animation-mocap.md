# 04 – Animation & Motion-Capture (ohne ARCore)

Stand: 2026-11-15 · Basiert auf `03` (Rig/Blendshapes) und `05` (Export der Animation)

---

## 1. Grundprinzip

Es gibt zwei getrennte Tracker, die wir je nach Modus einzeln oder gemeinsam betreiben:

| Tracker | Liefert | Benötigt | Frequenz |
|---|---|---|---|
| **Face Landmarker** (`LIVE_STREAM`) | 478 Landmarks, **52 Blendshape-Scores**, 4×4-Kopfpose | Frontkamera, Gesicht im Bild | 30 fps (Ziel) |
| **Pose Landmarker** (`LIVE_STREAM`) | 33 Landmarks (Bild + **Weltkoordinaten in Metern**, Ursprung Hüftmitte), optional Segmentierungsmaske | Ganzkörper im Bild | 30 fps |
| **Hand Landmarker** (2×) | 21 Landmarks je Hand (Bild + Welt) | Hände im Bild | 30 fps |

Alle drei laufen **vollständig on-device** (MediaPipe Tasks, Apache-2.0) [1](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker) [6](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker).
Es wird **kein ARCore, kein Tiefensensor, kein SLAM** benötigt: die Tiefeninformation kommt aus dem
Modell (metrische Weltkoordinaten des Pose-Trackers; metrische Kopfpose des Face-Trackers).

> **Hinweis:** Es gibt auch den kombinierten *Holistic Landmarker* (Gesicht + Pose + Hände in einem Task).
> Er ist bequemer, aber schwerer. Wir nutzen **getrennte Tasks mit gemeinsamem Frame-Takt**, weil wir so
> (a) Gesicht-only-Modus mit halber Last fahren können und (b) je Tracker unterschiedliche Delegates
> (GPU/NNAPI) zuweisen können. Holistic bleibt Fallback für Geräte mit schwacher CPU.

## 2. Gesichts-Animation

### 2.1 Pipeline pro Frame

```
Kameraframe (YUV, 720p für Tracking)
  → FaceLandmarker.detectAsync (GPU/NNAPI)           ~6–12 ms
  → Rohdaten: 52 Blendshape-Scores, 4×4-Matrix
  → Neutral-Abzug & Bereichs-Normierung              (kalibriert)
  → One-Euro-Filter je Kanal                          ~0,2 ms
  → Symmetrie-/Plausibilitäts-Checks                  ~0,1 ms
  → Anwenden auf das Mesh:
        v = v_neutral + Σ_k w_k · Δ_k   (+ Kieferrotation, Augenrotation, Zunge)
  → Kopfpose: q, t aus der 4×4-Matrix → auf den head-Bone
  → Render (Vulkan)                                   ~8 ms
```

### 2.2 Blendshape-Mapping

Die 52 Kanäle des Modells tragen bereits die **ARKit-Namen** (`browDownLeft`, `browInnerUp`, `eyeBlinkRight`,
`jawOpen`, `mouthSmileLeft`, `mouthPucker`, `cheekPuff`, `noseSneer`, `tongueOut`, …). Unser Basiskopf nutzt
dieselben Namen ⇒ **1:1-Mapping, keine Umsetztabelle**. Drei Regeln sind aber zwingend:

1. **Seitenkonvention:** Die Modell-Doku weist ausdrücklich darauf hin, dass `*Left`/`*Right` sich auf die
   abgebildete Person beziehen und sich bei horizontal gespiegeltem Eingabebild vertauschen. Wir speisen
   **immer das ungespiegelte Kamerabild** ein und spiegeln nur die Vorschau. (Unit-Test: Künstliches
   Spiegelbild muss dieselben Scores mit vertauschten Seiten liefern.)
2. **Bereichs-Normierung:** Rohe Scores erreichen bei den meisten Menschen nie 1,0. Nach der
   Bereichskalibrierung (siehe 2.3) wird je Kanal `w = clamp((s − s_neutral) / (s_max − s_neutral), 0, 1)`.
3. **Korrektur-Shapes:** Zusätzlich zu den 52 Formen rechnen wir eigene Korrekturen ein:
   - **Lid-Follow:** Augenlid-Verschiebung als Funktion der Augapfelrotation (`eyeLook*`) – verhindert das
     "Augen schauen durch die Lider"-Artefakt.
   - **Jaw-Lip-Correction:** Lippen folgen der Kieferrotation mit weichem Gewicht.
   - **Mikro-Expressions:** Optionales, schwaches Rauschen (Amplitude ≤ 1 % der Kopfgröße, 0,3–1 Hz), damit
     der Avatar nie "eingefroren" wirkt (Abschaltbar, wichtig für professionelle Anwendungen).

### 2.3 Kalibrierung (einmal pro Avatar, 40 Sekunden)

| Schritt | Dauer | Was passiert |
|---|---|---|
| 1. Neutral | 3 s | 90 Frames mitteln ⇒ `s_neutral` je Kanal, Neutral-Pose der Kopfmatrix |
| 2. Maximal-Ausdrücke | je 2 s | "Bitte maximal lächeln" · "Augen fest schließen" · "Brauen hoch" · "Brauen zusammenziehen" · "Mund weit auf" · "Kussmund" · "Wangen aufblasen" ⇒ `s_max` je Kanal |
| 3. Skalierung | – | Kopfgröße aus der 4×4-Matrix ⇒ Umrechnung Modell-Einheiten ↔ Basiskopf, damit die Kopfpose 1:1 passt |
| 4. Plausibilität | – | Prüfung: ist `s_max − s_neutral ≥ 0,15`? Sonst Kanal als "schwach messbar" markieren (dann greift der Transfer-Delta stärker) |

Ergebnis wird im `.fscan`-Projekt gespeichert und ist jederzeit wiederholbar ("Kalibrierung wiederholen").

### 2.4 Glättung & Latenz

- **One-Euro-Filter** je Kanal: `minCutoff = 1,2 Hz` (langsame Kanäle wie `browInnerUp`), `beta = 0,3`;
  bei schnellen Kanälen (`eyeBlink*`) `minCutoff = 4 Hz`, `beta = 0,8`, damit ein Zwinkern nicht
  "verschmiert" wird.
- **Latenz-Budget (Ziel Mittelklasse):** Kamera 33 ms + Inferenz 12 ms + Filter/Anwenden 4 ms + Render 8 ms
  + Display 16 ms ≈ **73 ms** (spürbar, aber akzeptabel). Verbesserung durch (a) Parallel-Inferenz auf NNAPI,
  (b) Render mit 60 fps, (c) optionale Prädiktion: lineare Extrapolation der Kopfpose um 1 Frame
  (nur bei ruhiger Bewegung, sonst Artefakte).
- **Frequenz:** Tracking mit 30 fps, Rendering mit 60 fps, Blendshape-/Gelenk-Interpolation dazwischen
  (Catmull-Rom für Gelenke, linear für Morph-Gewichte).

## 3. Körper-Mocap

### 3.1 Rig (eigenes Skelett, 37 Gelenke + 30 Finger-Gelenke)

```
root
 └ hips
    ├ spine_01 → spine_02 → chest → neck → head
    │                          ├ clavicle_L → shoulder_L → elbow_L → wrist_L → 5× (metacarpal, 3 phalanges)
    │                          └ clavicle_R → shoulder_R → elbow_R → wrist_R → 5× …
    ├ thigh_L → knee_L → ankle_L → toe_L
    └ thigh_R → knee_R → ankle_R → toe_R
```
Begründung der Namensgebung: **Unreal-/Mixamo-Konvention** – größtmögliche Kompatibilität mit Retargeting in
Unreal, Unity, Blender (Rigify/Mixamo-Add-ons), iClone und Cascadeur.

### 3.2 Retargeting (33 Landmarks → 37 Gelenke)

Die 33 Landmarks sind Positionen, keine Rotationen. Wir rechnen in vier Schritten:

1. **Maßstabs-Normierung:** Der Nutzer gibt einmalig seine **Körpergröße** ein (oder die App schätzt sie aus
   einem Kalibrierschritt: aufrecht stehen, ganz im Bild, dann bekannte Kamerahöhe + Brennweite). Damit werden
   die metrischen Weltkoordinaten plausibel; zusätzlich **Knochenlängen-Kalibrierung**:Der Nutzer macht einmal
   eine A-Pose (2 s), wir messen Ober-/Unterarm, Ober-/Unterschenkel, Schulterbreite und skalieren das
   Ziel-Skelett darauf. Ergebnis: Die Bewegung passt proportional zum Körper.
2. **Rotationen aus Landmark-Tripeln:** Für jedes Gelenk definieren wir ein lokales Koordinatensystem aus
   drei Landmarks (z. B. Ellenbogen:richtung aus `shoulder→elbow`, Referenz-Ebene aus `elbow→wrist` und dem
   Torso-Vektor). Daraus die Rotation relativ zur Ruhe-Pose. Für Gelenke mit nur zwei Landmarks
   (z. B. Wirbelsäule) verteilen wir die Rotation gleichmäßig auf `spine_01/02` (je 40 %) und `chest` (20 %).
3. **Stabilisierung:**
   - **Tiefen-Fix:** Die `z`-Komponente der Weltkoordinaten ist die unsicherste. Wir beschränken sie über
     die Knochenlängen (Inverse Kinematics mit FABRIK, 4 Iterationen) – das entfernt das typische
     "Tanzen" in der Tiefe.
   - **Bodenkontakt (Foot Lock):** Wenn die Fuß-Landmarks nahe der geschätzten Bodenebene sind und die
     Geschwindigkeit klein ist, wird der Fuß fixiert (Position + Rotation eingefroren, IK löst das Bein).
     Verhindert das gefürchtete "Rutschen".
   - **Confidence-Gewichtung:** Jedes Landmark hat `visibility`/`presence`. Unter 0,5 ⇒ Rotation des
     betroffenen Gelenks wird zum Vorframe interpoliert statt neu gesetzt.
   - **One-Euro-Filter** je Rotationskomponente (`minCutoff 1,5 Hz`, `beta 0,2`).
4. **Hände:** 21 Landmarks je Hand ⇒ direkte Winkel für die 3 Phalangen je Finger (Winkel zwischen
   aufeinanderfolgenden Knochen), plus Spreiz-Winkel aus der Metacarpal-Ebene. Hände sind der
   fehleranfälligste Teil; deshalb: Glättung stärker, und bei `presence < 0,4` wird die Hand auf die
   Vor-Rotation eingefroren.

### 3.3 Kombination Gesicht + Körper

- **Ganzkörper-Modus:** Pose-Tracker treibt das Skelett, Face-Tracker (wenn das Gesicht groß genug im Bild
  ist, d. h. Kopfhöhe ≥ 15 % der Bildhöhe) treibt Blendshapes + Kopfrotation (`neck`/`head` bekommen die
  Rotation aus der Gesichts-4×4-Matrix, weil die genauer ist als die aus den Schulter-Landmarks).
- **Nur-Gesicht-Modus:** Nur Face-Tracker, Rumpf in Ruhe-Pose, optional "schwebender Kopf" für VTuber.
- **Kopf-zu-Körper-Abgleich:** Der Avatar-Hals wird an die vom Pose-Tracker gelieferte Hals-Position gebunden
  (IK), damit bei Bewegung kein Spalt entsteht.

## 4. Aufnahme und Clip-Format

### 4.1 `.fsmc` (FaceScan Motion Clip)

Eigenes, offenes, dokumentiertes Containerformat (ZIP):

```
clip.fsmc/
  manifest.json         Version, FPS, Dauer, Kanäle, Gerät, Modell-Hashes, Erzeuger, Lizenz
  channels.bin          quantisierte Float-Blöcke (int16 mit Skalierung je Kanal, delta+kodiert)
  meta.json             Kanaltabelle: name → offset, typ (scalar|vec3|quat), min/max
  audio.m4a             optional (für spätere Lip-Sync-Nachbearbeitung)
  provenance.json       C2PA-Claims (signierte Herkunft, optional)
```

Kanäle: 52 Blendshape-Gewichte (scalar) · Kopf-Pose (Translation vec3 + Rotation quat) · je Gelenk
Rotation (quat) · Root-Translation (vec3) · 30 Finger-Gelenke (scalar) · optional Blickrichtung
(vec3). **Größe:** ~2,4 KB/Frame bei 30 fps ≈ 4,3 MB/Minute mit int16-Quantisierung (verlustfrei genug;
"Lossless"-Modus mit float32 optional).

### 4.2 Aufnahme-UI

- Großer roter Aufnahmeknopf (mit Gold-Ring), 3-2-1-Countdown (optional), Live-Vorschau des Avatars,
  Pegel-Anzeige für die Bewegungsintensität, "Aufnahme sichern" / "verwerfen".
- **Clip-Bibliothek:** Miniatur-Vorschau, Länge, Datum, Umbenennen, Trimmen (Anfang/Ende), Löschen.
- **Wiedergabe:** Scrubber, Loop, Langsam (0,25×), direkter Sprung in "Auf dieser Pose exportieren".

## 5. Export der Animation (Details in `05`)

| Ziel | Format | Inhalt |
|---|---|---|
| Universal (Blender, MotionBuilder, iClone) | **BVH** | Hierarchie + Euler-Kanäle; nur Skelett (Blendshapes separat als CSV/JSON) |
| Universal, verlustfrei, jede DCC | **ABC (Alembic)** | Point-Cache: Vertex-Positionen pro Frame (inkl. Morph-Ergebnis) – funktioniert überall, große Dateien |
| Unreal / Unity / Maya / Max / Blender | **FBX** | Skelett + bake-Animation auf den Kurven + Morph-Kurven |
| Web / Engine / Viewer | **glTF/GLB** | Node-Animation + animierte Morph-Gewichte (`node.weights`) |
| USD-Pipeline (Houdini, USD-Viewer, Apple) | **USDA/USDZ** | `UsdSkel` mit `UsdSkelAnimation`, Morph als `UsdSkel` "skel:blendShapes" |
| Entwickler / Forschung | **CSV, JSON** | Kanaltabelle, dokumentiert |

**Bake-Strategie:** Wir exportieren standardmäßig **gebackene** Clips (jeder Frame eine vollständige Pose),
weil Retargeting-Informationen (Knochenlängen) ohnehin im Rig stecken. Für Unity/Unreal bieten wir
"Keyframe-Reduktion (Fehler ≤ 0,5 mm)" an, um Dateigröße zu sparen.

## 6. Weitere Animations-Funktionen

| Funktion | Beschreibung | Priorität |
|---|---|---|
| **Emotions-Presets** | 7 Basis-Emotionen (Freude, Trauer, Wut, Angst, Ekel, Überraschung, Verachtung) als Regler – mischen sich additiv auf die 52 Kanäle | Should |
| **Pose-Bibliothek** | 12 Körper-Posen (Stehen, Winken, Sitzen, Zeigen, Daumen hoch, …) als Ausgangspunkt | Could |
| **Loop-Tools** | Nahtloser Loop (Anfang ≈ Ende) für Idle-Animationen | Should |
| **Audio-Lip-Sync** | Viseme aus Sprache, on-device (kleines Modell); erzeugt `jawOpen`, `mouthFunnel`, `mouthPucker`, `mouthClose` | Could (v2) |
| **Blick-Steuerung** | Manueller "Schau in die Kamera"-Regler (übersteuert `eyeLook*`) | Should |
| **Live-Stream zum Desktop** | UDP/Wi-Fi-Direct an optionale Begleit-App (kein Cloud-Zwang) – für OBS/Unity-Live-Setups | Could |
| **Bildschirm-Aufnahme mit transparentem Grund** | Für VTuber-Overlays: Avatar mit Alpha rendern, als Video (MediaCodec) mitschneiden | Could |

## 7. Qualitätsziele (Messung auf Mittelklasse)

| Metrik | Ziel |
|---|---|
| Tracking-Frequenz (Gesicht) | ≥ 28 fps |
| End-to-End-Latenz (Kamera → Avatar auf Schirm) | ≤ 90 ms |
| Blendshape-Jitter (Std.-Abw. bei ruhigem Gesicht) | ≤ 0,008 (Gewicht) |
| Zwinkern-Erkennung | ≥ 98 % der echten Lidschläge erkannt, ≤ 1 Fehlauslösung/Minute |
| Körper: Positionsfehler der Handgelenke (gegen Referenz) | ≤ 35 mm |
| Körper: Fuß-Rutschen | ≤ 5 mm/s im Stand |
| Akkuverbrauch Live-Animation | ≤ 12 %/h |

## 8. Typische Fehler und Gegenmaßnahmen (Erfahrungswerte)

| Symptom | Ursache | Lösung |
|---|---|---|
| Mimik viel zu schwach | Rohe Scores nie bei 1,0 | Bereichskalibrierung (2.3) zwingend; Fallback-Faktor 1,6 |
| Mimik spiegelt sich (linkes Auge zwinkert rechts) | Gespiegeltes Eingabebild | Nie spiegeln vor der Inferenz; Unit-Test |
| Kopf wackelt | Rauschen der 4×4-Matrix | One-Euro + Prädiktion; Ruhe-Erkennung (unter Schwelle ⇒ Pose einfrieren) |
| Kiefer "explodiert" bei `jawOpen` | Transfer-Delta zu groß | Delta-Clamp auf 12 mm; gemessene Expressionen bevorzugen |
| Körper zittert in der Tiefe | unsichere z-Koordinate | IK-Beschränkung + Knochenlängen-Kalibrierung |
| Füße rutschen | kein Bodenkontakt | Foot-Lock (3.2) |
| Animation ruckelt beim Export | zu wenige Keys | Bake mit fester Abtastrate, keine Keyframe-Reduktion als Standard |
