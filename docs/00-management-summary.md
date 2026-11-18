# 00 – Management Summary / Gesamtkonzept

Stand: 2026-11-15 · Entwickler: AndrexTheDev (hippie.highho@gmail.com)

---

## 1. Produktsatz (ein Satz)

**FaceScan** ist eine kommerzielle Offline-First-Android-App, die mit der Handykamera in unter zwei Minuten ein
detailgetreues, animierbares 3D-Modell von Gesicht **und Haaren** erzeugt, es live mit Gesichts- und
Körper-Tracking animiert und in alle gängigen Profi-3D-Formate exportiert – ohne ARCore, ohne Cloud, ohne Konto.

## 2. Die fünf harten Produktversprechen

| # | Versprechen | Messbare Definition (v1) |
|---|---|---|
| P1 | **Offline** | Kein Netzwerkaufruf während Scan, Rekonstruktion, Animation, Export. Nachweisbar per "Flugmodus-Test" im Release-Check. |
| P2 | **Gesicht + Haar** | Silhouetten-IoU ≥ 0,93 (Haut) bzw. ≥ 0,85 (Haar) gegen Masken der Aufnahmebilder; Wiedererkennung im Blindtest ≥ 80 % Zustimmung. |
| P3 | **Animierbar** | 52 ARKit-Blendshapes + Kopfpose live mit ≥ 25 fps auf Mittelklasse (Snapdragon-7-Klasse); Körper-Retargeting mit 33 Gelenken ≥ 25 fps. |
| P4 | **Profi-Export** | GLB, USDZ, FBX, ABC, OBJ, DAE, PLY, STL öffnen fehlerfrei in Blender 4.x, Maya 2025, Unreal 5.5, Unity 6, Houdini 20, ZBrush 2025, Substance Painter (je nach Format). |
| P5 | **Einsteigerfreundlich** | Erstnutzer:innen (ohne 3D-Wissen) schaffen Scan → Animieren → Export in ≤ 6 Minuten ohne Hilfe (gemessen im Usability-Test, n ≥ 12). |

## 3. Warum das ohne ARCore funktioniert (das Kernargument)

ARCore liefert SLAM (Kameraposenschätzung), Tiefensensoren und Anker. **Wir brauchen keins davon**, weil wir die
Kamerapose aus dem Gesicht selbst ableiten:

1. MediaPipe Face Landmarker liefert **478 3D-Landmarks** plus eine **metrische 4×4-Transformationsmatrix**
   (canonical → Kamera) – on-device, ohne Cloud [1](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker).
2. Die Kamera-**Intrinsics** (Brennweite in Pixel, Hauptpunkt, Verzeichnung) kommen aus Camera2
   (`LENS_INTRINSIC_CALIBRATION`).
3. Damit ist die Szene **metrisch skaliert**: das kanonische Gesichtsmodell hat reale Zentimeter-Ausdehnung,
   die Brennweite ist in Pixel bekannt ⇒ aus `(Pose, Intrinsics)` folgt echte Entfernung in mm.
4. Für jedes aufgenommene Bild lösen wir zusätzlich ein **EPnP/RANSAC** über die 478 Korrespondenzen – damit sind
   die Kameraposen stabiler als ein reines SLAM es bei 60 kurzen Frames wäre (kein Drift, keine Initialisierung).

> **Konsequenz:** Wir brauchen keine Bewegungssensoren-Fusion, kein Feature-Tracking, kein Tiefensensor.
> Gravity-Vektor aus dem Beschleunigungssensor dient nur als *Up-Vektor-Prior* für die Export-Achsen.
> Falls ein Gerät echtes Depth (`DEPTH16`) oder einen ToF-Sensor hat, nutzen wir ihn **optional** als Extra-Hypothese
> im TSDF-Fusion – nie als Voraussetzung.

Benötigte Permissions: `CAMERA` (Pflicht), `RECORD_AUDIO` (nur optional für Lip-Sync in v2),
`POST_NOTIFICATIONS` (nur für den Verarbeitungs-Service-Hinweis). Kein Standort, keine Kontakte, kein `INTERNET` für
die Kernfunktionen (das Internet-Recht wird nur für Kauf/Verifikation und optionale "Preis-Kurs"-Abfrage genutzt
und ist im Manifest als solches dokumentiert).

## 4. Zielgruppen & Einstiegsnutzen

| Zielgruppe | Einstiegsnutzen ("Warum installieren?") |
|---|---|
| Einsteiger / Hobby | "Ein 3D-Porträt von mir – als Andenken, für Social Media, als 3D-Druck." |
| Streamer / VTuber | "Mein Gesicht als animierbarer Avatar in 30 Minuten statt 300 € beim Modeler." |
| Indie-Game-Dev | "NPC-Gesichter aus dem echten Leben, GLB mit Blendshapes direkt in die Engine." |
| 3D-Artists (Blender/ZBrush/Maya) | "Scan als Ausgangsbasis, dann in der Profi-Software verfeinern." |
| 3D-Druck-Dienstleister | "Büste als STL in 5 Minuten." |

## 5. Geschäftsmodell (Kurzfassung – Details in `08`)

Freemium mit **Einmalkäufen** (Krypto-Zahlungsverkehr hat keine wiederkehrende Einzugslogik – daher:
Lifetime-Tiers + optionale Credit-Packs statt Abo).

| Tier | Preis (EUR-Äquivalent) | Kerninhalt |
|---|---|---|
| **Starter** (Free) | 0 € | Unbegrenzt scannen, 3 gespeicherte Avatare, Export GLB (20k Tris, 2K), 52 Blendshapes, Wasserzeichen im *Render-Bild*, nicht kommerziell nutzbar |
| **Creator** (Lifetime) | 39 € | Alle Mesh-Formate, 4K-Texturen, Haar-Cards, keine Wasserzeichen, kommerzielle Indie-Lizenz (< 100 k€ Umsatz), unbegrenzte Avatare |
| **Studio** (Lifetime) | 129 € | 8K-Texturen, Haar-Strands, Rig + Mocap-Export (BVH/ABC/FBX/USDskel), Studio-Kommerziallizenz (unbegrenzt), Body-Mocap, Multi-Avatar-Projekt |
| **Credit-Packs** | 4,90 € / 10 Stk. | Einzelexporte, Haar-Detail-Boost, Motion-Render-Pakete |

Zahlung ausschließlich in **SOL, BTC, ETH** an die vorgegebenen Adressen.
SOL ist der Hauptpfad (Referenz-Key-Technik, Sekunden-Finalität), BTC/ETH über Betrags-Fingerprint + Memo.
**Der Blockchain-Tx-Hash ist die Quittung** – daraus plus unserer Ed25519-Signatur entsteht das lokal
gespeicherte Lizenz-Token (offline gültig, 30-Tage-Online-Nachprüfung mit Grace-Periode).

## 6. Meilensteine (Überblick – Detailplan in `11`)

| Phase | Ziel | Dauer | Ergebnis |
|---|---|---|---|
| M0 | Machbarkeits-Prototyp (3DMM-Fit + MVS auf 3 Geräten) | 6 Wochen | Objektnachweis "Gesicht gut" |
| M1 | Vertikaler Schnitt: Scan → Mesh → GLB/OBJ | 10 Wochen | Interner Alpha-Build |
| M2 | Haar-Pipeline v1 (Haar-Cap + Cards) + Textur-Baking | 10 Wochen | Erste "sieht aus wie ich"-Ergebnisse |
| M3 | Retopo/Rig/Blendshapes + Animation (Gesicht) | 8 Wochen | Animierbarer Avatar |
| M4 | Export-Suite (FBX/USD/ABC/DAE/PLY/STL) + Format-Assistent | 8 Wochen | Profi-Export fertig |
| M5 | Körper-Mocap, Mocap-Export, UI-Politur, i18n DE/EN | 8 Wochen | Closed Beta |
| M6 | Monetarisierung (Krypto), Compliance, Landingpage, Release | 8 Wochen | Play-Release + Cloudflare-Pages-Site |

**Gesamt: ca. 58 Wochen (≈ 13–14 Monate)** bei 1 Entwickler + punktueller Unterstützung
(3D-Artist für Basismesh/Rig, Deutsch/Englisch-Lektorat, Steuerberatung). Realistischer Kalender bis Public Release:
**Q1 2028**, erste öffentliche Beta **Q3 2027**.

## 7. Top-Risiken (und Gegenmaßnahmen)

| # | Risiko | Wahrscheinlichkeit | Wirkung | Gegenmaßnahme |
|---|---|---|---|---|
| R1 | **Haar-Rekonstruktion** wirkt "wie eine Badekappe" | Hoch | Hoch | Haar-Cap + Cards + Strands als 3 Qualitätsstufen; Orientierungsfeld aus Gabor-Filtern; echte Strands erst ab "Studio"; von Beginn an mit 20 Testköpfen (verschiedene Frisuren/Typen) bewerten |
| R2 | **Thermik/Abstürze** auf Mittelklasse bei Pro-Modus | Hoch | Mittel | Stufenweises Budget (Thermal-Headroom API), Checkpoint/Resume, Geräteklassen-Profile, Pro nur mit Akku > 35 % |
| R3 | **Lizenzen** (FLAME/Basel sind forschungs-only) | Mittel | Sehr hoch | Eigene 3DMM aus eigenen, lizenzierten Scans aufbauen; ICT-FaceKit (MIT-Laut Repo) nur nach anwaltlicher Prüfung; niemals GPL/AGPL-Code in die App (VCGLib, MeshLab vermeiden) |
| R4 | **Krypto-Zahlung** schemeitert an Betragszuordnung (BTC/ETH, eine Adresse) | Mittel | Mittel | Betrags-Fingerprint + Memo + manueller "Tx einreichen"-Pfad mit Support; SOL als empfohlener Pfad prominent |
| R5 | **Play-Store-Ablehnung** (Kamera/Biometrie/Data-Safety) | Mittel | Hoch | Prominent In-App-Disclosure vor erstem Scan, Data-Safety-Formular "keine Erhebung/kein Upload", Alters-Gate 16+, keine Ad-/Tracking-SDKs |
| R6 | Piraterie (signierte Lizenzdatei kopierbar) | Hoch | Gering | Gerätebindung + Online-Transfer, Aufwand > Nutzen für Gelegenheitsnutzer; Fokus auf Bequemlichkeit statt Kopierschutz |

## 8. Wichtigste technische Entscheidungen (Kurzform, begründet in `13`)

| Entscheidung | Warum |
|---|---|
| **Native Kotlin + C++-Kern** (kein Flutter/RN/Unity) | Volle Kontrolle über Kamera2, Vulkan-Compute, Speicher und 16-KB-Page-Size; keine Engine-Lizenzkosten; beste Performance für MVS |
| **MediaPipe Tasks** statt eigener Modelle | 478 Landmarks + 52 Blendshapes + 4×4-Pose + Haar-Segmentierung out-of-the-box, Apache-2.0, on-device, kein ARCore nötig |
| **Eigene Export-Writer** statt Assimp | Volle Kontrolle über Blendshapes/Displacement/Units; Assimp schreibt nur FBX-ASCII, das Blender ≥ 2.8 nicht mehr importiert |
| **Eigene Basismesh/3DMM** statt FLAME/BFM | FLAME/Basel: Forschungs-Lizenz, keine kommerzielle Nutzung. Eigenes Modell = freie kommerzielle Nutzung + Wettbewerbsvorteil |
| **Alembic/Imath/PoissonRecon/Open3D** (BSD-3/MIT) | Rechtlich unbedenklich, auf Android baubar |
| **Landingpage als statische Seite ohne Build** | Cloudflare Pages braucht nur ein Verzeichnis; kein Node-Build, keine Supply-Chain-Risiken, extrem schnell |

## 9. Aktueller Stand

| Dimension | Stand |
|---|---|
| Anforderungs-/Konzeptdeckung der gestellten Fragen | **100 %** (alle 12 Themenfelder ausgearbeitet) |
| Recherche/Technologiewahl belegt | **100 %** (Quellen in `99-quellen.md`) |
| Landingpage (Cloudflare Pages) | **85 %** (strukturell + inhaltlich vollständig, Screenshots/Grafiken folgen) |
| Architektur & Pipelines spezifiziert | **80 %** (Algorithmik festgelegt, Parameter müssen empirisch kalibriert werden) |
| Designsystem (Farben, Screens, Copy) | **70 %** (Tokens + Flows definiert, kein Compose-Code) |
| App-Code | **0 %** |
| **Gesamtfertigstellung des Produkts** | **≈ 3 %** |
