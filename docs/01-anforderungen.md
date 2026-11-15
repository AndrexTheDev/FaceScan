# 01 – Anforderungen (Personas, Use Cases, MoSCoW, Abgrenzung)

Stand: 2026-11-15 · Grundlage für alle weiteren Dokumente.

---

## 1. Personas

| ID | Persona | Alter | Vorkenntnisse | Gerät | Erwartung |
|---|---|---|---|---|---|
| P1 | **Mia, Einsteigerin** | 34 | "Ich weiß, was 3D ist, mehr nicht" | Galaxy A55 (Mittelklasse) | "Ich will in 3 Minuten ein 3D-Bild von mir, das ich teilen kann." |
| P2 | **Jonas, Streamer/VTuber** | 22 | OBS, ein bisschen Blender | Pixel 9 | "Mein Gesicht als Avatar, der live meine Mimik macht, raus als VRM/GLB." |
| P3 | **Sam, Indie-Dev** | 29 | Unity/Unreal | Pixel 9 Pro | "NPC-Gesichter mit ARKit-Blendshapes, GLB, fertig." |
| P4 | **Nadia, 3D-Artist** | 38 | Blender/ZBrush/Maya, 12 Jahre | Xiaomi 15 Ultra | "Scan als Ausgangsbasis, dann in ZBrush weitermachen. Ich brauche saubere Topologie und alle Maps." |
| P5 | **Tom, 3D-Druck** | 45 | Cura, kein Modeling | Galaxy S24 | "Büste als STL, druckbar, ohne Nacharbeit." |

**Konsequenz für die UX:** P1 und P5 dürfen nie ein Fachwort sehen, ohne dass eine "Was ist das?"-Blase es erklärt.
P4 braucht einen "Profi-Bereich" mit Rohdaten, LODs, Displacement-EXR, Achsen-/Einheitenwahl.

## 2. Kern-Use-Cases

| ID | Use Case | Akteur | Happy Path |
|---|---|---|---|
| UC-1 | Ersten Scan durchführen | P1 | App öffnen → "Los geht's" → Anleitung ansehen → Gesicht in den Rahmen → langsam drehen → "Fertig" → Verarbeitung (Fortschritt sichtbar) → 3D-Modell drehen |
| UC-2 | Ergebnis prüfen und verbessern | P1/P4 | Vergleichsslider Foto ↔ Render, Qualitätsampel, 3 Regler (Hautglätte, Haarvolumen, Detail) |
| UC-3 | Modell animieren (live) | P2 | "Animieren" → Kamera an → Avatar spiegelt Mimik → Aufnahme starten/stoppen → Clip speichern |
| UC-4 | Körper-Mocap | P3 | Ganzkörper-Aufnahme vor der Kamera → Avatar bewegt sich mit → Aufnahme → Export |
| UC-5 | Exportieren für Zielsoftware | P4/P3/P5 | "Exportieren" → Ziel wählen (Blender/Unreal/Unity/3D-Druck/Web/Sonstiges) → Empfehlung bestätigen → Datei wird in `Dokumente/FaceScan/` geschrieben → "Teilen"-Sheet |
| UC-6 | Freischalten / kaufen | alle | "Pro freischalten" → Coin wählen (SOL/BTC/ETH) → Betrag + QR → im Wallet zahlen → App erkennt Zahlung → Lizenz aktiv, Quittung (Tx-Hash) lokal gespeichert |
| UC-7 | Daten löschen / exportieren (DSGVO) | alle | Einstellungen → "Meine Daten" → Alle Projekte als ZIP exportieren / vollständig löschen (mit Bestätigung + Löschprotokoll) |
| UC-8 | Modell nachträglich bearbeiten | P4 | `.fscan`-Projekt öffnen → erneut exportieren mit anderen Einstellungen (ohne Nachbearbeitung der Geometrie in der App) |

## 3. Funktionale Anforderungen (MoSCoW)

### 3.1 Aufnahme (Capture)

| ID | Anforderung | Prio |
|---|---|---|
| F-101 | Geführte Aufnahme mit Echtzeit-Overlay (Kopf-Silhouette, Zielring, Fortschrittsbogen) | Must |
| F-102 | Auto-Start, wenn Kopf korrekt positioniert/ruhig ist; Auto-Pause bei Verwackeln | Must |
| F-103 | Manuelle Belichtungssteuerung: AE/AWB/AF-Lock, feste ISO + Verschlusszeit, keine Brennweitenwechsel (Zoom-Lock) | Must |
| F-104 | Belichtungsreihe (3 EV) je Pose für shading-freie Albedo-Schätzung | Must |
| F-105 | Drei Modi: **Quick** (≈ 16 Frames / 20 s), **Standard** (≈ 48 Frames / 60 s), **Pro** (≈ 120 Frames / 3 min, 4K, Multidistanz) | Must |
| F-106 | Pro: Nutzung der Rückkamera mit Selfie-Spiegel-Assistent (zweite Person oder Spiegel) für Hinterkopf | Must |
| F-107 | Live-Qualitätsampel: Schärfe, Bewegung, Ausleuchtung, Abdeckung (bereits abgedeckte Winkel) | Must |
| F-108 | Sprachführung (on-device TTS, DE/EN) + Vibration, abschaltbar | Must |
| F-109 | Brillen-, Bart-, Kopfbedeckungs-Check mit Hinweis ("Brille bitte abnehmen – oder Quick-Modus") | Must |
| F-110 | Augen- und Mund-innen-Aufnahmen (geoöffnete Augen, "Aaaah", "Eeee") für Zähne/Zunge/Mundraum | Must (ab Standard) |
| F-111 | Guided-Expression-Set (neutral, lächeln, Augen zu, Brauen hoch, Brauen runter, Mund weit, Kiefer links/rechts, Nase rümpfen, "O", Wangen aufblasen) → personalisierte Blendshapes | Must (ab Standard) |
| F-112 | Optional: ToF/Depth-Frames als zusätzliche Hypothese nutzen (`DEPTH16`) | Could |
| F-113 | Optional: DUAL-Kameras (Stereo-Baseline) als Extra-Tiefenquelle | Could |
| F-114 | Übungsmodus mit CG-Puppe (mannequin) statt echtem Gesicht | Should |

### 3.2 Rekonstruktion

| ID | Anforderung | Prio |
|---|---|---|
| F-201 | Kamerapose je Frame aus Face-Landmarks (EPnP/RANSAC) + Intrinsics; **kein ARCore/SLAM** | Must |
| F-202 | Multi-Frame-3DMM-Fit (Identität geteilt, Expression/Pose/Licht pro Frame) | Must |
| F-203 | Dense MVS (Plane-Sweep / PatchMatch) auf GPU bei halber/viertel Auflösung | Must |
| F-204 | TSDF-Volumenfusion (Hashed Voxel, 0,5–1,0 mm) → Marching Cubes | Must |
| F-205 | Getrennte Fusion für Haut (stark geglättet) und Haar (schwach geglättet, maskengewichtet) | Must |
| F-206 | Wasserdichte Variante (Poisson) alternativ erzeugbar | Should |
| F-207 | Haar-Stufe 1: Haar-Cap (Volumen aus Haar-TSDF) | Must |
| F-208 | Haar-Stufe 2: + Strömungsfeld + Haar-Cards (50–250 Karten mit Alpha) | Must (Creator) |
| F-209 | Haar-Stufe 3: + echte Strands/Guides (bis ~50 k Strähnen auf High-End) mit Kollision gegen Kopf | Should (Studio) |
| F-210 | Non-Rigid-ICP-Registrierung des FaceScan-Basiskopfs (eigene Topologie, ~8–12 k Verts) | Must |
| F-211 | Transfer von Details als Displacement/Normal (16/32-bit) | Must |
| F-212 | 52 ARKit-kompatible Blendshapes, personalisiert (aus Guided Expressions + Deformations-Transfer) | Must |
| F-213 | Augäpfel, Hornhaut, Tränenflüssigkeit, Zähne, Zunge, Mundinnenraum (Template + Aufnahme) | Must (ab Standard) |
| F-214 | UV-Atlas (automatisch, streckungsarm) + Textur-Baking: Albedo, Normal, Roughness, AO/Cavity, SSS-Maske, Displacement | Must |
| F-215 | Textur-Auflösung 2K (Free) / 4K (Creator) / 8K (Studio) | Must |
| F-216 | LOD-Kette (LOD0…LOD3) + optionale Quad-Retopologie | Should |

### 3.3 Anzeige / Bearbeitung

| ID | Anforderung | Prio |
|---|---|---|
| F-301 | Eigener Renderer (Vulkan/GLES) mit PBR + SSS-Näherung + Haar-Karten-Shader | Must |
| F-302 | Orbit/Zoom/Pan per Geste, Auto-Rotate, Referenz-Grid, Beleuchtungs-Presets (Studio/Tageslicht/Sonne/Neon) | Must |
| F-303 | Vergleichsslider Foto ↔ Render, Kanten-/Drahtmodell-Overlay, Normals-/UV-/Displacement-Ansicht | Should |
| F-304 | Qualitätsbericht (Ampel + 5 Kennzahlen in Laiensprache) | Must |
| F-305 | Einfache Nachregler: Haut glätten, Poren-Detail, Haarvolumen, Haarlänge, Farbanpassung | Should |
| F-306 | "Nochmal scannen mit Tipps" – aus dem Qualitätsbericht direkt in die Aufnahme mit konkreten Hinweisen | Must |

### 3.4 Animation

| ID | Anforderung | Prio |
|---|---|---|
| F-401 | Live-Gesichtsanimation: 52 Blendshapes + Kopfpose, ≥ 25 fps Mittelklasse | Must |
| F-402 | Neutral-Kalibrierung (2 s ruhig) + Bereichskalibrierung (max. Lächeln etc.) | Must |
| F-403 | Emotions-Presets (Freude, Trauer, Wut, Überraschung, Ekel, Angst, Verachtung) als Regler | Should |
| F-404 | Live-Körper-Mocap (33 Gelenke) + Hände (2 × 21) | Must (Studio) / Should (Creator) |
| F-405 | Aufnahme von Motion-Clips (30/60 fps) mit Speicherung als `.fsmc` | Must |
| F-406 | Live-Vorschau mit dem eigenen Avatar + optional Green-Screen/Transparenz für OBS-Workflows | Could |
| F-407 | Audio-gestützter Lip-Sync (Viseme on-device) aus aufgenommenem Ton | Could (v2) |
| F-408 | Optionaler lokaler Stream (Wi-Fi/UDP) an Desktop-Begleit-App (kein Cloud-Zwang) | Could |

### 3.5 Export

| ID | Anforderung | Prio |
|---|---|---|
| F-501 | Formate: GLB/glTF, OBJ+MTL, PLY, STL, DAE, USD/USDZ, FBX (binär), ABC (Alembic) | Must |
| F-502 | Motion-Export: BVH, ABC (Point-Cache), FBX (baked), glTF (Morph-Animation), USDA (UsdSkel), CSV/JSON | Must (Studio) |
| F-503 | Einheiten (m/cm/mm) + Up-Achse (Y/Z) + Händigkeit wählbar, mit Voreinstellung pro Zielsoftware | Must |
| F-504 | Textur-Set getrennt/eingebettet, Kanal-Konvention (DirectX/OpenGL-Normal), 8/16/32-bit, PNG/JPEG/EXR/WebP | Must |
| F-505 | **Format-Assistent**: Ziel → empfohlenes Format + Settings in Laiensprache | Must |
| F-506 | Export als `.fscan`-Projekt (verlustfrei, wiederöffnbar) | Must |
| F-507 | Export über SAF in `Dokumente/FaceScan/<Name>/` + Android-Share-Sheet | Must |
| F-508 | Stapel-Export (mehrere Formate in einem Durchlauf) | Should |
| F-509 | Optional: C2PA-Content-Credentials (signierte Herkunft, offline signiert) | Should |
| F-510 | Optional: 3D-Druck-Paket (STL watertight + Sockel + Wandstärkenprüfung) | Should |

### 3.6 System / Konto / Monetarisierung

| ID | Anforderung | Prio |
|---|---|---|
| F-601 | Vollständige Nutzung ohne Konto, ohne Netz, ohne Cloud | Must |
| F-702 | Lokaler, verschlüsselter Tresor (AES-256-GCM, Keystore) mit PIN/Biometrie-Schloss | Must |
| F-703 | Kauf per SOL, BTC, ETH; Lizenz-Token lokal signiert; 30-Tage-Nachprüfung mit Grace | Must |
| F-704 | "Kauf wiederherstellen" über Tx-Hash (Quittung) | Must |
| F-705 | DSGVO: Datenübersicht, vollständige Löschung, Projekt-Export | Must |
| F-706 | Telemetrie strikt opt-in, anonym, ohne Identifier | Must |

## 4. Nicht-funktionale Anforderungen

| ID | Anforderung | Zielwert |
|---|---|---|
| N-101 | Scan-Dauer Ende-zu-Ende (Standard, Mittelklasse) | ≤ 180 s |
| N-102 | Scan-Dauer Quick (Mittelklasse) | ≤ 45 s |
| N-103 | Scan-Dauer Pro (High-End) | ≤ 480 s |
| N-104 | Speicherbedarf der App (installiert, mit Modellen) | ≤ 350 MB (Heavy-Modelle als Asset-Pack nachinstallierbar) |
| N-105 | Spitzen-RAM während Rekonstruktion | ≤ 1,6 GB auf 6-GB-Geräten (Profil "Low-Memory") |
| N-106 | Absturzrate (Crash-free sessions) | ≥ 99,5 % |
| N-107 | ANR-Rate | ≤ 0,2 % |
| N-108 | Akkuverbrauch Standard-Scan | ≤ 6 % (Mittelklasse) |
| N-109 | Thermik: kein Abbruch wegen Überhitzung | Adaptive Drosselung ab `THERMAL_STATUS_MODERATE`, Pause ab `SEVERE` |
| N-110 | Wiederaufnahme nach Unterbrechung (Anruf, App-Wechsel, Akku leer) | Checkpoint je Pipeline-Stufe, Fortsetzung garantiert |
| N-111 | Android-Version | minSdk 29 (Android 10), targetSdk aktuell (≥ 36) |
| N-112 | 16-KB-Page-Size-Konformität | Alle `.so` mit NDK r28+ / `ANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON` gebaut |
| N-113 | Sprachen | Deutsch, Englisch (ab Tag 1), weitere nach Bedarf |
| N-114 | Barrierefreiheit | WCAG 2.2 AA (Kontrast, Touch-Targets ≥ 48 dp, TalkBack, Schriftgröße bis 200 %) |
| N-115 | Kein Netzwerkverkehr im Kernpfad | Mit Netzwerk-Monitor (Strikt-Modus + Proxy-Test) nachgewiesen |
| N-116 | Lizenz- und Herkunftsnachweis | `THIRD_PARTY_LICENSES.md` automatisch generiert, im App-Menü sichtbar |

## 5. Abgrenzung (Out of Scope für v1)

- Ganzkörper-Scan (nur Kopf/Hals/Schulteransatz + separater Body-Rig für Mocap).
- Kleidungsscan, Hand-Scan als Geometrie (Hände nur als Rig).
- Cloud-Backup, Konto-Synchronisation, Multi-Device-Bibliothek.
- iOS-Version.
- Photogrammetrie von Objekten/Räumen (Fokus Gesicht + Haar).
- Generative "Verbesserung" durch Cloud-Modelle (rein on-device, deterministisch).
- Community-Marktplatz, Avatar-Sharing.

## 6. Abnahmekriterien für v1 ("Definition of Done")

1. 20 Testpersonen (davon 8 ohne 3D-Erfahrung, 6 verschiedene Haar-Typen/-Frisuren, 3 Hauttöne nach Fitzpatrick I–VI,
   4 mit Brille/Bart) erreichen ein verwertbares Ergebnis ohne Hilfe.
2. Blindvergleich Foto ↔ Render: ≥ 80 % der Personen werden von Bekannten "eindeutig erkannt".
3. Alle Must-Exporte öffnen sich in den Zielprogrammen ohne Nacharbeit (siehe `10-test-qa-performance.md`).
4. Flugmodus-Test: Scan → Animieren → Export funktioniert vollständig.
5. Play-Store-Vorprüfung (Data Safety, Prominent Disclosure, Ziel-API, 16 KB) bestanden.
6. Landingpage live auf Cloudflare Pages mit Impressum, Datenschutz, Preisen und Krypto-Adressen.
