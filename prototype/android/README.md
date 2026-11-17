# FaceScan – Test-APK

Stand: APK baut in der CI ([`.github/workflows/apk.yml`](../../.github/workflows/apk.yml)),
beide Jobs grün.

## Herunterladen und installieren

Die APK liegt am Release des jeweils letzten Laufs:

    https://github.com/AndrexTheDev/FaceScan/releases

Dort `app-debug.apk` antippen (etwa **80 MB**).

1. Auf dem Handy: **Einstellungen → Sicherheit → Unbekannte Quellen** für den
   Browser erlauben (Android fragt beim Installieren von selbst danach).
2. APK antippen und installieren.
3. Beim ersten Start die **Kameraerlaubnis** geben.
4. **NEU SCANNEN** antippen.

Voraussetzung: **Android 10 oder neuer** (`minSdk 29`).
Die App braucht keine Internetverbindung (die Kamera ist die einzige
Hardware, auf die sie zugreift; im Manifest ist ausdrücklich keine
`INTERNET`-Berechtigung eingetragen).

## Was in der App passiert

| Schritt | Anzeige | Bedeutung |
|---|---|---|
| Aufnahme | „Perfekt – bleib so." | Kamera läuft, Gesichtspunkte werden erkannt |
| Verarbeitung | „Gesichtspunkte erkennen" → „Kameraposen berechnen" → „Kopfform anpassen" → „Details verfeinern" | Pose und 3D-Modell werden gerechnet |
| Ergebnis | „Dein 3D-Modell" | Modell ansehen, animieren, exportieren |

## Warum die APK 80 MB groß ist

| Anteil | Größe |
|---|---|
| MediaPipe-Nativcode (4 Architekturen) | 42,1 MB |
| Java/Kotlin-Bytecode (mehrere dex-Dateien, R8 aus) | 34 MB |
| `face_landmarker.task` (Modellgewichte) | 3,6 MB |

Ein Debug-Bau schrumpft nicht und enthält alle vier Architekturen; beim
Installieren nutzt das Handy davon nur die passende. Ein Release-Bau mit
R8 und nur einer Architektur wäre deutlich kleiner.

## Bekannte Grenzen

- **Debug-Signatur.** Nur zum Testen, nicht zum Weitergeben.
- **Modellgewichte sind nicht eingecheckt.** `docs/09` verlangt für die
  MediaPipe-Modelle eine schriftliche Prüfung von Modellkarte und
  Google-AI-Edge-Bedingungen *vor* dem Einbau; der Prüfstatus ist dort
  **offen**. Die Datei wird beim Bauen heruntergeladen (Schalter
  `modell`, Standard **aus**) und liegt deshalb nie im Repository —
  siehe `.gitignore`. Ohne sie baut die App und startet auch, aber der
  erste Scan bricht ab.
- **Der Prototyp ist nicht auf einem Gerät gelaufen.** Kompiliert und
  unit-getestet ist er; die Bedienung auf echter Hardware ist der
  nächste Schritt.

## Neu bauen

Die APK entsteht **ausschließlich in GitHub Actions** — in der
Entwicklungsumgebung gibt es kein Java, kein Gradle und kein Android-SDK.

    gh workflow run apk.yml -f modell=true -f release=true

| Eingabe | Wirkung |
|---|---|
| `modell` | `face_landmarker.task` einbetten (Standard: aus) |
| `release` | zusätzlich ein GitHub-Release anlegen (Standard: aus) |

Der Workflow meldet von selbst, ob die gebaute APK scannen kann; ohne
Modell steht in den Annotations ausdrücklich, dass der erste Scan
abbricht.

Zwei Eigenheiten der Umgebung, die man kennen muss, wenn man den Workflow
ändern will:

- **`sdkmanager` liegt nicht auf dem PATH** (Exit 127, kein
  `cmdline-tools`). Das SDK ist auf dem Runner ohnehin vollständig
  vorhanden (bis `android-37.2`); es wird nur geprüft, nicht installiert.
- **Logs und Artefakte sind aus der Entwicklungsumgebung nicht abrufbar**
  (`results-receiver.actions.githubusercontent.com` ist gesperrt).
  Fehlermeldungen kommen deshalb als `::error::` / `::notice::` in die
  Annotations.

## Die Bibliothek

`com.google.mediapipe:tasks-vision:0.10.14`. Die Java-API weicht an zwei
Stellen von der Doku auf developers.google.com ab — die Doku beschreibt
eine neuere Version. Maßgeblich ist
[`FaceLandmarkerResult.java` im Tag v0.10.14](https://raw.githubusercontent.com/google-ai-edge/mediapipe/v0.10.14/mediapipe/tasks/java/com/google/mediapipe/tasks/vision/facelandmarker/FaceLandmarkerResult.java):

```java
List<List<NormalizedLandmark>> faceLandmarks();               // kein Optional
Optional<List<List<Category>>> faceBlendshapes();             // nicht Classifications
Optional<List<float[]>>        facialTransformationMatrixes(); // nicht Matrix
```

Die Einzelheiten stehen im Kopf von `FaceLandmarkerRunner.kt`.
