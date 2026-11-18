# FaceScan – Android-Prototyp

## Aktueller Stand

**Die App ist eine Demo, kein funktionsfähiger 3D-Gesichtsscan.** Der Aufnahmebildschirm leitet Kamerabilder experimentell an MediaPipe weiter und zeigt nur „Gesicht erkannt“ bzw. „kein Gesicht erkannt“ an. Das benötigt ein eingebettetes Modell und ist noch nicht auf einem Gerät verifiziert. Ohne Modell bleibt die Vorschau nutzbar und meldet den fehlenden Baustein. Die Erkennung speichert keine Bilder oder Gesichtspunkte. Der anschließende Verarbeitungsfortschritt und Qualitätsbericht sind simuliert; es wird kein persönliches 3D-Modell erstellt. Animation und Export sind nicht implementiert.

Die Mathematik-Komponenten sind durch Unit-Tests und Referenzdaten geprüft, der vollständige Ablauf aber noch nicht auf einem Gerät verifiziert. Für die Vorschau wird die Kamera-Berechtigung erst nach einer Erklärung angefragt. Bei Ablehnung bleibt die Vorschau gesperrt; ein Weg zurück und ein Link zu den App-Einstellungen sind vorgesehen. Das Verhalten ist noch nicht auf einem Gerät verifiziert.

## Test-APK

[Test-APK #19 herunterladen](https://github.com/AndrexTheDev/FaceScan/releases/tag/test-apk-19): `app-debug.apk`, rund 80 MiB, Android 10 oder neuer. Es handelt sich um einen Debug-Build, nicht um ein Produktiv-Release. Diese ältere APK enthält weder die hier beschriebene Berechtigungsbehandlung noch die experimentelle Gesichtserkennung oder eine ausreichende Demo-Kennzeichnung in der Oberfläche; sie erstellt kein Modell, auch wenn der Bildschirm anderes suggeriert.

Zum Installieren die APK auf das Android-Gerät laden und bei Bedarf die Installation aus dieser Quelle in den Android-Einstellungen erlauben. Die Kamera-Berechtigung nur erteilen, wenn die Kameravorschau getestet werden soll. Im Manifest ist keine `INTERNET`-Berechtigung eingetragen; ein tatsächlicher Offline-Gerätetest steht noch aus.

### Vorschlag für einen ersten Gerätetest

1. Gerät, Android-Version und APK-Version notieren; APK installieren und starten.
2. Kamera erlauben und prüfen, ob die Frontkamera-Vorschau erscheint. Ohne eingebettetes Modell muss „Modell fehlt“ erscheinen. Mit Modell: Gesicht ins Bild und wieder heraus bewegen; die Anzeige sollte zwischen „Gesicht erkannt“ und „kein Gesicht erkannt“ wechseln. Das auf Geräten mit unterschiedlicher Kameradrehung prüfen. Weiter zur Demo: **kein echtes 3D-Scanergebnis erwarten**.
3. App neu starten und Berechtigung verweigern: keine Vorschau, stattdessen Erklärung und Rückweg. Erneute Anfrage und nach wiederholter Ablehnung die App-Einstellungen testen. Nach Entzug bzw. Erteilung in den Einstellungen zurückkehren und prüfen, dass sich die Anzeige aktualisiert. Fehler und Abstürze dokumentieren.
4. Kamera-Vorschau schnell öffnen und abbrechen sowie erneut öffnen; App während der Erkennung in den Hintergrund schicken und zurückholen. Prüfen, dass die Anzeige nach Pausen nicht dauerhaft eine alte Erkennung zeigt und dass die Kamera wieder freigegeben wird. Fehler und Abstürze dokumentieren.
5. Optional im Flugmodus wiederholen. Kameravorschau, Navigation und etwaige Fehler dokumentieren; daraus keine Aussage über eine noch nicht implementierte Rekonstruktion ableiten.

## Modell und Lizenz

Die Gewichte `face_landmarker.task` sind nicht im Repository. Der Workflow lädt sie nur bei explizitem `modell=true` herunter und bettet sie dann in die APK ein. Der Standard ist `false`; ohne Modell ist die experimentelle Gesichtserkennung nicht verfügbar. Dies wird in der Aufnahme angezeigt, ohne die Demo zu blockieren.

Die Prüfung der Modellkarte und Google-AI-Edge-Bedingungen ist in [`docs/09`](../../docs/09-recht-compliance.md) **offen**. Vor einer Weitergabe oder anderweitigen Nutzung der Gewichte muss die Prüfung abgeschlossen und dokumentiert werden. Das Modell in der verlinkten APK ist bereits eingebettet; das ist keine Lizenzfreigabe.

## Build

Der Workflow [`.github/workflows/apk.yml`](../../.github/workflows/apk.yml) baut und testet den Prototyp auf GitHub Actions. In dieser Entwicklungsumgebung stehen Java, Gradle und Android-SDK nicht zur Verfügung.

```sh
gh workflow run apk.yml --ref arena/ee31e880-facescan -f modell=false -f release=true
```

`release=true` erstellt zusätzlich ein GitHub-Release. `modell=true` bettet die separat heruntergeladenen Gewichte ein; Lizenzprüfung beachten. Der Kurzbericht prüft nur, ob das Asset in der APK enthalten ist, und bescheinigt keine Scanbereitschaft.

Die große Debug-APK enthält Bibliotheken für vier Architekturen und ungeschrumpften Bytecode. Beispiel #19: rund 42 MiB native Bibliotheken, 34 MB DEX und 3,6 MB Modell; diese Anteile beziehen sich auf den entpackten Inhalt und sind nicht direkt mit der APK-Dateigröße vergleichbar.

## MediaPipe-Version

Verwendet wird `com.google.mediapipe:tasks-vision:0.10.14`. Die Java-Signaturen im [Quelltext dieser Version](https://github.com/google-ai-edge/mediapipe/blob/v0.10.14/mediapipe/tasks/java/com/google/mediapipe/tasks/vision/facelandmarker/FaceLandmarkerResult.java) sind maßgeblich; die Dokumentation kann eine andere Version beschreiben. Einzelheiten stehen in `FaceLandmarkerRunner.kt`.
