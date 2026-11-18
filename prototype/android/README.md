# FaceScan – Android-Prototyp

## Aktueller Stand

**Die App ist eine Demo, kein funktionsfähiger Gesichtsscan.** Der Aufnahmebildschirm zeigt die Kameravorschau, übergibt aber noch keine Frames an die Gesichtserkennung. Fortschritt und Qualitätsbericht sind simuliert. Es wird kein persönliches 3D-Modell erstellt; Animation und Export sind noch nicht implementiert. Ein eingebettetes MediaPipe-Modell allein ändert daran nichts.

Die Mathematik-Komponenten sind durch Unit-Tests und Referenzdaten geprüft, der vollständige Ablauf aber noch nicht auf einem Gerät verifiziert. Die Kamera-Berechtigungsbehandlung ist ebenfalls noch nicht fertig: Bei Ablehnung wird der weitere Ablauf derzeit nicht zuverlässig blockiert.

## Test-APK

[Test-APK #19 herunterladen](https://github.com/AndrexTheDev/FaceScan/releases/tag/test-apk-19): `app-debug.apk`, rund 80 MiB, Android 10 oder neuer. Es handelt sich um einen Debug-Build, nicht um ein Produktiv-Release. Diese ältere APK kennzeichnet den Demo-Zustand **noch nicht** ausreichend in der Oberfläche; sie erstellt kein Modell, auch wenn der Bildschirm anderes suggeriert.

Zum Installieren die APK auf das Android-Gerät laden und bei Bedarf die Installation aus dieser Quelle in den Android-Einstellungen erlauben. Die Kamera-Berechtigung nur erteilen, wenn die Kameravorschau getestet werden soll. Im Manifest ist keine `INTERNET`-Berechtigung eingetragen; ein tatsächlicher Offline-Gerätetest steht noch aus.

### Vorschlag für einen ersten Gerätetest

1. Gerät, Android-Version und APK-Version notieren; APK installieren und starten.
2. Kamera erlauben und prüfen, ob die Frontkamera-Vorschau erscheint. Demo durchlaufen und wieder verlassen. **Kein echtes Scanergebnis erwarten.**
3. App neu starten; zusätzlich testen, wie sie sich nach dem Entzug der Kamera-Berechtigung verhält. Fehler und Abstürze dokumentieren; die Behandlung ist noch unvollständig.
4. Optional im Flugmodus wiederholen. Kameravorschau, Navigation und etwaige Fehler dokumentieren; daraus keine Aussage über eine noch nicht implementierte Rekonstruktion ableiten.

## Modell und Lizenz

Die Gewichte `face_landmarker.task` sind nicht im Repository. Der Workflow lädt sie nur bei explizitem `modell=true` herunter und bettet sie dann in die APK ein. Der Standard ist `false`; ohne Modell könnte die spätere Gesichtserkennung nicht initialisiert werden. Der aktuelle Demo-Ablauf ruft sie noch nicht auf.

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
