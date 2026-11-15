# 06 – Offline-First, Datenmodell, Tresor

Stand: 2026-11-15 · Verantwortlich: `:core:data`, `:feature:processing`

---

## 1. Speicherorte (Android)

| Ort | Inhalt | Warum |
|---|---|---|
| `filesDir/projects/<uuid>/` | Arbeitsdaten laufender/fertiger Projekte (verschlüsselt) | app-privat, nicht über Backup auslesbar |
| `filesDir/models/` | ML-Modelle (`.task`, `.tflite`) + Prüfsummen | Auslieferung im Asset-Pack, Updates optional |
| `filesDir/licenses/` | Lizenz-Token, Quittungen (Tx-Hashes) | lokal, signiert |
| `noBackupFilesDir/vault.key` | Schlüssel-Referenz (Keystore-Handle) | `noBackup` ⇒ nie in Cloud-Backups |
| `cacheDir/tmp/<job>/` | Zwischenergebnisse, `*.stage*.bin`, Thumbnails | löschbar, bei Speicherdruck zuerst |
| SAF `Dokumente/FaceScan/<Projektname>/` | **Nutzer-Export** (Formate, Texturen, Projekt-ZIP) | vom Nutzer kontrolliert, teilbar, löschbar |
| MediaStore (`Pictures/FaceScan`) | Nur wenn Nutzer explizit "als Bild speichern" wählt | Opt-in |

**Nie:** `android:allowBackup="true"` für Projektdaten; keine Analyse-Dateien; keine Crash-Reports ohne
Zustimmung.

## 2. Das `.fscan`-Projektformat (verlustfrei, wiederöffnbar)

Ein **ZIP-Container** (Deflate, 4-Byte-Alignment-frei – es ist kein USDZ), Inhalt:

```
Mein-Kopf.fscan
├── manifest.json            # Version, Schema, Erzeuger, Zeitstempel, Prüfsummen
├── meta.json                # Name, Notizen, Person-Kennung (lokal), Tags, Favorit
├── capture/
│   ├── frames/0001.jpg …    # akzeptierte Frames (optional: "Quellbilder behalten", Default: nach 30 Tagen automatisch löschbar)
│   ├── calibration.json     # K, Verzeichnung, Posen R_t/t_t, IMU-Up-Vektor, Zeiten
│   └── perception.bin       # Landmarks, Blendshapes, Masken-Komprimierung (PNG/RLE)
├── geometry/
│   ├── mesh_skin_hi.bin     # Roh-Mesh (quantisiert, int16 mit Scale)
│   ├── mesh_skin_lod0..3.bin
│   ├── hair_cap.bin
│   ├── hair_cards.bin       # + Atlas-Verweise
│   ├── hair_strands.bin     # Kurven (L3)
│   ├── scalp_uv.bin
│   └── tsdf_meta.json       # Voxelgröße, Bounding-Box, Parameter der Stufen
├── rig/
│   ├── base_head.bin        # registrierter Basiskopf (Topologie fest)
│   ├── skeleton.json        # Hierarchie, Bind-Matrizen
│   ├── weights.bin          # Skin-Gewichte (uint8 quantisiert, max 4 Einflüsse)
│   ├── blendshapes/         # 52 Deltas + Korrektur-Shapes (int16 + Scale)
│   ├── blendshape_calib.json# Neutral/Range aus der Kalibrierung
│   └── morph_names.json     # ARKit-Namen in fester Reihenfolge ⇒ Export-Kompatibilität
├── textures/
│   ├── basecolor_4k.png · normal_4k.png · roughness_4k.png · ao_4k.png
│   ├── displacement_4k.exr  (oder .png16)
│   ├── sss_4k.png · hair_atlas.png · hair_alpha.png
│   └── uv_meta.json         # UV-Layout-Hash, Kanal-Konvention, Farbräume
├── animation/
│   ├── clips/<name>.fsmc
│   └── library.json
├── qa/
│   ├── report.json          # Kennzahlen, Ampeln, Tipps
│   └── thumb.jpg · preview_360.mp4 (optional)
├── provenance/
│   ├── c2pa_manifest.c2pa   # signierte Herkunft (optional)
│   └── third_party.json     # Modell-Hashes, Versionen
└── license.json             # Tier, Entitlement-Hash (kein Personenbezug!)
```

**Designentscheidungen:**
- Binärdaten **quantisiert** (int16 + Skalierungsfaktor im JSON) ⇒ 40–60 % kleiner, deterministisch,
  plattformunabhängig lesbar (Endianness little, dokumentiert).
- Alles ist **versioniert** (`schemaVersion`), mit Migrationsfunktion je Version.
- Das Format wird **offen dokumentiert** (Public Spec auf der Landingpage) – das ist ein Vertrauens- und
  Verkaufsargument ("deine Daten gehören dir, du kannst sie jederzeit selbst lesen").
- Verschlüsselung: Der Container ist im Tresor **AES-256-GCM-verschlüsselt** (Chunk-weise, 1 MiB Blöcke,
  12-Byte-Nonce + 16-Byte-Tag je Chunk). Beim **Nutzer-Export über SAF** wird wahlweise (a) entschlüsselt als
  normales ZIP oder (b) als verschlüsseltes `.fsvault` geschrieben.

**Platzbedarf pro Avatar (Richtwerte):**

| Inhalt | Quick | Standard | Pro |
|---|---|---|---|
| Quellbilder (optional) | 60 MB | 180 MB | 700 MB |
| Geometrie (alle LODs) | 25 MB | 70 MB | 260 MB |
| Texturen 4K (6 Maps) | – | 90 MB | 350 MB (8K) |
| Blendshapes (52 × 12 k Verts) | 18 MB | 18 MB | 18 MB |
| Haar (L2/L3) | 5 MB | 25 MB | 80 MB |
| **Summe (mit Bildern)** | **≈ 110 MB** | **≈ 385 MB** | **≈ 1,4 GB** |
| **Summe (ohne Quellbilder)** | **≈ 50 MB** | **≈ 205 MB** | **≈ 710 MB** |

Standardmäßig werden die Quellbilder nach erfolgreichem Scan **angeboten zu löschen** (Default: behalten,
mit Hinweis und Auto-Lösch-Option nach 30 Tagen) – das ist die wichtigste Stellschraube für Geräte mit
wenig Speicher.

## 3. Datenbank (Room)

Tabellen: `ProjectEntity` (uuid, name, createdAt, updatedAt, tierUsed, qualityJson, favorite, thumbnailPath,
sizeBytes, schemaVersion) · `ClipEntity` (uuid, projectId, name, fps, frameCount, durationMs, path, createdAt)
· `JobEntity` (id, type, state, progress, stage, checkpointPath, startedAt, updatedAt, errorMessage)
· `EntitlementEntity` (sku, tier, purchasedAt, txHash, chain, amount, currency, signature, deviceBinding,
lastVerifiedAt) · `SettingsEntity` (key/value) · `EventEntity` (lokales Audit-Log: "Scan erstellt",
"Daten gelöscht", "Export" – **nur lokal**, für den Nutzer einsehbar, nie übertragen).

Keine Personennamen-Klarnamen-Pflicht: "Name" ist frei wählbar, Standard "Mein Scan 1".

## 4. Verschlüsselung & Tresor

| Element | Verfahren |
|---|---|
| Datenschlüssel | AES-256-GCM, 256-bit, im **Android Keystore** (StrongBox falls vorhanden) |
| Schlüsselableitung | Keystore-Key ist nicht exportierbar; Datenkey wird mit ihm per AES-GCM gewrappt und in `noBackupFilesDir` gespeichert |
| Datei-Chunks | 1 MiB, Nonce = 12 Byte (Random je Chunk, im Chunk-Header), Tag 16 Byte |
| Zusätzliche Absicherung | Optional: Tresor-PIN (Argon2id → zusätzlicher Key-Wrap). Biometrie nur als **Bequemlichkeits-Freigabe** (BiometricPrompt + Keystore-`setUserAuthenticationRequired`) |
| Panic-Wipe | Einstellbare Aktion (z. B. 5× Tippen auf das Logo im Einstellungs-Screen) ⇒ löscht Datenschlüssel + Projekte |
| Screenshot-Schutz | `FLAG_SECURE` auf allen Screens mit Gesichtsdaten |

## 5. Hintergrundverarbeitung, Checkpoints, Wiederaufnahme

- **Vordergrund-Service** (`foregroundServiceType` passend deklariert) mit permanenter Benachrichtigung:
  "Gesicht wird berechnet · Stufe 4 von 11 · noch ca. 1:20" + Aktion "Abbrechen" + Aktion "Im Hintergrund
  weiter" (dann minimiert).
- **Partial WakeLock** nur während einer Stufe, danach freigegeben.
- **Checkpoint je Stufe:** `jobs/<jobId>/stage<N>.done` + Nutzdaten in `cacheDir`. Neustart ⇒ letzte
  abgeschlossene Stufe wird übersprungen. Ein Job überlebt Prozess-Tod, App-Update und Neustart.
- **Thermik/Akku:** siehe `02`. Zusätzlich: Bei `THERMAL_STATUS_SEVERE` wird der Job **pausiert** und der
  Nutzer gefragt ("Weiter, sobald das Handy abgekühlt ist? – wir machen genau hier weiter").
- **Zeitabschätzung:** Fortschritt pro Stufe aus einem gerätespezifischen Zeitmodell, nach jedem Scan
  nachkalibriert (gleitender Median) ⇒ die Prozentanzeige lügt nicht.

## 6. Modell- & Asset-Management (APK-Größe)

| Asset | Größe | Lieferung |
|---|---|---|
| `face_landmarker.task` | ≈ 4 MB | Install-Time Asset Pack |
| `pose_landmarker_*.task` | ≈ 6–15 MB | Install-Time |
| `hand_landmarker.task` | ≈ 8 MB | On-Demand (nur bei Körper-Modus) |
| `hair_segmenter.tflite` | ≈ 0,8 MB | Install-Time |
| Eigenes 3DMM (Basis + PCA-Matrizen, fp16) | ≈ 12–25 MB | Install-Time |
| Basiskopf/Rig/Templates | ≈ 6 MB | Install-Time |
| Haar-Prior-Modelle (L3) | ≈ 30 MB | On-Demand |
| App-Code + UI + Renderer | ≈ 45 MB | APK/AAB |
| **Installationsgröße (Ziel)** | **≤ 350 MB** | Play-Feature-Delivery |

- Alle Modelle mit **SHA-256-Prüfsumme**, die im Code verankert ist; Manipulation ⇒ Start verweigert mit
  klarer Meldung.
- **Kein Nachladen zur Laufzeit** im Kernpfad (Offline-First-Regel 2). Ausnahme: der optionale
  Modell-Update-Kanal (einzustellende Option "Modelle aktualisieren", aus, Default **aus**).

## 7. Backup, Umzug, Löschung (DSGVO-Bausteine)

| Funktion | Verhalten |
|---|---|
| **Projekt-Export** | Ein Projekt als `.fscan` (wahlweise entschlüsseltes ZIP) über SAF – vollständig, inkl. Quellbilder (Schalter) |
| **Alle Daten exportieren** | ZIP aller Projekte + Einstellungen + Lizenzen (ein Klick, Fortschrittsanzeige) |
| **Projekt löschen** | Sofort, mit Rückfrage ("Endgültig löschen? Das kann nicht rückgängig gemacht werden."), Löschung inkl. Cache und Thumbnails, Protokolleintrag |
| **Alles löschen** | Zwei-Faktor-Bestätigung (Tresor-PIN oder "ALLES LÖSCHEN" eintippen), danach Zeroize des Schlüssels |
| **Geräteumzug** | Export-ZIP auf neues Gerät (SAF/Datei/Kabel), Import über "Projekt öffnen". Lizenzen: "Kauf wiederherstellen" über Tx-Hash + unsere Signatur |
| **Aufbewahrung** | Keine serverseitige Speicherung existiert – folglich keine Löschfristen auf unserer Seite |
| **Audit-Log** | Der Nutzer sieht in "Einstellungen → Datenschutz → Verlauf", wann was gescannt, exportiert und gelöscht wurde. Alles lokal. |

## 8. Was das Gerät verlässt (Transparenz-Monitor)

| Anlass | Ziel | Daten | Default |
|---|---|---|---|
| Kauf/Verifikation | Solana-RPC / BTC-ESPLORA / ETH-RPC (per Nutzer gewählt, Multiple-Endpunkte) | öffentliche Adresse, Betrag, Referenz-Key, Tx-Hash | nur auf Nutzeraktion |
| Kursabfrage (optional) | CoinGecko/Exchange | keine Nutzerdaten, nur "SOL/EUR" | aus |
| Crash-/Diagnose | entfällt (lokal) – wenn aktiviert: nur anonyme, selbst gehostete Endpunkte ohne Identifier | Stacktrace, App-Version, Geräteklasse | **aus** |
| Landingpage-Links | Browser (kein WebView) | – | – |
| Update-Prüfung | Play Store (Google) | Standard | System |

Der Transparenz-Monitor listet genau diese Zeilen mit Ampel-Status und Letzt-Nutzung-Zeitpunkt auf. Er ist
das stärkste Verkaufsargument in der Datenschutz-Sektion der Landingpage.

## 9. Determinismus & Reproduzierbarkeit

- Alle Zufallsquellen (Strand-Jitter, PatchMatch-Initialisierung) nutzen einen **im Projekt gespeicherten Seed**.
- Pipeline-Version (`pipelineVersion`) und Modell-Hashes liegen im Manifest ⇒ ein Ergebnis ist auch in
  zwei Jahren reproduzierbar oder gezielt mit einer neuen Version nachrechenbar ("Mit der neuen Version
  neu berechnen" – aus denselben Quelldaten, wenn behalten).
