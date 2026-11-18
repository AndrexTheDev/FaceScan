# FaceScan – Android-Test-App

Die App enthält einen **experimentellen Gesichtsoberflächen-Scan** neben der Testoberfläche. Sie rekonstruiert aus den MediaPipe-Gesichtspunkten zweier Aufnahmen eine offene, nicht texturierte Gesichtsoberfläche und kann zwischen neutral und einem aufgenommenen Ausdruck interpolieren. Die Animation lässt sich als GLB mit Morph-Target exportieren. Dies ist **kein vollständiger 3D-Kopf** und keine metrisch kalibrierte Rekonstruktion: Haare, Hinterkopf, Textur und validierte 3D-Genauigkeit fehlen. Das Verfahren ist noch nicht auf einem echten Telefon und mit einem echten Gesicht verifiziert.

Die vorhandenen Tests und ein freiwillig teilbarer technischer Bericht bleiben zugänglich. Ein grüner CI-Lauf oder ein Emulatortest mit künstlichen Daten ersetzt den Gerätetest nicht.
## Installation und erster Test

Die neueste Test-APK liegt bei den [GitHub-Releases](https://github.com/AndrexTheDev/FaceScan/releases). Dort `app-debug.apk` herunterladen und auf Android 10 oder neuer installieren. Es ist ein Debug-Build. Wenn Android ein Update wegen abweichender Debug-Signatur ablehnt, die ältere Testversion erst deinstallieren (dabei werden ihre App-Daten gelöscht) und dann die neue APK installieren.

1. Vor dem ersten Start Internet aktivieren. Die App lädt die einzige zur Laufzeit benötigte Modelldatei automatisch von Google (rund 3,6 MB) herunter und prüft deren SHA-256. Der übrige Anwendungscode und die Bibliotheken sind in der APK. Die App meldet, ob das Modell bereit ist; bei einem Fehler Verbindung prüfen und **Erneut versuchen** antippen.
2. Beim Start werden eine einfache Pinhole-Projektion und MediaPipe auf einem schwarzen Testbild geprüft; der Systemhinweis zur Frontkamera wird angezeigt. Diese Smoke-Tests sind kein vollständiger Geometrietest.
3. **Synthetischen 3D-Mathe-Test starten** und das Ergebnis abwarten. Er prüft Pose (F1) und Multi-Frame-Fit (F2) anhand künstlicher Referenzdaten; seine Kennzahlen erscheinen im Bericht. Das ist kein Scan einer Person.
4. **Kameratest starten**, den Hinweis lesen und die Kamera erlauben. Gesicht ins Bild halten, **1. Gesicht im Bild testen** antippen und fünf Sekunden stillhalten. Gesicht aus dem Bild bewegen, **2. Gesicht außerhalb testen** antippen und fünf Sekunden warten. Jeder Test benötigt mindestens drei ausgewertete Frames; mindestens 75 % müssen die erwartete Antwort liefern. Zu wenige Frames sind „nicht aussagekräftig“, nicht bestanden.
5. Für **3. Im Flugmodus testen** Flugmodus einschalten und WLAN sowie weitere Netze ausschalten. Während der Test läuft, muss Android am Anfang und Ende Flugmodus ohne internetfähiges Netzwerk melden. Mindestens drei Frames müssen erfolgreich verarbeitet werden. Dies ist keine Netzwerkpaket-Messung und kein Offline-Test eines 3D-Scans.
6. **Testbericht** öffnen. Er zeigt Ergebnisse, nicht ausgeführte und abgebrochene Tests sowie technische Daten vor dem Teilen. **Kopieren** antippen und den Text in den Chat einfügen oder bewusst mit **Teilen** versenden. Bei einem Absturz die App erneut öffnen und den Bericht auf dem Startbildschirm abrufen. Die Testresultate bleiben nur während der Sitzung erhalten; bei einem Neustart müssen die geführten Tests erneut laufen.
7. Optional: Kamera-Berechtigung verweigern oder in den Systemeinstellungen entziehen, App wieder öffnen und Reaktion berichten. Ein Debug-Build kann geräteabhängig abweichen.

## Experimenteller Gesichts-Scan

1. **Experimentellen Gesichts-Scan starten**; Kameraerlaubnis erteilen und neutral in die Frontkamera schauen. Handy und Kopf möglichst ruhig halten. Nach mehreren erkannten Frames **1. Neutral aufnehmen** wählen.
2. Mimik ändern, einige Sekunden warten und **2. Mimik aufnehmen und Modell anzeigen** wählen. Die Erkennung mittelt bis zu fünf kürzlich verarbeitete Frames je Aufnahme. Längeres Warten verringert die Vermischung beider Ausdrücke; Kopfbewegung und Mimik können trotzdem nicht zuverlässig getrennt werden.
3. Die Drahtgitter-Vorschau kann per Wischen gedreht werden. Regler und Abspieltaste interpolieren zwischen den zwei aufgenommenen Ausdrücken. **Animiertes GLB exportieren** öffnet den Android-Dateidialog; die Datei enthält die Gesichtsgeometrie und eine einfache Morph-Animation.

Die angezeigte Punktschwankung in Pixeln misst nur die Stabilität während der jeweiligen Aufnahme – keine absolute 3D-Genauigkeit. Die Koordinaten sind auf Augenabstand normiert und die MediaPipe-Tiefe ist relativ; Einheiten im GLB sind **nicht maßstabsgetreu**. Es gibt keinen belegten Fehler in Millimetern und keine Rückseite. Das Ergebnis ist für Tests und Experimente, nicht für medizinische, biometrische oder vermessungstechnische Anwendungen geeignet.

Kamerabilder werden nicht gespeichert. Gesichtspunkte und Modell bleiben während der Nutzung im Arbeitsspeicher und werden beim Verlassen verworfen. Erst nach ausdrücklicher Auswahl eines Speicherorts schreibt die App ein GLB; es enthält sensible Gesichtsgeometrie und sollte nur bewusst geteilt werden.

Die Dreiecksindizes stammen aus [`canonical_face_model.obj` von MediaPipe v0.10.14](https://github.com/google-ai-edge/mediapipe/blob/v0.10.14/mediapipe/modules/face_geometry/data/canonical_face_model.obj), Apache-2.0. Die Lizenz liegt in `app/src/main/assets/licenses/mediapipe.txt`; es werden weder kanonische Modellpositionen noch Modellgewichte aus dieser Datei übernommen.

## Datenschutz und Netzwerk

Der erstmalige Modell-Download nutzt HTTPS zu `storage.googleapis.com`. Dabei sieht Google die IP-Adresse des Geräts; Mobilfunkkosten können anfallen. Die App benötigt dafür `INTERNET`. Nach der Installation wird bei erfolgreicher Integritätsprüfung kein erneuter Modell-Download ausgeführt; die Gesichtserkennung läuft lokal. Diese Aussage betrifft den implementierten Anwendungspfad, nicht eine bereits auf jedem Gerät bestätigte Netzwerkmessung.

Der Bericht enthält App-Version, Hersteller und Modell des Geräts, Android-Version, Kamera-Berechtigung, Modellstatus, Ergebnisse der Geräte- und geführten Tests, Fehlerklassen, Kamerabildformat, aggregierte Frame- und Erkennungszähler sowie Laufzeiten. Ein letzter Java-Absturz wird lokal mit Ausnahme-Klasse und höchstens acht eigenen Code-Stackframes gespeichert, ohne Fehlermeldung. Native Abstürze werden dadurch nicht zuverlässig erfasst. Der übrige Bericht existiert nur während der App-Sitzung. **Keine Fotos, Bilddaten oder Gesichtspunkte werden im Bericht gespeichert oder automatisch versendet.** Der Nutzer sieht den Bericht vor dem Kopieren/Teilen; andere Apps, an die er ihn sendet, unterliegen deren eigenen Datenschutzbedingungen.

## Modell und Lizenz

Die Modellgewichte sind weder im Repository noch in der APK. Die App lädt genau `face_landmarker/float16/1/face_landmarker.task` von Google und akzeptiert nur SHA-256 `64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff`. Der Download ist auf 10 MiB begrenzt; kaputte oder unvollständige Dateien werden nicht verwendet. Dateien liegen im privaten App-Speicher. Sollte Google den Inhalt ändern, scheitert die Integritätsprüfung statt ein anderes Modell zu laden.

Die Modellkarte und die Google-AI-Edge-Bedingungen sind nach [`docs/09`](../../docs/09-recht-compliance.md) **noch nicht schriftlich geprüft**. Der Test-Download ist keine Lizenzfreigabe; die Prüfung bleibt vor einer Weitergabe bzw. produktiven Nutzung zu erledigen.

## Build und Tests

Der Workflow [`.github/workflows/apk.yml`](../../.github/workflows/apk.yml) testet die Kotlin-Komponenten und baut die Debug-APK. Auf dem GitHub-Runner kann zusätzlich ein Test-Release erzeugt werden:

```sh
gh workflow run apk.yml --ref arena/ee31e880-facescan -f release=true
```

Die Unit-Tests prüfen u. a. Cache-Wiederverwendung, fehlerhafte Prüfsummen, Größenbegrenzung, Download-Fehler, Frame-Timing und den Schutz vor verspäteter Kamera-Bindung.

Der separate Workflow [Android-Emulatortest](../../.github/workflows/android-device-test.yml) prüft auf Android 11 mit x86-Emulator: Erststart ohne Netz, tatsächlichen Download und Integrität, Inferenz auf einem schwarzen Testbild, Bericht und Kopierfunktion, Offline-Start mit Modell-Cache sowie Kameraframes aus der emulierten Frontkamera. Dabei werden auch der synthetische F1/F2-Geometrietest, die geführten Tests und die Berechtigungsseite geprüft. Künstliche Bilder ersetzen weder ein menschliches Gesicht noch einen Test auf echter Hardware. Ein Gerätetest einschließlich Erkennungsqualität und manuellem Teilen bleibt erforderlich.

MediaPipe 0.10.14 enthält native Bibliotheken für `arm64-v8a`, `armeabi-v7a` und `x86`, aber nicht für `x86_64`. Die APK ist deshalb auf diese drei ABIs begrenzt; ein x86-64-Gerät benötigt 32-Bit-x86-Unterstützung. Reine x86-64-Geräte ohne x86-Unterstützung werden nicht unterstützt. Ein CI-Check verhindert, dass eine nicht passende ABI-Auswahl versehentlich ausgeliefert wird.
