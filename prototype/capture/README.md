# Aufnahme-Assistent (`prototype/capture/`)

Ein Wizard, der die Daten einsammelt, die zum Weiterbauen mit **echten**
Werten fehlen: die Kalibrierung (F-402) und Aufnahmen echter Mimik.

Er läuft **im Browser auf dem Telefon** — keine Installation, kein APK.

## Warum keine APK

Eine APK kann in dieser Umgebung nicht entstehen, und das ist keine Frage
des Wollens:

| Voraussetzung | hier |
|---|---|
| Java / JDK | nicht vorhanden |
| Gradle | nicht vorhanden |
| Android-SDK | nicht vorhanden |
| `dl.google.com` (um das SDK zu holen) | gesperrt |

Eine Web-App kann dafür alles, was dieser Wizard braucht: Kamera
(`getUserMedia`), Lage-Sensoren (`DeviceOrientationEvent`) und Rechnung auf
dem Gerät. Sie läßt sich über „Zum Home-Bildschirm hinzufügen" wie eine App
ablegen und startet dann ohne Browser-Leisten.

**Vorteil nebenbei:** das Gesichtsmodell wird auf dem Telefon geladen —
`storage.googleapis.com` ist in dieser Umgebung gesperrt, auf deinem Handy
nicht. Genau solche Daten kann ich also hier nicht beschaffen und dort schon.

## Starten

```
cd prototype/capture && python3 -m http.server 8080 --bind 0.0.0.0
```

Dann im Telefon-Browser die Vorschau-Adresse öffnen (https!, sonst gibt der
Browser die Kamera nicht frei).

Wird `vendor/` beim Klonen nicht mitgeliefert (es steht in `.gitignore`,
29 MB):

```
cd prototype/capture && npm pack @mediapipe/tasks-vision@1.2.3 \
  && tar xzf mediapipe-tasks-vision-1.2.3.tgz \
  && mkdir -p vendor && cp package/vision_bundle.mjs vendor/ \
  && cp -r package/wasm vendor/ && rm -rf package *.tgz
```

## Was der Wizard aufzeichnet

Neun Schritte, Dauern nach `docs/04` (2.3), Texte für Laien:

| Schritt | Dauer | Zweck |
|---|---|---|
| Ruhe | 3 s | `s_neutral` je Kanal |
| Lächeln, Augen zu, Brauen hoch, Brauen runter, Mund auf, Kussmund, Wangen aufblasen | je 2 s | `s_max` je Kanal |
| Kopf drehen | 4 s | Kopfhaltung für die Geometrie |

Je Bild: 52 Mimik-Werte, 478 Messpunkte, die 4×4-Kopfmatrix und die
Telefonlage. Das Ergebnis ist eine JSON-Datei mit der vollständigen
Kalibrierung — genau das, was `rig/blendshape_calib.json` im `.fscan`
braucht und was dort bisher fehlt.

## Wo die Daten bleiben

**Auf dem Telefon.** Es gibt keinen Upload. Erst wenn du am Ende auf
„Sichern" tippst, entsteht eine Datei in „Downloads" — und die schickst du
mir erst, wenn du willst.

## Vier Entscheidungen

1. **Anzeige gespiegelt, Rechnung nicht.** Eine Selfie-Ansicht spiegelt man,
   sonst wirkt sie falsch. MediaPipe warnt aber ausdrücklich: ein
   gespiegeltes Bild vertauscht links und rechts in den Mimik-Werten
   (`*Left`/`*Right` zählen von der Seite der Person). Gespiegelt wird
   deshalb nur per CSS.
2. **Zahlen binär, nicht als Text.** 478 Punkte × 3 Zahlen × 30 Bilder je
   Sekunde wären als JSON in einer Minute zweistellig megabytegroß. Als
   int16 sind es 2,9 kB je Bild. Das Layout steht in `app.js` unter
   `FORMAT` und wird von `tools/lese_capture.py` gelesen.
3. **Ein Füllbyte vor den Punkten.** Eine `Int16Array`-Sicht verlangt einen
   geraden Byte-Offset und wirft sonst. Bei 52 Kanälen geht die Rechnung
   zufällig auf, bei 53 nicht — und ob das Modell 52 oder 53 liefert, steht
   in dessen Datei. Lieber ein Byte verschenken.
4. **Der Größtwert ist ein 95er-Perzentil, kein Maximum.** Ein einzelnes
   verreißtes Bild würde als Maximum die ganze Kalibrierung nach oben ziehen.
   Das Perzentil nimmt den Wert, den der Nutzer wirklich durchgehend erreicht.

## Was ich prüfen konnte — und was nicht

Geprüft:

* `app.js` ist syntaktisch fehlerfrei (als ES-Modul, `node --check`).
* Die MediaPipe-API (`FaceLandmarker`, `detectForVideo`, `faceBlendshapes`,
  `facialTransformationMatrixes`) steht so in den Typdefinitionen von
  `@mediapipe/tasks-vision` 1.2.3 — nicht geraten, nachgeschlagen.
* Die WASM-Runtime liegt vollständig in `vendor/wasm/`.
* Der Rundweg des Binärformats: aus Python geschrieben, vom Leser
  zurückgeholt. Fehler: Zeit 1,1e-07 (float32), Mimik 0,00196 — **genau eine
  halbe Stufe** —, Punkte verlustfrei. Für 52 und 53 Kanäle.

**Nicht** geprüft — dafür brauche ich dich:

* Ob die Kamera auf deinem Telefon wirklich aufgeht.
* Ob das Modell von den Google-Servern lädt.
* Ob die Aufnahme in der Praxis durchläuft.

Ich habe hier keine Kamera und keinen Browser. Ich kann die Seite ausliefern
und ihren Code prüfen; ob sie auf deinem Gerät tut, kannst nur du sehen.

## Rechtliches

`face_landmarker.task` ist Apache-2.0 beim **Code**. Für die **Modelldatei**
gilt eine eigene Modellkarte mit Google-AI-Edge-Bedingungen — und
`docs/09` führt genau diesen Punkt als **offen**: „vor Einbau schriftlich
prüfen". Für einen Aufnahme-Test ist das unkritisch. Bevor das Modell in ein
ausgeliefertes Produkt wandert, muß das geklärt sein.
