# FaceScan – Android-Test-App

Die App enthält einen **experimentellen Gesichtsoberflächen-Scan** neben der Testoberfläche. Sie erstellt aus MediaPipe-Gesichtspunkten eine offene Gesichtsoberfläche mit optionaler einseitiger Fototextur und zeichnet nach einer Neutralaufnahme eine bis zu vier Sekunden lange Mimiksequenz auf. Die Animation lässt sich als GLB mit Morph-Target exportieren. Dies ist **kein vollständiger 3D-Kopf** und keine metrisch kalibrierte Rekonstruktion: Haare, Hinterkopf, vollständige Textur und validierte 3D-Genauigkeit fehlen. Das Verfahren ist noch nicht auf einem echten Telefon und mit einem echten Gesicht verifiziert.

Die vorhandenen Tests und ein freiwillig teilbarer technischer Bericht bleiben zugänglich. Ein grüner CI-Lauf oder ein Emulatortest mit künstlichen Daten ersetzt den Gerätetest nicht.
## Installation und erster Test

Die neueste Test-APK liegt bei den [GitHub-Releases](https://github.com/AndrexTheDev/FaceScan/releases). Dort `app-debug.apk` herunterladen und auf Android 10 oder neuer installieren. Es ist ein Debug-Build. Wenn Android ein Update wegen abweichender Debug-Signatur ablehnt, die ältere Testversion erst deinstallieren (dabei werden ihre App-Daten gelöscht) und dann die neue APK installieren.

1. Vor dem ersten Start Internet aktivieren. Die App lädt die einzige zur Laufzeit benötigte Modelldatei automatisch von Google (rund 3,6 MB) herunter und prüft deren SHA-256. Der übrige Anwendungscode und die Bibliotheken sind in der APK. Die App meldet, ob das Modell bereit ist; bei einem Fehler Verbindung prüfen und **Erneut versuchen** antippen.
2. Beim Start werden eine einfache Pinhole-Projektion, ein synthetisches Scan-Mesh mit GLB-Export, ein Foto-/UV- und OBJ-Test mit künstlichem Farbbild sowie MediaPipe auf einem schwarzen Testbild geprüft; der Systemhinweis zur Frontkamera wird angezeigt. Diese Smoke-Tests sind kein vollständiger Geometrietest.
3. **Synthetischen 3D-Mathe-Test starten** und das Ergebnis abwarten. Er prüft Pose (F1) und Multi-Frame-Fit (F2) anhand künstlicher Referenzdaten; seine Kennzahlen erscheinen im Bericht. Das ist kein Scan einer Person.
4. **Kameratest starten**, den Hinweis lesen und die Kamera erlauben. Gesicht ins Bild halten, **1. Gesicht im Bild testen** antippen und fünf Sekunden stillhalten. Gesicht aus dem Bild bewegen, **2. Gesicht außerhalb testen** antippen und fünf Sekunden warten. Jeder Test benötigt mindestens drei ausgewertete Frames; mindestens 75 % müssen die erwartete Antwort liefern. Zu wenige Frames sind „nicht aussagekräftig“, nicht bestanden.
5. Für **3. Im Flugmodus testen** Flugmodus einschalten und WLAN sowie weitere Netze ausschalten. Während der Test läuft, muss Android am Anfang und Ende Flugmodus ohne internetfähiges Netzwerk melden. Mindestens drei Frames müssen erfolgreich verarbeitet werden. Dies ist keine Netzwerkpaket-Messung und kein Offline-Test eines 3D-Scans.
6. **Testbericht** öffnen. Er zeigt Ergebnisse, nicht ausgeführte und abgebrochene Tests sowie technische Daten vor dem Teilen. **Kopieren** antippen und den Text in den Chat einfügen oder bewusst mit **Teilen** versenden. Bei einem Absturz die App erneut öffnen und den Bericht auf dem Startbildschirm abrufen. Die Testresultate bleiben nur während der Sitzung erhalten; bei einem Neustart müssen die geführten Tests erneut laufen.
7. Optional: Kamera-Berechtigung verweigern oder in den Systemeinstellungen entziehen, App wieder öffnen und Reaktion berichten. Ein Debug-Build kann geräteabhängig abweichen.

## Experimenteller Gesichts-Scan

1. **Experimentellen Gesichts-Scan starten**; Kameraerlaubnis erteilen und neutral in die Frontkamera schauen. Handy und Kopf möglichst ruhig halten. Nach mehreren erkannten Frames **1. Neutral aufnehmen** wählen. Alternativ nimmt **1. Neutral mit Fotoausschnitt aufnehmen** ausdrücklich einen kleinen Fotoausschnitt auf. Dieser wird als Fototextur im GLB eingebettet und kann auch Hintergrund enthalten. Die App prüft grob, ob das Gesicht vollständig und ausreichend groß im Bild liegt und die Punkte stabil sind. Diese empirischen Schwellen sind keine Qualitäts- oder Genauigkeitsgarantie.
2. **2. Mimik 4 Sekunden aufnehmen** startet die Aufnahme. Kopf und Telefon möglichst ruhig halten und die Mimik bewegen. Die App speichert höchstens 16 zeitgestempelte Formen im Speicher; Bilder werden nicht gespeichert. Bei Gesichtsausfall wird auch eine zuvor erfasste Neutralform verworfen; sie muss erneut aufgenommen werden. Bei Anschnitt, zu kleinem Gesicht, größeren Erkennungslücken, Kamerawechsel, Hintergrundwechsel oder Abbruch wird die Sequenz verworfen. Langsame Geräte können deshalb eine erneute Aufnahme erfordern.
3. Die vereinfachte Flächenvorschau kann per Wischen gedreht werden; eine ausgewählte Fototextur wird darin angezeigt. Sie verwendet eine orthografische Projektion und grobe Tiefensortierung, keinen vollständigen 3D-Renderer. Der Regler zeigt den Zeitverlauf; die Wiedergabe wiederholt ihn und kann am Ende springen. **Animiertes GLB exportieren** öffnet den Android-Dateidialog. Die Datei enthält die Geometrie, zeitgestempelte Morph-Targets und, falls ausdrücklich gewählt, den fotografischen Ausschnitt als eingebettete JPEG-Textur. Alternativ speichert **OBJ** nur die neutrale Geometrie, ohne Animation und ohne Foto. Manche 3D-Programme oder Viewer unterstützen nicht alle bis zu 16 Morph-Targets; Kompatibilität ist noch nicht auf realen Zielprogrammen geprüft.

### Neutralgeometrie aus mehreren Frames

Bei der Neutralaufnahme werden bis zu fünf aktuelle Erkennungen **aus derselben Kameraansicht** in augenabstandsnormierte Koordinaten umgerechnet. Die App wählt anhand der Ankerpassung einen Konsens-Frame, richtet die übrigen Oberflächen starr daran aus und bildet pro Koordinate den Median. Sie benötigt mindestens drei akzeptierte Frames; der neueste Frame muss Teil des Konsenses sein. Einzelne starke Landmark-Ausreißer können dadurch weniger Einfluss haben. Die Vorschau zeigt die Anzahl und den internen Ankerrest, die lediglich Stabilität bzw. Passung beschreiben.

Das ist **keine Mehransichten-Rekonstruktion**, kein Tiefensensor und kein Beleg für höhere reale 3D-Genauigkeit. Die geschätzte Tiefe kann systematisch falsch sein; starre Ausrichtung, Perspektive und Mimik können Ergebnisse verfälschen. Die Schwelle und der Nutzen sind noch nicht mit echten Personen gegen eine externe Referenz validiert.

### Experimentelle Bewegungskorrektur

Jede aufgenommene Form wird über 13 Punkte an Stirn, Augenwinkeln und Nasenrücken starr auf die neutrale Gesichtsform ausgerichtet. Eine Quaternionen-Lösung schätzt 3D-Rotation und Translation im zuvor auf Augenabstand normierten Raum; Mimik abseits dieser Anker bleibt als Verformung erhalten. Übersteigt der interne RMS-Abstand der Anker den heuristischen Grenzwert von 0,12 Augenabständen, verwirft die App die Sequenz. Der größte verbleibende Anpassungsrest wird in der Vorschau angezeigt. Das ist ein Maß für die *interne Passung*, nicht ein nachgewiesener Fehler gegenüber der Wirklichkeit.

Die MediaPipe-Tiefe ist geschätzt und verändert sich bei Perspektive, Verdeckung, Augenbewegung und Kopfrotation. Diese einfache starre Ausrichtung kann solche Effekte nicht zuverlässig ausgleichen und die Anker können selbst durch Mimik oder Tracking schwanken. Möglichst frontal und ruhig aufnehmen. Keine Personenerkennung: Es wird nicht geprüft, ob alle Formen von derselben Person stammen. Die Schwelle und der Nutzen sind noch nicht an echten Personen oder kalibrierter Ground Truth getestet. Tests mit synthetischen Drehungen und Translationen prüfen nur die mathematische Implementierung.

Die angezeigte Punktschwankung in Pixeln misst nur die Stabilität während der jeweiligen Aufnahme – keine absolute 3D-Genauigkeit. Die angezeigten Schwellen und die Schwankung beweisen weder die Scanqualität noch die richtige Zuordnung von Kopfbewegung und Mimik. Die Koordinaten sind auf Augenabstand normiert und die MediaPipe-Tiefe ist relativ; Einheiten im GLB sind **nicht maßstabsgetreu**. Es gibt keinen belegten Fehler in Millimetern und keine Rückseite. Das Ergebnis ist für Tests und Experimente, nicht für medizinische, biometrische oder vermessungstechnische Anwendungen geeignet.

Ohne Fotoauswahl wird kein Fotoausschnitt erzeugt. Bei ausdrücklicher Fotoauswahl speichert die App einen auf die Gesichtsregion zugeschnittenen, höchstens 768 Pixel großen JPEG-Ausschnitt **zunächst nur im Arbeitsspeicher**; er kann Hintergrund, Brille und Schatten enthalten und wird in der Vorschau gezeigt. Gesichtspunkte, Foto und Modell werden beim Verlassen verworfen. Erst nach ausdrücklicher Auswahl eines Speicherorts schreibt die App eine Datei. GLB kann das Foto enthalten, OBJ enthält Geometrie ohne Foto: Beide sind sensible Daten und sollten nur bewusst geteilt werden. Keine automatische Übertragung.

Zum Vergleich mit echten, extern vermessenen Referenzpunkten steht ein [Offline-Auswertewerkzeug](../reference/validation/README.md) bereit. Es trennt die Punkte zur Registrierung von zurückgehaltenen Kontrollpunkten. Ohne solche Referenzdaten liefert es keine tatsächliche Genauigkeitszahl.

Die Dreiecksindizes stammen aus [`canonical_face_model.obj` von MediaPipe v0.10.14](https://github.com/google-ai-edge/mediapipe/blob/v0.10.14/mediapipe/modules/face_geometry/data/canonical_face_model.obj), Apache-2.0. Die Lizenz liegt in `app/src/main/assets/licenses/mediapipe.txt`; es werden weder kanonische Modellpositionen noch Modellgewichte aus dieser Datei übernommen.

## Datenschutz und Netzwerk

Der erstmalige Modell-Download nutzt HTTPS zu `storage.googleapis.com`. Dabei sieht Google die IP-Adresse des Geräts; Mobilfunkkosten können anfallen. Die App benötigt dafür `INTERNET`. Nach der Installation wird bei erfolgreicher Integritätsprüfung kein erneuter Modell-Download ausgeführt; die Gesichtserkennung läuft lokal. Diese Aussage betrifft den implementierten Anwendungspfad, nicht eine bereits auf jedem Gerät bestätigte Netzwerkmessung.

Der Bericht enthält App-Version, Hersteller und Modell des Geräts, Android-Version, Kamera-Berechtigung, Modellstatus, Ergebnisse der Geräte- und geführten Tests, Fehlerklassen, Kamerabildformat, aggregierte Frame- und Erkennungszähler sowie Laufzeiten. Ein letzter Java-Absturz wird lokal mit Ausnahme-Klasse und höchstens acht eigenen Code-Stackframes gespeichert, ohne Fehlermeldung. Native Abstürze werden dadurch nicht zuverlässig erfasst. Der übrige Bericht existiert nur während der App-Sitzung. **Keine Fotos, Bilddaten oder Gesichtspunkte werden im Bericht gespeichert oder automatisch versendet.** Der Nutzer sieht den Bericht vor dem Kopieren/Teilen; andere Apps, an die er ihn sendet, unterliegen deren eigenen Datenschutzbedingungen.

## Modell und Lizenz

Die Modellgewichte sind weder im Repository noch in der APK. Die App lädt genau `face_landmarker/float16/1/face_landmarker.task` von Google und akzeptiert nur SHA-256 `64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff`. Der Download ist auf 10 MiB begrenzt; kaputte oder unvollständige Dateien werden nicht verwendet. Dateien liegen im privaten App-Speicher. Sollte Google den Inhalt ändern, scheitert die Integritätsprüfung statt ein anderes Modell zu laden.

Die Modellkarte und die Google-AI-Edge-Bedingungen sind nach [`docs/09`](../../docs/09-recht-compliance.md) **noch nicht schriftlich geprüft**. Der Test-Download ist keine Lizenzfreigabe; die Prüfung bleibt vor einer Weitergabe bzw. produktiven Nutzung zu erledigen.

## Build und Tests

Der Workflow [`.github/workflows/apk.yml`](../../.github/workflows/apk.yml) prüft bei Änderungen automatisch die Kotlin-Komponenten, die synthetischen GLBs und den Referenzvergleich, ohne eine APK zu bauen. Erst auf ausdrücklichen Dispatch werden Debug-APK und optional Test-Release gebaut. Der Emulatortest ist ebenfalls manuell zu starten. Ein Test-Release kann so erzeugt werden:

```sh
gh workflow run apk.yml --ref arena/ee31e880-facescan -f release=true
```

Die Unit-Tests prüfen unter anderem synthetische starre 3D-Rotationen/Translationen, fehlerhafte Anker, Gesichtsoberfläche, Animation und GLB-Export; ein unabhängiger Khronos glTF-Validator prüft synthetische GLB-Dateien mit und ohne Fototextur. Weitere Tests prüfen Cache-Wiederverwendung, fehlerhafte Prüfsummen, Größenbegrenzung, Download-Fehler, Frame-Timing und den Schutz vor verspäteter Kamera-Bindung.

Der separate Workflow [Android-Emulatortest](../../.github/workflows/android-device-test.yml) prüft auf Android 11 mit x86-Emulator: Erststart ohne Netz, tatsächlichen Download und Integrität, Inferenz auf einem schwarzen Testbild, Bericht und Kopierfunktion, Offline-Start mit Modell-Cache sowie Kameraframes aus der emulierten Frontkamera. Dabei werden auch der synthetische F1/F2-Geometrietest, die geführten Tests und die Berechtigungsseite geprüft. Künstliche Bilder ersetzen weder ein menschliches Gesicht noch einen Test auf echter Hardware. Der aktuelle Implementierungs- und Prüfstand steht in [docs/14](../../docs/14-implementierungsstatus.md). Ein Gerätetest einschließlich Erkennungsqualität und manuellem Teilen bleibt erforderlich.

MediaPipe 0.10.14 enthält native Bibliotheken für `arm64-v8a`, `armeabi-v7a` und `x86`, aber nicht für `x86_64`. Die APK ist deshalb auf diese drei ABIs begrenzt; ein x86-64-Gerät benötigt 32-Bit-x86-Unterstützung. Reine x86-64-Geräte ohne x86-Unterstützung werden nicht unterstützt. Ein CI-Check verhindert, dass eine nicht passende ABI-Auswahl versehentlich ausgeliefert wird.
