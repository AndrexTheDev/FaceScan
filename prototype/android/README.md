# FaceScan – Android-Test-App

Die Test-App dient dazu, **Kameravorschau und experimentelle Gesichtserkennung auf einem echten Android-Gerät zu prüfen** und einen technischen Bericht freiwillig zu teilen. Sie erstellt noch kein 3D-Modell; Rekonstruktion, Animation und Export sind nicht implementiert. Der Erkennungsweg wurde bisher nicht auf einem Gerät verifiziert. Ein grüner CI-Build ersetzt diesen Test nicht.

## Installation und erster Test

Die neueste Test-APK liegt bei den [GitHub-Releases](https://github.com/AndrexTheDev/FaceScan/releases). Dort `app-debug.apk` herunterladen und auf Android 10 oder neuer installieren. Es ist ein Debug-Build. Wenn Android ein Update wegen abweichender Debug-Signatur ablehnt, die ältere Testversion erst deinstallieren (dabei werden ihre App-Daten gelöscht) und dann die neue APK installieren.

1. Vor dem ersten Start Internet aktivieren. Die App lädt die einzige zur Laufzeit benötigte Modelldatei automatisch von Google (rund 3,6 MB) herunter und prüft deren SHA-256. Der übrige Anwendungscode und die Bibliotheken sind in der APK. Die App meldet, ob das Modell bereit ist; bei einem Fehler Verbindung prüfen und **Erneut versuchen** antippen.
2. **Kameratest starten**, den Hinweis lesen und die Kamera erlauben. Das Gesicht einige Sekunden ins Bild halten und dann aus dem Bild bewegen. Die Anzeige sollte zwischen „Gesicht erkannt“ und „kein Gesicht erkannt“ wechseln. Der Test ist experimentell und kann auch fehlschlagen.
3. **Testbericht** öffnen. Er zeigt die tatsächlichen Diagnose-Daten vor dem Teilen. **Kopieren** antippen und den Text in den Chat einfügen oder bewusst mit **Teilen** versenden. Bei einem Absturz die App erneut öffnen und den Bericht auf dem Startbildschirm abrufen.
4. Nach erfolgreicher Einrichtung Flugmodus aktivieren, App neu starten und den Kameratest wiederholen. Das bereits geprüfte Modell wird lokal wiederverwendet. Bitte auch beschreiben, was sichtbar war und an welcher Stelle ein Fehler auftrat.
5. Optional: Kamera-Berechtigung verweigern oder in den Systemeinstellungen entziehen, App wieder öffnen und Reaktion berichten. Ein Debug-Build kann geräteabhängig abweichen.

## Datenschutz und Netzwerk

Der erstmalige Modell-Download nutzt HTTPS zu `storage.googleapis.com`. Dabei sieht Google die IP-Adresse des Geräts; Mobilfunkkosten können anfallen. Die App benötigt dafür `INTERNET`. Nach der Installation wird bei erfolgreicher Integritätsprüfung kein erneuter Modell-Download ausgeführt; die Gesichtserkennung läuft lokal. Diese Aussage betrifft den implementierten Anwendungspfad, nicht eine bereits auf jedem Gerät bestätigte Netzwerkmessung.

Der Bericht enthält App-Version, Hersteller und Modell des Geräts, Android-Version, Kamera-Berechtigung, Modellstatus, Fehlerklassen, Kamerabildformat, aggregierte Frame- und Erkennungszähler sowie Laufzeiten. Ein letzter Java-Absturz wird lokal mit Ausnahme-Klasse und höchstens acht eigenen Code-Stackframes gespeichert, ohne Fehlermeldung. Native Abstürze werden dadurch nicht zuverlässig erfasst. Der übrige Bericht existiert nur während der App-Sitzung. **Keine Fotos, Bilddaten oder Gesichtspunkte werden im Bericht gespeichert oder automatisch versendet.** Der Nutzer sieht den Bericht vor dem Kopieren/Teilen; andere Apps, an die er ihn sendet, unterliegen deren eigenen Datenschutzbedingungen.

## Modell und Lizenz

Die Modellgewichte sind weder im Repository noch in der APK. Die App lädt genau `face_landmarker/float16/1/face_landmarker.task` von Google und akzeptiert nur SHA-256 `64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff`. Der Download ist auf 10 MiB begrenzt; kaputte oder unvollständige Dateien werden nicht verwendet. Dateien liegen im privaten App-Speicher. Sollte Google den Inhalt ändern, scheitert die Integritätsprüfung statt ein anderes Modell zu laden.

Die Modellkarte und die Google-AI-Edge-Bedingungen sind nach [`docs/09`](../../docs/09-recht-compliance.md) **noch nicht schriftlich geprüft**. Der Test-Download ist keine Lizenzfreigabe; die Prüfung bleibt vor einer Weitergabe bzw. produktiven Nutzung zu erledigen.

## Build und Tests

Der Workflow [`.github/workflows/apk.yml`](../../.github/workflows/apk.yml) testet die Kotlin-Komponenten und baut die Debug-APK. Auf dem GitHub-Runner kann zusätzlich ein Test-Release erzeugt werden:

```sh
gh workflow run apk.yml --ref arena/ee31e880-facescan -f release=true
```

Die Unit-Tests prüfen u. a. Cache-Wiederverwendung, fehlerhafte Prüfsummen, Größenbegrenzung, Download-Fehler, Frame-Timing und den Schutz vor verspäteter Kamera-Bindung. Ein Gerätetest für Download, Kamera, Gesichtserkennung und Teilen bleibt erforderlich.
