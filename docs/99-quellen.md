# 99 – Quellen der Recherche

Stand: 2026-11-15 · Alle technischen Kernaussagen dieser Dokumentation sind hier belegt.

---

## Gesichtserkennung / Tracking (on-device, ohne ARCore)

| # | Quelle | Kernaussage |
|---|---|---|
| [1](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker) | Google AI Edge – Face Landmarker | 478 3D-Landmarks, **52 Blendshape-Scores**, optionale 4×4-„facial transformation matrix" (canonical→beobachtet), Running-Modus `LIVE_STREAM`, Ausführung on-device |
| [2](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/android) | Face Landmarker – Android | Optionen `outputFaceBlendshapes`, `outputFacialTransformationMatrixes`; Hinweis: `*Left`/`*Right` beziehen sich auf die **Person**, Spiegelung invertiert sie |
| [3](https://webai.show/models/face-landmarker/) | WebAI Showcase – FaceLandmarker | Bestätigung: Modell ~4 MB, läuft lokal, Apache-2.0, 52 „ARKit-style" Kanäle |
| [4](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker) | Google AI Edge – Pose Landmarker | 33 Landmarks, zusätzlich **WorldLandmarks in Metern** (Ursprung Hüftmitte), optionale Segmentierungsmaske |
| [5](https://developers.google.com/edge/mediapipe/solutions/vision/holistic_landmarker?tab=Python) | Google AI Edge – Holistic Landmarker | Kombination: 478 Gesicht + 33 Pose (Bild + Welt) + 2 × 21 Hand + 52 Blendshapes + Maske |

## Haar-Segmentierung

| # | Quelle | Kernaussage |
|---|---|---|
| [6](https://gitlab.nrp-nautilus.io/ar-noc/mediapipe/-/tree/master/mediapipe/models) | MediaPipe-Modellliste („Hair Segmentation") | `hair_segmentation.tflite`, Paper „Real-time Hair segmentation and recoloring on Mobile GPUs" |
| [7](https://theneuralbase.com/mediapipe/learn/intermediate/hair-segmentation/) | MediaPipe Hair Segmentation (Praxisbericht) | Modellpfad `…/image_segmenter/hair_segmenter.tflite`, 2 Klassen (Hintergrund/Haar), `output_confidence_masks` liefert Float-Wahrscheinlichkeiten statt harter Maske |
| [8](https://dev.to/gabbrowick/live-hair-colour-try-on-entirely-on-the-phone-mediapipe-in-a-webview-inside-flutter-4jof) | Praxis: Haar-Try-on komplett auf dem Telefon | `hair_segmenter.tflite`, 780 KB, 2 Klassen; ~10 ms Inferenz auf einem Pixel 8 Pro mit GPU-Delegate; „kein Frame verlässt das Telefon" |

## Mobile Stereo-/Tiefenberechnung (Leistungsbudget)

| # | Quelle | Kernaussage |
|---|---|---|
| [9](https://www.microsoft.com/en-us/research/wp-content/uploads/2022/09/mobicom22-final138.pdf) | MobiDepth (MobiCom 2022) | Mobiles Stereo-Matching ist **speicherbandbreiten-limitiert**; Fusions- und Slicing-Optimierungen nötig – Bestätigung unserer Vulkan-Compute-Architektur |

## Formate

| # | Quelle | Kernaussage |
|---|---|---|
| [10](https://projects.blender.org/blender/blender-addons/issues/79960) | Blender-Issue „FBX are not supported" | Blender unterstützt **FBX-ASCII seit 2.8 nicht mehr** (Entfernung 2018); für aktuelles ASCII-FBX wäre ein Autodesk-SDK nötig ⇒ unser eigener binärer Writer |
| [11](https://dev.to/cy_cy_a73a75ea2dde2b6cf02/your-usdz-will-be-rejected-by-an-iphone-three-packaging-rules-apple-doesnt-negotiate-2960) | USDZ-Packaging-Regeln | USDZ = ZIP mit **allen Einträgen unkomprimiert (ZIP_STORED)**, **64-Byte-Alignment** der Daten, keine Verschlüsselung; Verstoß ⇒ Ablehnung durch iPhone/Blender-Import |
| [12](https://www.danthree.studio/en/glossary/usdz-file-format) | „What is USDZ?" | USDZ = unkomprimiertes, unverschlüsseltes ZIP aus USDA/USDC/USD + Texturen; Content-Type `model/vnd.usdz+zip` |
| [13](https://github.com/alembic/alembic/blob/master/LICENSE.txt) | Alembic-Lizenztext | **BSD-3-Clause** (Lucasfilm/Sony Pictures Imageworks) ⇒ kommerziell nutzbar |
| [14](https://www.loc.gov/preservation/digital/formats//fdd/fdd000583.shtml) | Library of Congress – OpenEXR | OpenEXR: **BSD-3-Clause**; Imath ist eine **Pflichtabhängigkeit** zum Bauen von Alembic |
| [15](https://github.com/AcademySoftwareFoundation/Imath) | Imath (ASWF) | **BSD-3-Clause**, Vektor-/Matrix-Mathematik, „half"-Typ |
| [16](http://www.assimp.org/index.php?id=11:faq) | Assimp-FAQ | „Am I allowed to use the library in a commercial product?" → **Ja**, modifizierte BSD-Lizenz, Namensnennung erforderlich, keine Werbung mit dem Namen |

## Geometrie-/Mesh-Bibliotheken

| # | Quelle | Kernaussage |
|---|---|---|
| [17](https://github.com/mkazhdan/PoissonRecon) | PoissonRecon (Kazhdan/Hoppe) | **MIT**, Poisson Surface Reconstruction |
| [18](https://github.com/isl-org/Open3D-PoissonRecon) | Open3D-PoissonRecon | **MIT** |
| [19](https://www.open3d.org/paper.pdf) | Open3D-Paper | Open3D ist **MIT** (Nutzung nur in unserer Test-Toolchain) |
| [20](https://github.com/prideout/xatlas) | xatlas | **MIT**, UV-Parametrisierung ohne externe Abhängigkeiten (C++11) |
| [21](https://www.reddit.com/r/blender/comments/1imqe6k/makehuman-license/) | MakeHuman-Lizenz (Diskussion) | Quellcode AGPL, **Kern-Assets CC0**, Ausgaben frei nutzbar – vor Verwendung juristische Zweitmeinung einholen |

## Modell-Lizenzen (3DMM) – Ausschlussgründe

| # | Quelle | Kernaussage |
|---|---|---|
| [22](https://flame.is.tue.mpg.de/modellicense.html) | FLAME-Modelllizenz | Academic Model License: **kommerzielle Nutzung ausdrücklich verboten**; nur „FLAME 2023 Open" unter CC-BY, mit Verboten (pornografisch, „fake, libelous, misleading") |
| [23](https://github.com/USC-ICT/ICT-FaceKit) | ICT-FaceKit | Repo nennt **MIT**, gleichzeitig Bezeichnung „non-commercial version" ⇒ widersprüchlich, **nicht ohne anwaltliche Klärung verwenden** |
| [24](https://github.com/fernandotonon/QtMeshEditor/issues/889) | Diskussion: ARKit-Blendshapes per Deformation Transfer | Bestätigt: ICT-FaceKit MIT-Tier, FLAME „research-only"; Algorithmus „Deformation Transfer" (Sumner & Popović) frei, Referenzimplementierung MIT |

## Krypto-Zahlungen

| # | Quelle | Kernaussage |
|---|---|---|
| [25](https://devrels.xyz/articles/solana-pay-the-spec) | Solana Pay – Spec-Praxis | Pro Bestellung ein **Referenz-Public-Key** im `solana:`-URL; `findReference`/`getSignaturesForAddress(reference)` findet die Zahlung ohne Tx-Eingabe; `validateTransfer` prüft Empfänger/Betrag/Mint |
| [26](https://stablecoininsider.org/solana-pay-usdc/) | Solana Pay USDC (Praxis 2026) | Referenz als Read-only-Account; `findReference` (Polling) vs. `watchReference` (WebSocket); Finalität `confirmed`/`finalized`; Börsenauszahlungen können **keine** Referenz setzen ⇒ Betrags-Eindeutigkeit als Rückfall |
| [27](https://dev.to/ammadkapadiaa/accept-usdc-on-a-static-site-with-solana-pay-and-a-cloudflare-worker-no-kyc-processor-1cjf) | Solana-Pay auf statischer Seite | Bestätigt das Referenz-Muster; „eine Signatur bezahlt genau eine Bestellung"; Signatur-Wiederverwendung ablehnen; bei Betrags-Matching muss die Signatur **neuer als die Bestellung** sein |
| [28](https://norman.finance/de/en/blog/accepting-cryptocurrency-payments-germany) | Krypto-Zahlungen in DE 2026 | Legal, aber kein gesetzliches Zahlungsmittel; **Tausch** nach § 3 Abs. 12 UStG; Rechnung in EUR; Kursquelle dokumentieren; CARF/DAC8 ab 2026 |
| [29](https://flexlogistique.fr/crypto-payments-and-vat-what-sellers-should-know/) | Krypto & MwSt (EU) | Ab 10.000 € grenzüberschreitenden B2C-Umsätzen OSS-Registrierung; Anbieter digitaler Dienstleistungen müssen ggf. ab der ersten Leistung registriert sein; Aufzeichnungspflichten inkl. Wallet-Adressen und Tx-IDs |
| [30](https://www.icon.partners/post/dac8-in-the-eu-crypto-transactions-now-reported-to-tax-authorities) | DAC8 | Pflichten ab 1.1.2026, erste Meldungen 2027; primär für CASPs; Selbstverwahrung grundsätzlich außerhalb, **Sichtbarkeit steigt dennoch** |
| [31](https://tangem.com/en/learning-hub/post/mica-crypto-rules-germany/) | MiCA in DE | BaFin-Aufsicht; Plattformen ohne CASP-Lizenz müssen EU-Kunden ab 1.7.2026 nicht mehr bedienen; **Selbstverwahrung ist von MiCA ausdrücklich ausgenommen** (Transfers zwischen eigenen Wallets) |

## Google Play / Android

| # | Quelle | Kernaussage |
|---|---|---|
| [32](https://github.com/react/react-native/issues/53649) | 16-KB-Page-Size (Play-Pflicht) | Ab Nov. 2025 für Apps mit nativen Bibliotheken, die Android 15+ anvisieren; NDK r28+ bzw. `ANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON`; Fremd-`.so` müssen nachgebaut werden |
| [33](https://www.reddit.com/r/androiddev/comments/1tqd2t8/google_quietly_extended_the_16kb_page_size/) | Fristverlängerung | Erst Nov. 2025 → Mai 2026 → offenbar **1. Feb. 2027**; Frist im Play-Konsolen-Konto prüfen |
| [34](https://legiflare.com/blog/google-play-prominent-disclosure) | Prominent Disclosure | Muss **in der App** erscheinen, im normalen Nutzungsfluss, vor Beginn der Datenerfassung, darf **nicht nur** in Datenschutzerklärung/AGB stehen, muss Datenart und Zweck nennen und ausdrückliche Zustimmung einholen |
| [35](https://www.termsfeed.com/blog/android-sensitive-data-collection/) | Android: sensible Daten | Zustimmung, Transparenz, Datenminimierung, Sicherheit; In-App-Hinweis darf nicht mit anderen Hinweisen vermischt und nicht nur über einen Link erreichbar sein; Auto-Dismiss unzulässig |
| [36](https://support.google.com/googleplay/android-developer/answer/10787469?hl=en) | Data-Safety-Formular | Verpflichtend und wahrheitsgemäß; Entwickler tragen die Verantwortung |

## Provenienz (C2PA)

| # | Quelle | Kernaussage |
|---|---|---|
| [37](https://proofmode.org/blog/simple-c2pa) | Simple C2PA for Mobile | Rust-SDK-basiert; **Schlüssel und selbst-signiertes X.509-Zertifikat komplett lokal auf dem Gerät erzeugbar**; Android-Bibliothek verfügbar; Beispielcode (Kotlin) |
| [38](https://github.com/contentauth/c2pa-android-example) | c2pa-android-example | Referenz-App (Compose + CameraX), Signierung mit lokal im Keystore gehaltenen RSA-Keys, In-Place-Signierung unter Scoped Storage |
| [39](https://c2pa.org/faqs/) | C2PA-FAQ | C2PA ist ausdrücklich für **Offline-Workflows** ausgelegt: Geräte können lokal signieren; Zertifikate vorab bereitstellen und später erneuern; durable Credentials (Wasserzeichen) als Zusatz |

## Design (Barrierefreiheit der Flaggenfarben)

Kontrastwerte wurden für dieses Dokument selbst berechnet (WCAG-2.2-Formel, relative Leuchtdichte):

| Paar | Ergebnis |
|---|---|
| Schwarz auf Grün `#009B3A` | **5,75:1** ✔ AA |
| Schwarz auf Gold `#FFD100` | **14,37:1** ✔ AAA |
| **Weiß** auf Grün `#009B3A` | **3,65:1** ✘ für Fließtext (nur große Schrift) |
| **Weiß** auf Gold `#FFD100` | **1,46:1** ✘ unbrauchbar |
| Grün `#007A2E` auf Weiß (Day-Mode) | **5,49:1** ✔ AA |
| Gold `#8A6A00` auf Weiß (Day-Mode-Text) | **5,07:1** ✔ AA |
| Fehlerrot `#B3261E` auf Weiß | **6,54:1** ✔ AA |
| Grün `#00B34A` auf `#0E0E0E` (Night) | **6,94:1** ✔ AA |
