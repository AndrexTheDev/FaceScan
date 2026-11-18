# Externer 3D-Vergleich mit unabhängigen Kontrollpunkten

Dieser Offline-Vergleich misst **nicht von selbst die reale Genauigkeit**. Dafür braucht er echte, mit Einwilligung erhobene Referenzdaten eines ausreichend genauen 3D-Referenzsystems und zuverlässige Korrespondenzen. Keine Beispielzahlen dürfen als Messergebnis ausgegeben werden. Die eingebaute Test-Suite benutzt nur künstliche Daten.

1. Aus der App das neutrale OBJ exportieren. Es enthält 468 Landmark-Vertices in MediaPipe-Reihenfolge (CSV-Indizes 0–467; OBJ-Indizes sind 1–468). Keine automatische Korrespondenzsuche: Die 3D-Punkte müssen im **selben neutralen Ausdruck** auf der externen Referenzoberfläche eindeutig und reproduzierbar markiert werden. Dabei nur tatsächlich sichtbare Flächen vergleichen, nicht Haare/Hinterkopf.
2. Lokale CSV mit den Spalten `landmark,x_mm,y_mm,z_mm,role` erstellen. Koordinaten gehören zum selben Referenzkoordinatensystem in Millimetern. Jeden Landmark-Index nur einmal verwenden. Rolle ist exakt `fit` oder `holdout`; mindestens 4 räumlich verteilte Fit-Punkte und 3 getrennte Holdout-Punkte. Mehr räumlich breit verteilte Punkte sind nötig, um ein aussagekräftiges Urteil zu erhalten.
3. Mit Python 3 und NumPy lokal ausführen:

   ```sh
   python prototype/reference/validation/compare_landmarks.py neutral.obj referenz.csv --output vergleich.json
   ```

Die angepasste Ähnlichkeitstransformation (Rotation ohne Spiegelung, Translation, positive Skala) wird **ausschließlich** auf Fit-Punkten geschätzt. Die zurückgehaltenen Punkte gehen nicht in den Fit ein. Für beide Gruppen stehen Anzahl, Mittelwert, Median, RMS, p95 und Maximum des 3D-Punktabstands in Millimetern im Ergebnis. Das Ergebnis enthält keine individuellen Koordinaten, aber ist immer noch ein potenziell sensibler personen- bzw. gerätebezogener Prüfbericht. Es wird nicht automatisch verschickt.

**Interpretation:** Weil Skala und Lage anhand der Referenz angepasst werden, ist der Holdout-Fehler ein Formvergleich *nach* Referenzkalibrierung. Er belegt weder eine unabhängig metrisch kalibrierte App noch die Messgüte von Referenzgerät oder Markierung. Registrierungs- und Zuordnungsfehler, Gesichtsausdruck, verdeckte Punkte, Gesichtsbewegungen, Geräteeigenschaften und demografische Bandbreite müssen separat untersucht und dokumentiert werden. Ohne Ground Truth oder ohne unabhängige Holdout-Punkte keine Millimeter-Genauigkeit behaupten.

Tests (ohne reale Daten):

```sh
python -m unittest discover -s prototype/reference/validation -v
```
