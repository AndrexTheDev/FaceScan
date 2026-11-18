# FaceScan – 3D-Gesicht- & Haar-Scanner für Android (offline first)

> **Vision:** Mit dem Handy in 60 Sekunden ein animierbares 3D-Porträt von sich selbst einscannen –
> inklusive Haare, in Studio-Qualität, **komplett offline**, exportierbar in jedes Profi-3D-Format.
> Kein ARCore. Keine Cloud. Kein Konto.
>
> **Aktueller Stand, nicht das fertige Produkt:** Die Android-App erstellt eine experimentelle, offene
> Gesichtsoberfläche aus einer Kameraansicht und exportiert GLB/OBJ. Zusätzlich gibt es eine experimentelle
> Mehransichten-Aufnahme aus 2–8 Kopfhaltungen, die ein trianguliertes Teilnetz als OBJ/GLB mit
> Strukturdiagnose ausgibt – skaliert über ein Durchschnittsgesicht, nicht metrisch validiert. Sie benötigt beim ersten Start
> Internet für einen Modelldownload. Haare, Hinterkopf, validierte metrische Genauigkeit und die meisten
> unten beschriebenen Funktionen sind noch nicht implementiert oder nicht real getestet. Details und
> Grenzen: [Android-README](prototype/android/README.md), [Implementierungsstatus](docs/14-implementierungsstatus.md).

**Entwickler:** AndrexTheDev · E-Mail: hippie.highho@gmail.com
**Stand:** experimenteller Android-Prototyp; siehe [Implementierungsstatus](docs/14-implementierungsstatus.md).

---

## Inhalt dieses Repositories

| Datei | Inhalt |
|---|---|
| [`docs/00-management-summary.md`](docs/00-management-summary.md) | Produktkern, USP, Geschäftsmodell, Meilensteine, Top-Risiken, aktueller Stand in % |
| [`docs/01-anforderungen.md`](docs/01-anforderungen.md) | Personas, Use Cases, funktionale + nicht-funktionale Anforderungen (MoSCoW), Abgrenzung |
| [`docs/02-architektur.md`](docs/02-architektur.md) | Schichten, Tech-Stack, Module, Threading, Offline-First-Regeln, Performance-Budget |
| [`docs/03-scan-pipeline.md`](docs/03-scan-pipeline.md) | **Kern-IP:** Kamera-Assistent → 3DMM-Fit → MVS → Haar-Rekonstruktion → Retopo/Rig → Textur |
| [`docs/04-animation-mocap.md`](docs/04-animation-mocap.md) | Gesicht (52 Blendshapes) + Körper-Mocap ohne ARCore, Retargeting, Aufnahme, Export |
| [`docs/05-export-formate.md`](docs/05-export-formate.md) | Formatmatrix, eigene Writer, Einheiten/Achsen, Validierung, Format-Assistent |
| [`docs/06-offline-first-datenmodell.md`](docs/06-offline-first-datenmodell.md) | `.fscan`-Container, Vault, Verschlüsselung, Asset-/Modell-Management, Thermik |
| [`docs/07-ui-ux-designsystem.md`](docs/07-ui-ux-designsystem.md) | Farbtokens (Jamaika + Day-Mode), Screens, Flows, Copy DE/EN, Barrierefreiheit |
| [`docs/08-monetarisierung-crypto.md`](docs/08-monetarisierung-crypto.md) | Freemium-Modell, SOL/BTC/ETH-Flows, Lizenz-Token, Buchhaltung/Steuern |
| [`docs/09-recht-compliance.md`](docs/09-recht-compliance.md) | DSGVO, Biometrie, Play-Policies, C2PA, OSS-Lizenz-Audit, Modell-Lizenzen |
| [`docs/10-test-qa-performance.md`](docs/10-test-qa-performance.md) | Testpyramide, Gerätematrix, Metriken/Schwellwerte, Beta, Release-Checkliste |
| [`docs/11-roadmap.md`](docs/11-roadmap.md) | Phasen M0–M6, Team, Kosten, KPIs |
| [`docs/12-landingpage-cloudflare.md`](docs/12-landingpage-cloudflare.md) | Aufbau + Deployment der Landingpage (Cloudflare Pages) |
| [`docs/13-adr.md`](docs/13-adr.md) | Architecture Decision Records (alle harten Entscheidungen) |
| [`docs/14-implementierungsstatus.md`](docs/14-implementierungsstatus.md) | Tatsächlich implementierte und noch offene Funktionen, Prüfstatus |
| [`docs/99-quellen.md`](docs/99-quellen.md) | Belegte Quellen der Recherche |
| [`landing/`](landing/) | Statische Landingpage (DE/EN) für Cloudflare Pages – Zero-Build |

---

## Die fünf Säulen der Produktvision (geplant)

1. **Offline first** – Kamera, Rekonstruktion, Animation, Export: alles auf dem Gerät. Kein Konto, kein Upload,
   keine Telemetrie ohne explizite Zustimmung. Nur der optionale Kauf (Krypto) braucht einmalig Netz.
2. **Perfektes Gesicht + echte Haare** – geführte Aufnahme, Multi-View-Rekonstruktion mit bekannten Kameraposen
   (aus Face-Landmarks, **ohne SLAM/ARCore**), getrennte Geometrie-Pipelines für Haut und Haar.
3. **Animierbar ohne ARCore** – MediaPipe Face Landmarker liefert on-device 478 Landmarks, 52 ARKit-Blendshapes
   und die 4×4-Kopfpose; Pose Landmarker liefert 33 Körper-Landmarks in Weltkoordinaten (Meter).
4. **Profi-Export** – glTF/GLB, USD/USDZ, FBX, Alembic, OBJ, Collada, PLY, STL + voller Textursatz
   (Albedo/Normal/Roughness/AO/Displacement) + Motion als BVH/ABC/USDskel.
5. **Einsteigerfreundlich** – ein Assistent, ein Button, Ampel-Feedback, Format-Assistent ("Wofür willst du es
   nutzen?"), keine Fachbegriffe ohne "Was ist das?"-Erklärung. Deutsch + Englisch.

## Design-Farben (Jamaika-Flagge)

| Rolle | Hex | Verwendung |
|---|---|---|
| Schwarz (Jamaika) | `#000000` / `#0E0E0E` | Basisfläche Night-Mode |
| Grün (Jamaika) | `#009B3A` | Primärfarbe, Buttons, Fortschritt |
| Gold (Jamaika) | `#FFD100` | Akzent, Erfolg, Highlights |
| Day-Mode-Grün | `#007A2E` | Text/Buttons auf hellem Grund (AA-konform) |
| Day-Mode-Gold | `#8A6A00` | Gold als Text auf hell (Gold selbst besteht Kontrast nicht) |

Details, Kontrastwerte und Token-Tabelle: [`docs/07-ui-ux-designsystem.md`](docs/07-ui-ux-designsystem.md).

## Geplanter Tech-Stack

Kotlin · Jetpack Compose · CameraX + Camera2 (manuelle Sensorkontrolle) · MediaPipe Tasks (Face/Pose/Hand/Hair-Segmentation) ·
TensorFlow Lite (GPU/NNAPI) · C++17-Kern über JNI · Vulkan-Compute (Fallback OpenGL ES 3.1) · Room · WorkManager ·
Android Keystore (AES-256-GCM) · eigene Export-Writer · Cloudflare Pages (nur Landingpage/Website).

## Status

Der Android-Prototyp und synthetische Referenzimplementierungen sind vorhanden; das vollständige Produkt ist nicht fertig. Eine belastbare Prozentzahl und eine validierte reale Messgenauigkeit liegen nicht vor. Der [Implementierungsstatus](docs/14-implementierungsstatus.md) trennt tatsächlich vorhandene Funktionen von Planung und noch ausstehenden Prüfungen.
