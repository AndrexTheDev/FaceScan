# 09 – Recht, Compliance, Sicherheit, Lizenzen

Stand: 2026-11-15 · **Hinweis:** Arbeitsgrundlage, keine Rechtsberatung. Vor Launch: Fachanwalt (IT-Recht/
Medienrecht) + Steuerberater.

---

## 1. Datenschutz (DSGVO/BDSG)

### 1.1 Einordnung der Daten

| Datenart | Einordnung | Konsequenz |
|---|---|---|
| Kamerabilder des Gesichts | Personenbezogene Daten (Art. 4 Nr. 1) | Verarbeitung nur mit Rechtsgrundlage |
| 3D-Modell des Gesichts | Personenbezogen; **biometrisch i. S. d. Art. 9 nur dann**, wenn es *zur eindeutigen Identifizierung* verarbeitet wird | Wir identifizieren **nicht** ⇒ kein Art. 9. Wir behandeln die Daten **vorsorglich wie Art. 9** (Privacy by Design). |
| Technische Daten (Geräteklasse, App-Version) | Nur lokal, keine Übertragung | Kein Tatbestand |

**Rechtsgrundlagen:** Art. 6 (1)(b) DSGVO (Vertrag: Bereitstellung der App-Funktion) für die Verarbeitung
auf dem Gerät; Art. 6 (1)(a) (Einwilligung) für alles Freiwillige (Telemetrie, Sprachführung mit TTS-Daten,
Projekt-Export). **Keine** Verarbeitung zu Werbezwecken, **keine** Weitergabe, **keine** Auftragsverarbeiter.

### 1.2 Datenschutz-Folgenabschätzung (DSFA)

Rechtlich nicht zwingend (keine umfangreiche Verarbeitung besonderer Kategorien, keine systematische
Überwachung), aber **dringend empfohlen** und ein starkes Verkaufsargument. Inhalt:
1. Beschreibung der Verarbeitung (Kamera → lokale Rekonstruktion → lokale Speicherung).
2. Risiken: Verlust/Missbrauch des Geräts, Screenshot/Cloud-Backup durch das System, Deepfake-Missbrauch
   exportierter Modelle.
3. Maßnahmen: Verschlüsselung, `FLAG_SECURE`, `allowBackup=false`, `noBackupFilesDir` für Schlüssel,
   Tresor-PIN/Biometrie, Panic-Wipe, lokales Audit-Log, C2PA-Kennzeichnung, Alters-Gate.
4. Ergebnis: Restrisiko gering, dokumentiert ⇒ die Datenschutz-Sektion der Landingpage kann darauf verweisen.

### 1.3 Betroffenenrechte (in der App umgesetzt)

| Recht | Umsetzung |
|---|---|
| Information (Art. 13/14) | Datenschutzerklärung in der App **und** auf der Landingpage, vor dem ersten Scan verlinkt |
| Auskunft (Art. 15) | „Einstellungen → Datenschutz → Meine Daten": Liste aller Projekte, Größe, Datum, Clips |
| Löschung (Art. 17) | Projekt löschen / Alles löschen (Zwei-Faktor-Bestätigung, Löschprotokoll) |
| Datenübertragbarkeit (Art. 20) | Export als `.fscan` (dokumentiertes, offenes Format) bzw. als ZIP |
| Einschränkung/Widerspruch | Entfällt faktisch (keine Verarbeitung außerhalb des Geräts) |

### 1.4 Nationales Recht (DE)

- **§ 22 KUG / Recht am eigenen Bild:** Das *Erstellen* eines 3D-Modells ist keine Bildveröffentlichung, aber
  das **Veröffentlichen des Ergebnisses** (Render, Social Media) kann eine Einwilligung der abgebildeten
  Person erfordern. ⇒ In-App-Funktion **„Model-Release"**: kurzer Text + Unterschrift-Feld (digital), lokal
  als PDF erzeugt, mit Datum/Zeit und Hinweis, dass die Einwilligung zwischen den Parteien (Nutzer ↔
  Modell) gilt. Nur ein Werkzeug, keine Rechtsberatung, klar beschriftet.
- **§ 201a StGB** (Verletzung des höchstpersönlichen Lebensbereichs): Schutz vor Entstellung/"Nackt-
  Bearbeitung". ⇒ EULA-Verbot + technische Leitplanken (keine Funktionen zur Entkleidung; keine
  "Nudify"-Features; Verstoß führt zur Deaktivierung).
- **EU AI Act:** Unser System ist **kein Hochrisiko-System**. Bei Generierung/Synthese von Bildinhalten
  greifen Transparenzpflichten (Kennzeichnung synthetischer Inhalte). ⇒ C2PA-Content-Credentials (Kapitel 4)
  undsichtbares Wasserzeichen in gerenderten Bildern des Free-Tiers. Prüfen: Gilt die App selbst als
  "Anbieter" oder der Nutzer? (Fachanwalt.)
- **Jugendschutz:** Alters-Gate **16+** (biometrie-nahe Verarbeitung, DSGVO Art. 8 in DE: 16 Jahre).

## 2. Google Play

| Anforderung | Umsetzung |
|---|---|
| **Data-Safety-Formular** | Wahrheitsgemäß: *keine Erhebung, keine Weitergabe*. Kamera = nur auf dem Gerät verarbeitet. „Data collected: None" – das ist das stärkste Vertrauenssignal im Store-Eintrag. |
| **Prominent Disclosure (In-App-Hinweis)** | Pflicht, wenn Datenerhebung für Nutzer nicht erwartbar ist [1](https://legiflare.com/blog/google-play-prominent-disclosure) [2](https://www.termsfeed.com/blog/android-sensitive-data-collection/): Vor der Kamera-Berechtigung ein **eigener Screen**, nicht nur in der Datenschutzerklärung, mit: (a) was wir erfassen (Kamerabild des Gesichts), (b) wofür (3D-Modell), (c) dass es das Gerät nicht verlässt, (d) ausdrückliche Zustimmung per Button (kein Wegklicken, kein Auto-Dismiss). |
| **Berechtigungen** | `CAMERA` (mit Disclosure), `RECORD_AUDIO` (optional, nur Lip-Sync), `POST_NOTIFICATIONS` (Verarbeitungs-Service), `FOREGROUND_SERVICE`. **Kein** Standort, keine Kontakte, keine Telefonnummer, kein `READ_MEDIA_*` (wir nutzen SAF). |
| **Ziel-API-Level** | Immer aktuelles targetSdk (Play-Pflicht). |
| **16-KB-Page-Size** | Alle nativen Bibliotheken mit NDK r28+ und `ANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON` bauen [3](https://github.com/react/react-native/issues/53649). Die Fristen wurden mehrfach verlängert (zuletzt offenbar auf 2027) [4](https://www.reddit.com/r/androiddev/comments/1tqd2t8/google_quietly_extended_the_16kb_page_size/) – trotzdem ab Tag 1 erfüllen. |
| **Keine Werbe-/Tracking-SDKs** | Kein Advertising-ID, kein Firebase Analytics im Kern (optionaler, anonymer Self-Host-Endpunkt nur mit Opt-in). |
| **KI-/Deepfake-Policy** | Wenn wir später generative Funktionen (Detail-Prior, Audio-Lip-Sync, Text-zu-Mimik) einführen: In-App-Kennzeichnungspflicht + Meldeweg für Missbrauch + Verbot in den AGB. |
| **Store-Eintrag** | Screenshots in beiden Modi (Night/Day), Kurzvideo, Feature-Graphic in Jamaika-Farben, Datenschutz-Link, Support-E-Mail, keine irreführenden Vergleiche ("besser als X" ist riskant). |
| **Altersfreigabe** | 16+ (biometrie-nahe Verarbeitung). |

## 3. Sicherheit der App

| Thema | Maßnahme |
|---|---|
| Tresor | AES-256-GCM, Keystore/StrongBox, optional Argon2id-PIN (siehe `06`) |
| Export aus dem Tresor | „Daten verlassen den Tresor" ⇒ Warnung + Bestätigung, danach Klartext-ZIP |
| Angriffsfläche | Keine WebViews, kein `INTERNET` im Kernprozess, kein dynamisches Code-Laden, R8 + Strip |
| Modell-Integrität | SHA-256 aller ML-Modelle im Code verankert; Abweichung ⇒ Start verweigert |
| Native Sicherheit | Bound-Checks, Fuzzing der Importer/Writer (siehe `10`), kein `strcpy`, ASan/UBSan im CI |
| Adressen im Code | Konstanten + Prüfsumme; Anzeige der ersten/letzten Zeichen; kein Clipboard-Monitoring |
| Support | Kein Fernzugriff, keine Kontodaten; Support arbeitet nur mit vom Nutzer freiwillig gesendeten Tx-IDs |

## 4. C2PA / Content Credentials (Herkunftsnachweis)

**Ziel:** Nachweisbar machen, dass ein Render/Export aus FaceScan stammt und wie er erzeugt wurde –
wichtig gegen Deepfake-Vorwürfe und für professionelle Nutzer (Studio-Portfolio).

- **Bibliothek:** `contentauth/c2pa-android` bzw. das darauf aufbauende `simple-c2pa`
  (Android via Maven) [5](https://proofmode.org/blog/simple-c2pa) [6](https://github.com/contentauth/c2pa-android-example).
  Lizenzen der Teilkomponenten vor Einbau verifizieren (C2PA-Rust-SDK ist überwiegend Apache-2.0/MIT).
- **Offline-Signierung:** möglich – Schlüsselpaar und selbst-signiertes Zertifikat werden **auf dem Gerät**
  erzeugt [5](https://proofmode.org/blog/simple-c2pa). Das ist exakt unser Offline-First-Anspruch.
  Einschränkung: Ein selbst-signiertes Gerätezertifikat hat geringere Vertrauenswürdigkeit als ein
  zertifiziertes C2PA-Zertifikat – in der App ehrlich benennen ("Unterschrift deines Geräts").
  Für v2: Zertifikat von einer CA/über den eigenen Server ausstellen (einmalig online).
- **Was wird signiert?** Rendert-Bilder (PNG/JPEG) und das Projekt-Manifest; bei 3D-Formaten zusätzlich eine
  begleitende `.c2pa`-Manifest-Datei. Assertions: `c2pa.created`, Software-Agent (FaceScan + Version),
  Erzeugungszeit, Hash der Quell-Frames, Pipeline-Parameter, Lizenz-Tier, **keine** Personendaten.
- **Zusätzlich:** Unsichtbares Wasserzeichen (robuste, aber unaufdringliche Einbettung in den gerenderten
  Bildern) und – im Free-Tier – ein sichtbares, dezentes Wasserzeichen.

## 5. Lizenzen: Audit der Fremd-Bestandteile (verbindlich vor jedem Release)

### 5.1 Erlaubt (permissiv, kommerziell nutzbar)

| Komponente | Lizenz | Prüfstatus |
|---|---|---|
| MediaPipe Tasks (Android) | Apache-2.0 | bestätigt [7](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker) |
| TensorFlow Lite | Apache-2.0 | Standard |
| MediaPipe-Modelle (`face_landmarker.task`, `hair_segmenter.tflite`, Pose/Hand) | Apache-2.0-Code; **Modellkarten/Google-AI-Edge-Bedingungen vor Einbau schriftlich prüfen** | **offen** |
| Alembic (`alembic/alembic`) | **BSD-3-Clause** | bestätigt [8](https://github.com/alembic/alembic/blob/master/LICENSE.txt) |
| Imath | BSD-3-Clause | bestätigt [9](https://github.com/AcademySoftwareFoundation/Imath) |
| OpenEXR | BSD-3-Clause | bestätigt [10](https://www.loc.gov/preservation/digital/formats//fdd/fdd000583.shtml) |
| PoissonRecon | MIT | bestätigt [11](https://github.com/mkazhdan/PoissonRecon) |
| xatlas (UV) | MIT | bestätigt [12](https://github.com/prideout/xatlas) |
| Microsoft UVAtlas | MIT | Standard (vor Einbau Datei-Lizenz prüfen) |
| Open3D | MIT (nur Test-Toolchain) | bestätigt [13](https://www.open3d.org/paper.pdf) |
| Assimp | BSD-3-Clause (**nur Tests**, nicht im Produkt: schreibt nur FBX-ASCII) | bestätigt [14](http://www.assimp.org/index.php?id=11:faq) |
| Eigen | MPL-2 (dateibezogen): unverwendet lassen oder unverändert + dynamisch linken | Standard |
| libpng / zlib / libjpeg-turbo / libwebp | zlib / BSD-artig | Standard |
| ZXing (QR) | Apache-2.0 | Standard |
| AndroidX / Compose / Room / Hilt / Kotlin | Apache-2.0 | Standard |
| MakeHuman-Basisassets | **CC0** (die *Software* MakeHuman ist AGPL – nur die CC0-Assets und daraus erzeugte Meshes sind frei) | bestätigt [15](https://www.reddit.com/r/blender/comments/1imqe6k/makehuman-license/) – **juristische Zweitmeinung einholen** |

### 5.2 Verboten / nur mit Klärung

| Komponente | Problem | Entscheidung |
|---|---|---|
| **FLAME** (MPI) | Academic Model License: „any use for commercial … purposes is prohibited". Ausnahme: **FLAME 2023 Open** unter CC-BY, aber mit Verbot von pornografischen und „fake, libelous, misleading"-Inhalten [16](https://flame.is.tue.mpg.de/modellicense.html) | **Nicht verwenden.** Eigene 3DMM aufbauen. |
| **Basel Face Model (BFM)** | Forschungs-/Einzellizenz, keine kommerzielle Weitergabe | **Nicht verwenden.** |
| **ICT-FaceKit** | Repo nennt MIT, gleichzeitig wird die Version als „non-commercial version" bezeichnet [17](https://github.com/USC-ICT/ICT-FaceKit) | **Nicht ohne anwaltliche Klärung.** Falls geklärt: nur als *Referenz*, nie als ausgeliefertes Asset. |
| **VCGLib / MeshLab / Blender-Quelltext** | GPL/AGPL | **Streng verboten** – auch kein „Abschreiben" von Algorithmen aus GPL-Quelltext (z. B. Blenders FBX-Exporter). Der FBX-Writer wird aus öffentlichen Formatbeschreibungen und eigenen Experimenten entwickelt. |
| **CGAL** (Teile GPL) | GPL/LGPL-Mix | Nur LGPL-Teile, dynamisch gelinkt – besser: vermeiden. |
| **COLMAP** | Lizenzhistorie uneinheitlich (ältere Versionen GPL) | **Nicht verwenden** (wir brauchen es ohnehin nicht). |
| Forschungs-Datensätze (FaceScape, HEADSPACE, 3D-RGBD-Köpfe usw.) | Meist „research only" | Nur mit schriftlicher kommerzieller Lizenz – sonst: **eigene Daten** erheben |

### 5.3 Absicherung im Build

1. `THIRD_PARTY_LICENSES.md` wird im Build automatisch erzeugt (Gradle-Lizenz-Plugin) und in der App unter
   „Über → Danksagungen" **vollständig** angezeigt (Pflicht bei BSD/Apache/MIT: Copyright-Vermerke).
2. **Lizenz-Gate in der CI:** Ein Skript prüft die Abhängigkeitsliste gegen eine Whitelist
   (erlaubt: Apache-2.0, MIT, BSD-2/3, ISC, 0BSD, CC0, zlib, MPL-2-nur-unverändert). Jede
   GPL/AGPL/LGPL/"non-commercial"-Lizenz bricht den Build.
3. Trainingsdaten für die eigene 3DMM: **ausschließlich** mit schriftlicher Einwilligung, die die
   Nutzung für statistische Modellbildung ausdrücklich einschließt (Opt-in, getrennt von der
   Datenschutzerklärung, widerrufbar mit Löschfolge für künftige Modellversionen).
4. Jede ausgelieferte Datei (Mesh, Textur, Template) bekommt ein Herkunfts-Metadatum
   (`source: own | cc0 | mit | <lizenz>`), das auch im Export landet.

## 6. EULA / Nutzungsbedingungen (Entwurf der Kernpunkte)

| Abschnitt | Inhalt |
|---|---|
| **Lizenzumfang** | Starter: privat, nicht kommerziell. Creator: kommerziell bis 100 k € Jahresumsatz des Lizenznehmers. Studio: unbegrenzt.Immer: **der Nutzer darf die exportierten Modelle bearbeiten, verkaufen und in Produkten einsetzen** (das ist der Kern des kommerziellen Werts). |
| **Nicht erlaubt** | Biometrische Identifikation von Personen; Massenüberwachung; Erzeugung pornografischer, verleumderischer oder täuschender Inhalte; Nutzung ohne Einwilligung der abgebildeten Person (Verweis auf Model-Release); Weiterverkauf der App-Dateien/Modelle als „Scan-Dienst" ohne Studio-Lizenz. |
| **Verantwortung des Nutzers** | Einwilligung der abgebildeten Person, Rechte an Frisur/Tattoos/Make-up (Schöpfungshöhe beachten), Kennzeichnung synthetischer Inhalte. |
| **Gewährleistung** | Software „wie besehen"; keine Zusicherung medizinischer/metrologischer Genauigkeit (expliziter Hinweis: **kein** medizinisches Gerät, keine biometrische Erkennung). |
| **Haftung** | Vorsatz/Grobfahrlässigkeit unberührt; im Übrigen begrenzt – üblich, aber anwaltlich formulieren lassen. |
| **Widerruf/Rückgabe** | Freiwillige 14-Tage-Rückgabe (siehe `08`), gesetzliches Widerrufsrecht bei Fernabsatz beachten. |
| **Streitbeilegung** | Verbraucherstreitbeilegung (VSBG-Hinweis) für DE-Kunden prüfen. |

## 7. Marken, Names, Vertriebsformalitäten

| Punkt | To-do |
|---|---|
| Name „FaceScan" | Marken-/Firmenrecherche (DPMA, EUIPO) vor Launch; Wortmarke prüfen (Klasse 9/42) |
| Paketname | `com.andrexthedev.facescan` (festlegen vor dem ersten Release – danach nicht mehr änderbar) |
| Domain | `facescan.app` o. Ä. prüfen; Landingpage auf Cloudflare Pages |
| Impressum | Für Website (Impressumspflicht) *und* in der App verlinken (DE-Recht) |
| Datenschutzerklärung | DE + EN, in App und Website, Versionierung mit Änderungshistorie |
| Versicherung | Betriebshaftpflicht + IT-/Vermögensschadenhaftpflicht (Medienrisiko) prüfen |
| Signierung | Play App Signing, Upload-Key sicher verwahren (Offline-Backup!) – sonst ist die App nicht mehr updatefähig |
