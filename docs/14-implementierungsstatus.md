# Implementierungs- und Prüfstatus: Android-Gesichtsscan

Diese Übersicht unterscheidet App-Funktionen von Entwürfen und synthetischen Referenzprogrammen. Die Dokumente 03–05 beschreiben das Zielsystem; sie belegen keine Implementierung in der Android-App. Ein Häkchen bei einem synthetischen Test ist kein Nachweis an einem Menschen oder einem physischen Gerät.

| Bereich | Android-Stand | Nachweis / offen |
|---|---|---|
| Installation und Offline-Betrieb | Modell wird beim ersten Start von Google geladen und anhand SHA-256 geprüft; danach lokal verwendet. | Download, Cache und Emulatorfälle vorhanden. Echte Netzwerkmessung pro Gerät offen. Modelllizenzprüfung weiterhin offen: `09`. |
| Kamera und Erkennung | Frontkamera; MediaPipe-Landmarks, Bildrotation, Lebenszyklus und Berechtigungen. Bericht klassifiziert statische Metadaten der gebundenen Kamera ohne Ersatzwerte. | Kamera-Pfad mit künstlicher Emulator-Kamera getestet. Qualität und Abdeckung echter Gesichter, Geräte und Umgebungen offen. Keine Identitätsprüfung zwischen Frames. |
| Geometrie | Offene Gesichtsfläche mit 468 Punkten und 898 Dreiecken aus einer Ansicht; neutral aus mehreren zeitlich nahen Frames derselben Ansicht starr ausgerichtet und robust per Median kombiniert. MediaPipe-Tiefe ist geschätzt, Augenabstand normiert. | Synthetische Pipeline-/Topologie-/Ausreißer-Tests vorhanden; der neue Neutral-Fusionspfad ist noch nicht auf einem echten Gerät geprüft. **Keine kalibrierte oder metrisch überprüfte 3D-Rekonstruktion, keine Multi-View-Fusion.** |
| Mehransichten-Kern | Separater experimenteller Kotlin-Kern trianguliert korrespondierende entzerrte Pixel mit bekannten Posen und rekonstruiert unvollständige Punktwolken; optionaler Mehrheitskonsens gegen Ausreißer und explizite Crop-/Rotations-/Skew-Umrechnung und opt-in Brown-Conrady-Entzerrung; keine Verbindung zum Scanablauf. | Nur künstliche Testdaten. Kalibrierung, Kamera-/Kopfposen, robuste reale Korrespondenzen, Verdeckungen und Oberflächenfusion fehlen; kein realer Mehransichten-Scan. |
| Abdeckung | Nur sichtbare Gesichtsoberfläche. | Haar, Ohren, Hinterkopf und ein vollständiger, geschlossener Kopf fehlen. |
| Aufnahmequalität | Heuristische Prüfungen auf Bildrand, Gesichtsgröße und Stabilität; experimentelle Licht-/Kontrast- und 2D-Ausrichtungshinweise, ohne Aufnahme zu blockieren. Fehlerhafte Sequenz wird verworfen. | Schwellen nicht an echten Geräten, Hauttönen oder Lichtbedingungen validiert; kein verlässlicher Schärfe-, Belichtungs- oder Verdeckungsnachweis. |
| Fototextur | Optionaler, ausdrücklich angeforderter Fotoausschnitt aus einer Ansicht, mit UV-Projektion; sonst kein Fotoausschnitt. | Unit-Tests und synthetisches GLB validiert. Android-Selbsttest für künstliches Foto/UV/Vorschau implementiert, auf aktueller Version noch nicht im Emulator ausgeführt. Reale Beleuchtung, Verdeckung und Passung offen. Ausschnitt kann Hintergrund enthalten. |
| Animation | Vier Sekunden zeitgestempelte Landmarks als Morph-Targets; starrer experimenteller Anker-Fit soll Kopfbewegung reduzieren. Optionaler zeitabhängiger Tiefpass und künstlicher 0,5-Sekunden-Rückweg zur Neutralform für Vorschau und GLB, standardmäßig aus. | Mathematische und synthetische Tests vorhanden; Glättung kann Bewegungen verzögern und Ausdrücke abschwächen. Kein validierter 52-Blendshape-Rig, keine zuverlässige Trennung von Pose und Ausdruck, kein Langzeit-Mocap; reale Gesichter und Zielprogramme noch nicht getestet. |
| Vorschau | Orthografische Flächenvorschau mit optionaler Fototextur, approximativer Tiefensortierung und experimentellen Hinweisen auf winzige Dreiecke bzw. lange Kanten in Neutralform und Animation. | Implementiert; aktueller Android-Renderpfad muss im Emulator und auf echter Hardware geprüft werden. Kein Z-Buffer oder vollständiger 3D-Renderer. Netz-Hinweise sind unkalibriert und kein Genauigkeitsnachweis. |
| Export | Animiertes GLB mit Vertex- und Morph-Normalen, optional mit eingebettetem JPEG; statisches neutrales OBJ mit Vertexnormalen ohne Foto/Animation. Dokumentenauswahl explizit. | Künstliches GLB mit/ohne Foto unabhängig validiert; synthetisches OBJ über externen Parser mit Referenzkoordinaten, Normalen und Indizes geprüft. Manuelle Interoperabilität mit 3D-Programmen und reales Speichern sind offen. Weitere geplante Formate und Rig fehlen. |
| Messung | Offline-Referenzvergleich für vom Nutzer bereitgestellte korrespondierende 3D-Punkte, Fit und unabhängige Holdouts getrennt. | Nur synthetisch geprüft. Keine realen Referenzdaten vorhanden; keine Millimeter-Genauigkeit gemessen. Referenzgeführter Skalenfit ist kein Nachweis eigener metrischer Kalibrierung. |
| Datenschutz | Keine automatische Übertragung von Fotos oder Gesichtspunkten. Foto nur nach Opt-in, zunächst im RAM; GLB kann es beim bewussten Export enthalten. | Abruf fremder Modellgewichte beim ersten Start. Gerätebericht enthält keine Bilder/Koordinaten oder Exportdateinamen, aber aggregierte Foto- und Exportzähler. Datenschutzprüfung und reale Netzwerkmessung offen. |
| Tests und APK | Kotlin-Unit-Tests, künstliche Scan-/Export-Selbsttests in der App und Emulator-Tests vorhanden. | Qualitätsmodus baut keine APK. Den aktuellen Stand erst nach Abschluss als Test-APK bauen und im Emulator sowie mit Einwilligung auf realen Geräten testen. |

## Reihenfolge zur tatsächlichen Fertigstellung

1. **Auf realem Gerät prüfen:** Berechtigungen, erster Modell-Download, wiederholbare Neutral- und Mimikaufnahme mit/ohne Foto, Datei speichern/abbrechen, Export mit mehreren unabhängigen GLB-/OBJ-Lesern und Offline-Betrieb. Fehler, Gerät, Licht und App-Version im Bericht festhalten; keine Fotos/Koordinaten automatisch versenden.
2. **Kalibrierte Referenzdaten erheben:** Mit Einwilligung, dokumentierter Genauigkeit und getrennten Fit-/Holdout-Punkten; verschiedene Geräte, Gesichter, Abstände, Licht und Kopfhaltungen. Das [Offline-Werkzeug](../prototype/reference/validation/README.md) wertet Formfehler nach Referenz-Fit aus; selbständige metrische Kalibrierung separat prüfen.
3. **Echte Rekonstruktion vervollständigen:** Kamerakalibrierung und Distortion, reproduzierbare Mehransichten, Bild-/Pose-Akzeptanz, eigene oder ausdrücklich lizenzierte Rekonstruktionsmodelle, geometrische Fusion, Haar/Hinterkopf und Vollständigkeits-/Unsicherheitsbericht. Ohne sichtbare Daten nicht als gemessen ausgeben.
4. **Animation und Austausch vervollständigen:** validierter Kopf-/Augen-/Kieferrig, standardisierte Ausdrucksbasis und Zeitserien, Bewegungs-/Ausdruckstrennung, Zielprogrammtests und weitere tatsächlich implementierte Exportformate. Nicht aus zwei oder 16 aufgenommenen Formen 52 unabhängige Ausdrücke behaupten.
5. **Abschlussgate:** Lizenz- und Datenschutzprüfung, automatische und reale Gerätetests, gemessene Güte gegen vorab festgelegte Akzeptanzkriterien, Dokumentation der Restfehler. Erst danach Test-APK bauen und verteilen.


## Grobe Fortschrittsschätzung

Die folgenden Werte sind eine **subjektive Planungsschätzung**, keine gemessene Vollständigkeit oder Zeitprognose. Bezugsziel ist das gesamte hier dokumentierte Produkt einschließlich realistischer Geräteprüfung, vollständigem Kopf/Haar, belastbarer Genauigkeit, Animation und Export. Zahlen können bei neuen Erkenntnissen steigen oder sinken.

| Teilziel | Gewicht | Grob erfüllt | Wesentliche Lücke |
|---|---:|---:|---|
| Installation, lokaler Betrieb | 10 | 6 | Modell-Lizenz, breite Gerätetests und Netzwerkmessung |
| Geführte Aufnahme und Qualitätskontrolle | 15 | 3 | echte Mehransichten, Beleuchtung/Verdeckung validieren |
| 3D-Rekonstruktion und Genauigkeit | 25 | 2 | kalibrierte Mehransichten, reale Ground Truth |
| Vollständiger Kopf und Haar | 15 | 0 | nicht in der Android-App umgesetzt |
| Animation und Rig | 10 | 2 | standardisierte Ausdrucksformen, Rig, reale Validierung |
| Export und Bedienung | 10 | 3 | weitere Formate, Interoperabilität und Echtgerätetests |
| Datenschutz und Recht | 5 | 2 | vollständige Datenschutz- und Lizenzprüfung |
| Qualitätssicherung und Freigabe | 10 | 2 | reale Geräte, Teilnehmer und Abnahmekriterien |
| **Summe** | **100** | **ca. 20** | **Grobe Gesamtschätzung: etwa 20 %** |

Ein bestandenes synthetisches oder Emulator-Testpaket erhöht diese Zahl nicht automatisch: der ungelöste Kern ist die echte, validierte Rekonstruktion, nicht die Zahl der Tests oder Dateien.
