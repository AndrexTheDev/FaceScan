# 10 – Test, QA, Performance

Stand: 2026-11-15 · Grundsatz: **Ohne Ground Truth keine Qualitätssteuerung.**

---

## 1. Testpyramide

| Ebene | Umfang | Werkzeuge | Frequenz |
|---|---|---|---|
| **Unit (C++)** | Geometrie, Optimierung, Writer, Filter, Mathematik | GoogleTest, ASan/UBSan | jeder Commit |
| **Unit (Kotlin)** | Domain, Licensing, Container-IO, Format-Code | JUnit 5, Turbine, Truth | jeder Commit |
| **Golden-File (Export)** | `SceneIR` → Writer → unabhängiger Reader → Vergleich | Python (`pygltflib`, `trimesh`, `Open3D`, `usd-core`, `bpy`) | jeder Commit (Nightly für große Sets) |
| **Algorithmik-Regression** | Pipeline auf dem **synthetischen Datensatz** mit bekannter GT | eigener Harness (CLI-Build für Desktop) | jede Nacht |
| **Instrumentation** | Kamera, Permissions, Service, Thermik, SAF | AndroidX Test, Hilt-Testing | jeder Release-Kandidat |
| **UI** | Compose-Semantik, Screenshot-Tests (Night/Day, DE/EN) | Compose UI Test, Roborazzi | jeder Release-Kandidat |
| **Performance** | Scan-Dauer je Stufe, RAM, Akku, Thermik, fps | Macrobenchmark, eigener Profiler-Hook | wöchentlich |
| **Gerätematrix (manuell)** | Echte Scans auf 8–12 Geräten | Testprotokoll | je Meilenstein |
| **Usability** | Erstnutzer:innen, Aufgabenbezogen | Testleitfaden, Videoaufzeichnung (mit Einwilligung) | M3, M5, M6 |
| **Fuzzing** | Writer/Importer gegen kaputte Daten | libFuzzer auf den C++-Parsern | wöchentlich |

## 2. Ground Truth – drei unabhängige Referenzen

| Referenz | Aufbau | Nutzen | Aufwand |
|---|---|---|---|
| **Synthetische Köpfe** | 10 CG-Köpfe (selbst erstellt/lizenziert) mit **bekannter Geometrie**, gerendert aus 48 exakt bekannten Kameraposen, mit Haar-Varianten, 3 Hauttönen, 2 Altersstufen | Exakte Fehlermessung (Chamfer-Distanz in mm), Parameter-Tuning ohne Rauschen | mittel (einmalig) |
| **Studio-Referenzscans** | 20 Personen, Referenz-Scanner (Dienstleister oder gemietetes System) | Echte Fehlerverteilung inkl. Haar, Haut, Bewegung | 2–5 k€ |
| **Blindvergleich (Wahrnehmung)** | Paare „Foto ↔ Render" werden Bekannten der Testperson vorgelegt: „Ist das dieselbe Person?" | Das einzige Maß, das zählt, wenn es um Ähnlichkeit geht | gering |

**Metriken (Zielwerte für v1, Mittelklasse, Standard-Modus):**

| Metrik | Messung gegen | Ziel |
|---|---|---|
| Chamfer-Distanz (Gesichtshaut) | Synthetische GT | ≤ 0,8 mm (Mittelwert) |
| Landmark-Reprojektionsfehler | GT-Posen | ≤ 1,5 px |
| Silhouetten-IoU Haar | GT-Masken | ≥ 0,85 |
| Normalenfehler | GT-Normalen | ≤ 8° (Mittelwert) |
| Farbe (ΔE) | GT-Albedo | ≤ 5 |
| Wiedererkennung (Blindtest) | menschlich | ≥ 80 % „eindeutig erkannt" |
| Scan-Dauer | – | ≤ 180 s (Standard, Mittelklasse) |
| Spitzen-RAM | – | ≤ 1,6 GB |
| Abstürze pro Scan | – | 0 |

## 3. Gerätematrix (Pflicht-Set)

| Klasse | Gerätebeispiele | Was getestet wird |
|---|---|---|
| Low | Galaxy A15/A55, Moto G (4 GB), Redmi Note 13 | Reduced-Profile, Speicherdruck, Abbruch/Wiederaufnahme |
| Mid | Pixel 8a/9, Galaxy S24 FE, Nothing Phone | Standard-Modus, Zeitbudget, Thermik |
| High | Pixel 9 Pro, Galaxy S25 Ultra, Xiaomi 15 Ultra | Pro-Modus, 8K, Haar-Stufe 3 |
| Exoten | Gerät ohne Vulkan-Compute, Gerät ohne NNAPI-Delegate, Gerät mit ToF | Fallback-Pfade |
| Alt | Android 10/11 (minSdk) | API-Kompatibilität, Camera2-Fallbacks |

Zusätzlich: **Firebase Test Lab** (oder alternatives Device-Farm) für automatisierte Smoke-Tests – **nur mit
synthetischen/generischen Testdaten, niemals mit echten Gesichtsbildern** (Datenschutz!).

## 4. Performance-Messung (eingebaut)

- Jede Pipeline-Stufe meldet `start`, `end`, `peakMemory`, `thermalStatus`, `batteryPercent`.
- Diese Telemetrie ist **lokal** und wird im Qualitätsbericht (Profi-Ansicht) angezeigt; sie wird nur mit
  Opt-in (anonym, ohne Bilder) exportiert.
- Wöchentlicher Benchmark-Lauf auf 3 Referenzgeräten mit festem Bildersatz ⇒ Trendkurve
  (Regression > 10 % ⇒ Build blockiert).

## 5. Usability-Testprotokoll (M3, M5, M6)

| Schritt | Inhalt |
|---|---|
| Teilnehmende | 12 Personen: 6 ohne 3D-Erfahrung, 3 Creator, 3 Profis; 6 Haar-Typen; verschiedene Hauttöne |
| Aufgaben | (1) Ersten Scan erstellen, (2) Ergebnis bewerten, (3) Modell animieren, (4) für Blender exportieren, (5) Kauf simulieren (Testnet) |
| Messung | Zeit je Aufgabe, Abbrüche, Hilferufe, „Wo hast du gezögert?", SUS-Fragebogen (Ziel ≥ 80) |
| Nachgespräch | 5 Fragen: Was war verwirrend? Welche Wörter waren fremd? Was hat gefehlt? Was war überflüssig? Würdest du zahlen? |
| Auswertung | Jeder Fund wird als Issue mit Priorität (Blocker/Major/Minor) angelegt; Blocker vor dem nächsten Meilenstein behoben |

## 6. Release-Checkliste (verbindlich, je Release)

**Funktion**
- [ ] Flugmodus-Test: Scan → Animieren → Export vollständig ohne Netz
- [ ] Kauf-Flow auf Solana Devnet + manuellem Pfad durchgespielt
- [ ] Alle Formate geschrieben und mit Fremdsoftware geöffnet (Protokoll + Screenshots, `05` Kapitel 8)
- [ ] Warnungen bei Formatverlusten erscheinen korrekt (z. B. Haar-Strähnen in glTF)

**Qualität**
- [ ] Synthetischer Datensatz: alle Metriken innerhalb der Zielwerte
- [ ] 20 echte Personen: ≥ 18 verwertbare Ergebnisse, ≥ 80 % Wiedererkennung
- [ ] Haar-Bewertung durch 3D-Artist: keine „Badekappen"-Ergebnisse bei Stufe 2/3

**System**
- [ ] 16-KB-Page-Size-Check im App Bundle Explorer: „unterstützt"
- [ ] targetSdk aktuell, alle Berechtigungen mit Disclosure verknüpft
- [ ] Crash-free ≥ 99,5 % in der Beta, ANR ≤ 0,2 %
- [ ] Akku-/Thermik-Test auf Low/Mid/High
- [ ] Wiederaufnahme nach Prozess-Tod, Anruf, Bildschirm aus, Akku < 5 %

**Recht/Daten**
- [ ] Data-Safety-Formular ausgefüllt und mit der Realität abgeglichen
- [ ] Prominent Disclosure vorhanden (Screenshot im Review-Protokoll)
- [ ] `THIRD_PARTY_LICENSES.md` aktuell, Whitelist-Check der CI bestanden
- [ ] Datenschutzerklärung + Impressum verlinkt, Version vermerkt
- [ ] Löschfunktion getestet (Daten wirklich weg, inkl. Cache und Thumbnails)

**Sprachen/Design**
- [ ] DE und EN vollständig (Pseudo-Locale-Test ohne Layout-Bruch)
- [ ] Night + Day Mode auf allen Screens geprüft
- [ ] Kontrastwerte (Dokument in `07`) erneut gemessen
- [ ] TalkBack-Durchlauf auf den 5 Hauptscreens

## 7. Bekannte kritische Testfälle (Punkte, an denen solche Projekte scheitern)

| Testfall | Erwartetes Verhalten |
|---|---|
| Brille auf | Erkennung + Hinweis; Quick-Modus mit Brille muss trotzdem ein brauchbares Ergebnis liefern (Augenregion aus Modell) |
| Sehr kurze Haare / Glatze | Kein Haar-Mesh-Artefakt; Haar-Stufe wird automatisch auf L1 gesetzt |
| Starke Locken (4C) | Haar-Volumen plausibel; keine Löcher; Silhouetten-IoU ≥ 0,75 (niedrigerer Schwellwert akzeptiert, dokumentiert) |
| Bart | Bart als eigenes Haar-System; Kinnregion nicht durch 3DMM "verschluckt" |
| Gegenlicht | Frames werden abgelehnt; Hinweis "nicht gegen das Fenster" |
| Zittern/Bewegung | Kein Frame akzeptiert ⇒ kein Scan; aber keine Endlosschleife: nach 90 s Abbruch mit Tipp |
| Zweite Person im Bild | Zuordnung bleibt stabil (Tracking-Verriegelung auf die erste erkannte Person) |
| Sehr helles/dunkles Gesicht (Fitzpatrick I und VI) | Belichtungsregelung greift; Albedo ohne Farbstich (ΔE ≤ 6) |
| Gerät wird heiß | Pause + Fortsetzung, kein Datenverlust |
| Speicher voll während des Scans | Kontrollierter Stopp mit Checkpoint, keine halben Projekte |
| Uhrzeit-/Zeitzonenwechsel, Flugmodus an | Lizenzen bleiben gültig; Quittungen unverändert |
| App-Update während laufenden Jobs | Job überlebt oder wird sauber fortgesetzt |
