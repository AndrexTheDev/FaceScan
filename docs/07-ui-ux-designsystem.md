# 07 – UI/UX & Designsystem (Jamaika + Day-Mode, DE/EN)

Stand: 2026-11-15 · Modul `:design` (Compose, Material 3 als Basis, eigene Tokens)

---

## 1. Zehn UX-Grundsätze (verbindlich)

1. **Ein Ziel pro Bildschirm.** Kein Screen fragt zwei Dinge gleichzeitig.
2. **Der Hauptweg ist ein Knopf.** "Scannen" ist immer die größte, goldene Aktion.
3. **Keine Fachbegriffe ohne Erklärung.** Jedes Fachwort hat ein „ⓘ Was ist das?" – eine Zeile, Laiensprache.
4. **Fehler sind Anweisungen, keine Meldungen.** Nicht "Tracking verloren", sondern "Ich sehe dein Gesicht
   nicht mehr – bitte langsam zurück in den Rahmen."
5. **Immer ein Ausweg.** Zurück, Abbrechen und "Später" sind überall erreichbar (auch während der Berechnung).
6. **Fortschritt ist sichtbar und ehrlich.** Stufenname + Prozent + Restzeit + "Was passiert gerade?".
7. **Erfolg wird gefeiert.** Nach dem Scan: kurze Animation, Konfetti in Jamaika-Farben, sofortiges 3D-Modell.
8. **Nie blockieren.** Alles ist unterbrechbar, alles ist fortsetzbar, nichts verliert Arbeit.
9. **Farbe bedeutet nie allein Information.** Jede Ampel hat zusätzlich ein Symbol und einen Satz.
10. **Erklären statt bevormunden.** Wir sagen, *warum* wir etwas brauchen ("Gutes Licht = scharfe Details").

## 2. Farb-Tokens

### 2.1 Markenfarben (Jamaika-Flagge)

| Token | Hex | Rolle |
|---|---|---|
| `jamaica.black` | `#000000` | Basis Night, Typografie auf Grün/Gold |
| `jamaica.green` | `#009B3A` | Primärfarbe |
| `jamaica.gold` | `#FFD100` | Akzent, Erfolg, Fortschritt |

### 2.2 Night-Mode „Rasta Night" (Standard)

| Token | Hex | Verwendung |
|---|---|---|
| `bg` | `#000000` | Hintergrund |
| `surface.1` | `#0E0E0E` | Karten, Sheets |
| `surface.2` | `#1A1A1A` | Eingaben, Chips |
| `surface.3` | `#2A2A2A` | Kanten, Trenner |
| `text.primary` | `#F5F5F5` | 15,96:1 auf `surface.2` ✔ AAA |
| `text.secondary` | `#A8A8A8` | 7,0:1 ✔ AA |
| `brand.green` | `#00B34A` | Auf dunklem Grund besser lesbar als das Flaggen-Grün (6,94:1 auf `#0E0E0E` ✔ AA) |
| `brand.green.strong` | `#009B3A` | Füllungen, Logos, Flaggenakzent (5,75:1 gegen Schwarz ✔ AA) |
| `brand.gold` | `#FFD100` | Akzent, Fortschritt (14,37:1 gegen Schwarz ✔ AAA) |
| `onBrand` | `#000000` | **Text auf Grün und Gold immer schwarz** (Grün 5,75:1, Gold 14,37:1) |
| `ok` | `#00B34A` | |
| `warn` | `#FFC400` | 12,09:1 ✔ |
| `error` | `#FF6B6B` | Rot ist keine Flaggenfarbe – nur für Fehler, wegen Eindeutigkeit erlaubt |
| `scrim` | `#000000` @ 72 % | |

> **Wichtig:** Weiße Schrift auf `#009B3A` erreicht nur 3,65:1 – das besteht AA für Fließtext **nicht**.
> Deshalb: **Buttons grün oder gold mit schwarzer Schrift.** Das ist nicht nur barrierefrei, es ist auch der
> markanteste Teil des Designs.

### 2.3 Day-Mode „Sunrise"

| Token | Hex | Verwendung | Kontrast |
|---|---|---|---|
| `bg` | `#FFFFFF` | Hintergrund | – |
| `surface.1` | `#F5F5F2` | Karten (warm gebrochenes Weiß, damit es nicht steril wirkt) | – |
| `surface.2` | `#E9E9E4` | Eingaben | – |
| `text.primary` | `#101010` | 19,0:1 ✔ AAA |
| `text.secondary` | `#5A5A55` | ≈ 7:1 ✔ AA |
| `brand.green` | `#007A2E` | Primär (dunkleres Flaggen-Grün) | 5,49:1 auf Weiß ✔ AA |
| `brand.gold.fill` | `#FFD100` | **nur als Fläche/Icon mit schwarzer Schrift** | Gold als Text auf Weiß = 1,46:1 ✘ |
| `brand.gold.text` | `#8A6A00` | Gold **als Text/Link** | 5,07:1 ✔ AA |
| `onBrand` | `#FFFFFF` | Text auf `#007A2E` (5,49:1 ✔ AA); Text auf Gold-Fläche: `#101010` |
| `error` | `#B3261E` | 6,54:1 ✔ AA |

**Umschaltung:** Automatisch nach System (Android 12+ dynamisch), manuell erzwungen möglich
(„Nacht / Tag / System"). Alle Screens müssen in beiden Modi geprüft werden (Screenshot-Tests).

### 2.4 Semantische Regeln

- Grün = „weiter / gut / aktiv". Gold = „Aufmerksamkeit / Erfolg / Fortschritt". Rot = „Fehler / Abbrechen".
- Das **Flaggen-Grün bleibt immer Grün**, auch im Day-Mode – nur die Helligkeit wird angepasst.
- Gold wird im Day-Mode nie als Fließtext verwendet (Kontrast 1,46:1) – nur als Füllung mit schwarzer
  Schrift oder als dunkle Textvariante `#8A6A00`.
- Fokus-Ringe: 2 dp Gold auf dunklem, `#007A2E` auf hellem Grund (sichtbar, nicht nur Farbwechsel).

## 3. Typografie, Maße, Bewegung

| Element | Wert |
|---|---|
| Schrift | **Roboto Flex** (variabel) für UI, **Inter** Fallback; Zahlen tabellarisch |
| Display / H1 | 34 sp / 28 sp, Gewicht 700 |
| H2 (Screen-Titel) | 24 sp / 20 sp, 600 |
| Body | 16 sp (min. 14 sp), Zeilenhöhe 1,45 |
| Button | 16 sp, 600, Groß-/Kleinschreibung wie Satz (kein Caps-Only) |
| Touch-Target | **min. 56 dp** (Material fordert 48 – wir nehmen mehr, weil die App im Stehen bedient wird) |
| Raster | 8-dp-Raster, Rand 20 dp |
| Radien | Buttons 16 dp, Karten 20 dp, Sheets 28 dp (oben), Chips 12 dp |
| Elevation | Night: keine Schatten, nur 1-dp-Ränder (Schatten sind auf Schwarz unsichtbar). Day: Tonal-Elevation |
| Bewegung | 220 ms Standard, 400 ms für Screen-Wechsel, `FastOutSlowIn`. Respektiert `animatorDurationScale=0` |
| Haptik | Tick bei akzeptiertem Frame, doppelter Tick bei Stufenabschluss, langer Tick bei Fehler |

**Einsteiger-Hilfe:** Jeder Fachbegriff hat ein „ⓘ"-Icon. Tippen ⇒ Bottom-Sheet mit **einem Satz Laiendeutsch
+ einem Beispiel + einem Bild**. Beispiele:
- Mesh → „Das ist dein 3D-Modell: ein Netz aus vielen kleinen Dreiecken, wie ein engmaschiges Netz über deinem Gesicht."
- Blendshape → „Eine gespeicherte Mimik, z. B. ‚lächeln'. Mehrere davon gemischt ergeben jedes Gesicht."
- Displacement → „Eine Karte, die dem 3D-Modell sagt, wo es Beulen und Falten hat – wie eine Prägung in Papier."
- UV → „Die Verpackung deines Modells: das 3D-Modell wird flachgelegt, damit man es bemalen kann."
- Rig → „Das unsichtbare Skelett, an dem man den Kopf bewegen kann – wie eine Marionette."

## 4. Komponenten (Auszug)

| Komponente | Beschreibung |
|---|---|
| `PrimaryButton` | Grün, schwarze Schrift, 56 dp hoch, volle Breite, Ladezustand integriert |
| `GoldActionButton` | Für „Scannen" und „Exportieren" – Gold, schwarze Schrift, 64 dp, mit weichem Glow |
| `DangerButton` | Rot umrandet, transparent gefüllt („Löschen", „Abbrechen") |
| `QualityLight` | Ampel: Kreis + Symbol (✓ / ! / ✕) + kurzer Satz, nie nur Farbe |
| `StageProgress` | Stufenname + Prozentbalken (Gold) + Restzeit + „Was passiert hier?"-Link |
| `CaptureOverlay` | Head-Silhouette, Zielring, Fortschrittsbogen (Gold), Ampel unten, Abbrechen oben |
| `InfoTip` | „ⓘ Was ist das?" – Bottom-Sheet, ein Satz, ein Bild |
| `CompareSlider` | Foto ↔ Render, Griff in Gold, Beschriftung „Vorher/ Nachher" |
| `FormatCard` | Zielsoftware-Icon + Name + ein Satz Empfehlung + Dateiendung-Badge |
| `AvatarViewer` | 3D-Ansicht mit Gestensteuerung, Beleuchtungs-Presets, Ansichtsmodi |
| `EmptyState` | Illustration (Jamaika-Farben) + ein Satz + ein Knopf – nie eine leere Liste |

## 5. Screens & Flows

### 5.1 Erster Start (Onboarding, 5 Screens, überspringbar)

```
[1] Willkommen            „Scanne dich in 3D – in einer Minute."
    Illustration (Kopf + Handy, Jamaika-Farben)      [Los geht's]  [Ich habe schon ein Konto? Nein – brauchst du nicht.]
[2] Was wir speichern     „Alles bleibt auf deinem Handy. Nichts geht ins Internet."
    3 Punkte mit Symbolen                            [Verstanden]
[3] Kamera erlauben       In-App-Disclosure (Play-Pflicht!) + Systemdialog
    „FaceScan braucht die Kamera, um dein Gesicht zu scannen. Die Bilder verlassen dein Handy nicht.
     Wir erstellen keine biometrische Erkennung und geben nichts weiter."   [Kamera erlauben]
[4] Kurzanleitung         12-sekündiges, stumm abspielbares Video (lokal) + 3 Piktogramme
[5] Übung (optional)      „Erst mit der Übungspuppe testen?"  [Üben] [Direkt scannen]
```
> Screen [3] ist **Play-Store-relevant**: Die Erklärung muss *in der App*, *vor* der Berechtigung und
> *alleinstehend* erscheinen (nicht nur in der Datenschutzerklärung). Siehe `09`.

### 5.2 Home

```
┌─────────────────────────────────────────────┐
│  ☰   FaceScan                        ⓘ  ☾/☀ │
├─────────────────────────────────────────────┤
│                                             │
│         [ 3D-Vorschau des letzten Modells ] │
│              (drehbar, Gold-Ring)           │
│                                             │
│   Mein Kopf · 14.11.2026 · 4,2 MB           │
│   ●●●●● Qualität: sehr gut                  │
│                                             │
│   [ Animieren ]  [ Exportieren ]  [ Teilen ]│
├─────────────────────────────────────────────┤
│  Meine Modelle                     [Alle ▸] │
│  ┌──────┐ ┌──────┐ ┌──────┐                 │
│  │ Kopf │ │ Kopf │ │  +   │                 │
│  │  1   │ │  2   │ │ Neu  │                 │
│  └──────┘ └──────┘ └──────┘                 │
├─────────────────────────────────────────────┤
│        ███████  NEU SCANNEN  ███████        │  ← GoldActionButton
└─────────────────────────────────────────────┘
```

### 5.3 Scan-Ablauf

```
[Modus wählen]   ⚡ Schnell (20 s)  ⭐ Standard (60 s)  👑 Profi (3 min)
   „Schnell: gut für Social Media.  Standard: empfohlen.  Profi: für 3D-Profis."
                [ Weiter ]
        ↓
[Vorbereitung]  Checkliste mit Live-Häkchen:
   ☑ Helles, gleichmäßiges Licht (kein Gegenlicht)   ☑ Brille ab   ☑ Haare offen/ wie gewünscht
   ☑ Ca. 50 cm Abstand   ☑ Keine Kopfbedeckung       ☐ Hinterkopf: Helfer oder Spiegel?
                [ Kamera starten ]
        ↓
[Aufnahme]      Overlay + Ampel + Sprachführung + Fortschrittsbogen
                „Langsam nach links drehen … genau … jetzt zurück zur Mitte …"
                [ Abbrechen ]  (immer sichtbar)
        ↓
[Verarbeitung]  „Wir rechnen" – 11 Stufen, Prozent, Restzeit, „Was passiert hier?"
                „Du kannst die App verlassen – wir machen weiter."  [ Im Hintergrund weiter ]
        ↓
[Ergebnis]      3D-Modell + Qualitätsampeln + Vergleichsslider
                [ Animieren ] [ Exportieren ] [ Nochmal scannen mit Tipps ] [ Als Vorlage übernehmen ]
```

### 5.4 Export-Assistent (das Herzstück für Einsteiger)

```
[Wofür willst du dein Modell nutzen?]
   🟦 Blender         🟩 Unreal/Unity        🟪 3D-Druck
   🟧 Web/Godot       🟨 VTuber/VRM          🟫 Apple/AR (USDZ)
   ⬜ Etwas anderes (Profi-Modus)
        ↓  (Beispiel Blender)
[Empfehlung]
   „FBX – damit kann Blender dein Modell, dein Skelett und deine Mimik in einem Schritt übernehmen.
    Dazu ein Ordner mit den Texturen (Farbe, Details, Licht)."
   Einheit: Meter · Achsen: Z-oben · Details: 4K · Mimik: 52 Formen
   [ Ändern ]                            [ Exportieren ]
        ↓
[Speicherort]   „Wohin damit?" → SAF-Ordnerauswahl, Standard `Dokumente/FaceScan/Mein Kopf/`
        ↓
[Fertig]  ✅ „Fertig! 1 FBX-Datei + 6 Texturen."
          [ Dateien anzeigen ]  [ Teilen ]  [ Noch ein Format ]
```

### 5.5 Animieren

```
[Modus]   😊 Nur Gesicht     🧍 Gesicht + Körper
   „Nur Gesicht: dein Avatar spricht und lächelt.  Ganzkörper: du bewegst dich, der Avatar folgt."
        ↓
[Kalibrierung]  „Bitte 3 Sekunden entspannt geradeaus schauen." (Ring füllt sich)
                „Jetzt bitte maximal lächeln … und entspannen." (4 kurze Schritte, 20 s)
        ↓
[Live]    Avatar links, dein Kamerabild rechts (oder Avatar groß + kleines Kamerabild)
          ● Aufnahme · Presets (Freude, Wut, …) · Regler (Intensität, Glättung) · Latenz-Anzeige
        ↓
[Clip]    Vorschau, Trimmen, „Als … exportieren" (BVH/ABC/FBX/GLB/USD/CSV)
```

## 6. Copy-Glossar DE ↔ EN (Begriffe, die der Nutzer sieht)

| Intern | DE (Nutzer) | EN (user-facing) |
|---|---|---|
| Scan | Scan | scan |
| Mesh | 3D-Modell | 3D model |
| Retopology | Saubere Form (für Animation) | clean shape (for animation) |
| Blendshape | Mimik-Form | expression shape |
| Rig | Skelett | skeleton |
| Texture map | Oberflächenbild | texture map |
| Albedo | Farbe | color |
| Normal map | Detail-Relief | detail relief |
| Displacement | Form-Details | shape detail |
| UV map | Verpackung (flachgelegt) | unwrapped layout |
| Export | Sichern / Datei erstellen | save / create file |
| Mocap | Bewegungsaufnahme | motion capture |
| TSDF/Voxel | (nie gezeigt) | (never shown) |
| Calibration | Abgleich | calibration |
| Quality report | Qualitätsbericht | quality report |
| Watertight | geschlossen (druckbar) | watertight (printable) |
| Strands | Haar-Strähnen | hair strands |
| Cards | Haar-Flächen | hair cards |
| Freemium tier | Starter / Creator / Studio | Starter / Creator / Studio |

**Tonalität DE:** Du-Form, aktiv, kurz, nie passiv-aggressiv („Ups, zu dunkel – geh ans Fenster." statt
„Beleuchtung unzureichend"). **Tonalität EN:** „you", gleicher Tonfall, keine wörtlichen Übersetzungen
(Sinn vor Wortlaut).

## 7. Fehler-, Leer- und Ladezustände

| Zustand | Verhalten |
|---|---|
| Noch kein Modell | Illustration + „Noch kein Modell – scanne dich in einer Minute." + Gold-Button |
| Kamera verweigert | Erklärung + „Erneut erlauben" + „Ohne Kamera geht es leider nicht" + Link zu Anleitung |
| Zu wenig Licht | Overlay-Hinweis + Taschenlampe-anbieten (Frontkamera: Bildschirm-Helligkeit erhöhen + weißes Overlay) |
| Verarbeitung fehlgeschlagen | „Das hat nicht geklappt." + **konkreter Grund** + „Erneut versuchen" + „Bericht speichern" (lokal, für Support) |
| Zu wenig Speicher | „Du brauchst 2,5 GB frei. Aktuell: 1,8 GB." + „Aufräumen" (führt zu Projektverwaltung) |
| Heiß | „Kurz abkühlen lassen – wir machen genau hier weiter." + [ Weiter, wenn kühler ] |
| Export schlägt fehl | „Die Datei konnte nicht geschrieben werden." + Ausweichvorschlag („Als GLB speichern?") |
| Ladezustand > 5 s | Immer Text, was gerade passiert; nie nur ein Kreisel |

## 8. Barrierefreiheit (Ziel: WCAG 2.2 AA)

- Kontrast: Alle Paare in 2.2/2.3 geprüft (Werte dokumentiert). Große Schrift (≥ 24 sp) mind. 3:1,
  Fließtext mind. 4,5:1.
- Touch-Ziele ≥ 56 dp, Abstände ≥ 8 dp.
- TalkBack: Jedes Element mit Inhaltsbeschreibung; der **Scan-Fortschritt wird periodisch angesagt**
  (alle 20 %), die Ampel als Text, nicht als Farbe.
- Schriftgröße: bis 200 % ohne Layout-Bruch (Compose `dp` → `sp`-Skalierung, kein Fix-Layout).
- Reduzierte Bewegung: `Transitions` respektieren die Systemeinstellung; Konfetti/Auto-Rotate aus.
- Keine zeitbegrenzten Aktionen (außer der Aufnahme, die pausierbar ist).
- Einhand-Bedienung: Hauptaktionen im unteren Bildschirmdrittel.
- Farbenblindheit: Rot/Grün-Ampeln immer mit Symbol + Text; kein reiner Farbcode bei Format-Auswahl.

## 9. Internationalisierung

- `res/values-de` (Standard), `res/values-en`. Alle Strings in XML, keine hartcodierten Texte.
- **In-App-Sprachumschaltung** (Android 13+ `LocaleManager`, davor `AppCompatDelegate`), Auswahl im
  Onboarding und in den Einstellungen; Fallback: Systemsprache.
- Pseudo-Locale-Tests (`en-XA`, `ar-XB`) vor jedem Release gegen Layout-Brüche.
- Datums-/Zahlenformate über `java.text`/ICU; Dateinamen immer ASCII-sicher (Umlaute → ae/oe/ue, optional).
- Zwei Lektorats-Durchgänge: DE (Muttersprache) und EN (Muttersprache). Keine reinen
  Maschinenübersetzungen in der UI.
- Währungen: Preise in EUR angegeben, Krypto-Betrag daneben („≈ 0,214 SOL").

## 10. Einstellungs-Karte

```
Mein Konto        · Lizenzen & Quittungen · Kauf wiederherstellen · Pro freischalten
Scannen           · Modus (Schnell/Standard/Profi) · Qualität erzwingen · Quellbilder behalten
                  · Hinterkopf-Assistent · Sprachführung an/aus · Ton an/aus
Ansicht           · Night / Day / System · Auto-Rotate · Beleuchtungs-Preset
Animation         · Glättung · Intensität · Mikrobewegung · Blick-Korrektur · Körper-Kalibrierung
Export            · Standard-Ziel · Einheit · Achsen · Texturformat · Texturgröße · Kanal-Packing
                  · Profi-Modus (alle Formate) · C2PA-Herkunft einbetten
Datenschutz       · Tresor-PIN · Biometrie · Screenshot-Schutz · Panic-Wipe · Daten exportieren
                  · Alles löschen · Verlauf (Audit-Log) · **Transparenz-Monitor**
Über              · Version · Modell-Versionen · Danksagungen (Lizenzen) · Support · Impressum
```

## 11. Anti-Patterns (was wir niemals tun)

- Keine Banner-Werbung, keine Tracking-SDKs, keine „Rate uns"-Popup-Kaskaden.
- Keine Dark Patterns beim Kauf (kein „Nein danke, ich will schlechte Ergebnisse").
- Keine Popups während der Aufnahme.
- Kein Konto-Zwang, keine E-Mail-Abfrage vor dem ersten Scan.
- Keine „Überraschungs"-Uploads (auch nicht „zur Qualitätsverbesserung").
- Keine irreversiblen Aktionen ohne Rückfrage (Löschen immer mit Bestätigung).
- Keine stillen Formatverluste beim Export (immer Warnung, wenn etwas nicht mitkommt, z. B. Haar-Strähnen
  in glTF).
