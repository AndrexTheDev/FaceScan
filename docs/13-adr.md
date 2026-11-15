# 13 – Architecture Decision Records (ADR)

Stand: 2026-11-15 · Format: ADR-Nr., Status, Kontext, Entscheidung, Konsequenzen

---

### ADR-001 · Kein ARCore
**Status:** beschlossen
**Kontext:** ARCore würde Kameraposen, Tiefendaten und Tracking liefern – ist aber eine Abhängigkeit von
Google Play Services, nicht auf allen Geräten verfügbar, und der Auftrag lautet ausdrücklich „ohne ARCore".
**Entscheidung:** Kameraposen werden per **EPnP/RANSAC aus 478 Face-Landmarks** plus Camera2-Intrinsics
bestimmt; die metrische Skala kommt aus dem kanonischen Gesichtsmodell + Brennweite in Pixel.
**Konsequenz:** Keine Play-Services-Abhängigkeit, kein SLAM-Drift, geringere APK-Größe, volle
Geräteunabhängigkeit. Preis: Wir brauchen ein gut funktionierendes Gesichts-Tracking (gegeben) und können
keine beliebigen Objekte scannen (nicht gefordert).

### ADR-002 · Native Kotlin + C++-Kern statt Flutter/React Native/Unity
**Status:** beschlossen
**Kontext:** Volle Kontrolle über Camera2, Vulkan-Compute, Speicherbudget, 16-KB-Page-Size und Export-Writer.
**Entscheidung:** Kotlin/Compose für UI und Domain, C++17 für Geometrie/Export, JNI dazwischen.
**Konsequenz:** Höherer Entwicklungsaufwand, dafür beste Performance, keine Engine-Lizenz, keine
Fremd-Runtime. Der C++-Kern läuft in einem eigenen Prozess (OOM-Isolation).

### ADR-003 · MediaPipe Tasks als Wahrnehmungsschicht
**Status:** beschlossen
**Kontext:** Eigene Netze wären Monate an Arbeit und bräuchten Trainingsdaten mit kommerziell sauberer
Lizenz. MediaPipe liefert on-device, Apache-2.0: 478 Landmarks, 52 ARKit-Blendshapes, 4×4-Kopfpose,
33-Körper-Landmarks in Metern, Haar-Segmentierung.
**Entscheidung:** MediaPipe Tasks (Face/Pose/Hand Landmarker, Image Segmenter) verwenden.
**Konsequenz:** Enorme Zeitersparnis, sofortige ARKit-Kompatibilität. **Offener Punkt:** Modellkarten/
Nutzungsbedingungen der Gewichte vor Einbau schriftlich prüfen (Code ist Apache-2.0).

### ADR-004 · Eigene 3DMM statt FLAME/Basel/ICT-FaceKit
**Status:** beschlossen
**Kontext:** FLAME ist forschungs-lizenziert („any use for commercial … purposes is prohibited"), Basel
ebenfalls, ICT-FaceKit nennt MIT, spricht aber von einer „non-commercial version".
**Entscheidung:** Eigene 3DMM aus eigenen, schriftlich lizenzierten Aufnahmen (20–100 Personen, Opt-in mit
ausdrücklicher Modellnutzungsklausel). Bis dahin: Morphing-Gerüst aus dem MediaPipe-Kanonmodell +
registrierungsbasierte Verfeinerung.
**Konsequenz:** Höherer Anfangsaufwand und die Qualität steigt mit der Datenmenge; dafür vollständige
kommerzielle Freiheit, kein Rechtsrisiko und ein eigener Unternehmenswert.

### ADR-005 · Eigene Export-Writer statt Assimp
**Status:** beschlossen
**Kontext:** Assimp (BSD-3) kann exportieren, aber **kein binäres FBX** (nur ASCII, das Blender seit 2.8
nicht mehr importiert) und keine Displacement-/Morph-Details in der von uns benötigten Form.
**Entscheidung:** Eigene Writer (C++) auf Basis eines gemeinsamen `SceneIR`. Assimp/Blender/Open3D nur in
der **Test-Toolchain**.
**Konsequenz:** Volle Kontrolle, deterministische Ausgaben, Golden-File-Tests. Aufwand für FBX binär ist
erheblich (Welle 3) – mit ABC als dokumentiertem Ausweichweg.

### ADR-006 · FBX binär selbst schreiben (nicht ASCII, nicht FBX-SDK)
**Status:** beschlossen (mit Risikovermerk)
**Kontext:** Das Autodesk-FBX-SDK darf nicht weitergegeben werden; ASCII-FBX wird von Blender ab 2.8 nicht
mehr importiert; FBX ist aber das wichtigste Austauschformat für Maya/Max/Blender/Unity/Unreal.
**Entscheidung:** Eigener Writer für **FBX 7.5 binär**, entwickelt aus öffentlichen Formatbeschreibungen
und eigenen Round-Trip-Experimenten. **Ausdrücklich verboten:** Abkupfern aus GPL-Quelltext (Blender-FBX-
Exporter). Gegen eine feste Validierungsmatrix geprüft.
**Konsequenz:** Höchstes Einzelrisiko im Export-Bereich. Gegenmaßnahmen: ABC/USD als Fallback, automatisierte
Round-Trip-Tests, manuelle Freigabe je Release, ehrliche Kommunikation in der App.

### ADR-007 · USD als USDA/USDZ (kein USD-SDK, kein USDC in v1)
**Status:** beschlossen
**Kontext:** Das USD-SDK (Boost, TBB, OpenSubdiv, MaterialX) für Android zu bauen, ist ein eigenes Projekt.
**Entscheidung:** Wir schreiben **USDA (ASCII)** selbst und verpacken **USDZ** nach den offiziellen
Packaging-Regeln (alle Einträge unkomprimiert, 64-Byte-Alignment, kein Passwort). USDC (binär) erst mit dem
geplanten Desktop-Begleitprogramm.
**Konsequenz:** USDA/USDZ sind in Blender, Houdini, Apple-Geräten und Unreal-Interchange nutzbar; Dateien
sind größer als USDC. Für die meisten Anwendungsfälle akzeptabel.

### ADR-008 · Offline-First schlägt Kopierschutz
**Status:** beschlossen
**Kontext:** Signierte Lizenzdateien sind kopierbar; jeder Online-Zwang würde das Kernversprechen brechen.
**Entscheidung:** Lokal signierte Quittung (Ed25519) + On-Chain-Tx als Identitätsanker; Online-Nachprüfung
nur alle 30 Tage mit 90 Tagen Grace; Gerätebindung; Wiederherstellung über Tx-Hash.
**Konsequenz:** Ein gewisses Maß an Piraterie wird akzeptiert; dafür maximaler Nutzen für ehrliche Kunden,
keine Serverkosten, keine Ausfälle. Ausgleich über Bequemlichkeit, Preis und Updates.

### ADR-009 · SOL als Hauptzahlungsweg, BTC/ETH über Betrags-Fingerprint
**Status:** beschlossen
**Kontext:** Eine Adresse pro Kette ohne Custody ⇒ Zuordnung muss aus der Transaktion selbst kommen.
**Entscheidung:** SOL nutzt Solana-Pay-Referenz-Keys (`getSignaturesForAddress(reference)`); BTC/ETH nutzen
einen eindeutigen Betrags-Offset (plus optionales Memo) und 2-von-3-Endpoint-Verifikation; immer ein
manueller Tx-ID-Pfad als Rückfall.
**Konsequenz:** SOL ist komfortabel und schnell, BTC/ETH funktionieren, brauchen aber Disziplin beim
„exakten Betrag". Klare UI-Kommunikation und ein Support-Pfad sind Pflicht.

### ADR-010 · Keine Konten, keine Cloud, keine Telemetrie im Standard
**Status:** beschlossen
**Kontext:** Zielgruppe ist datenschutzsensibel (Gesichtsdaten), das Produktversprechen ist Offline.
**Entscheidung:** Keine Accounts, keine Server, kein Analytics-Standard, kein Crash-Reporting ohne Opt-in.
**Konsequenz:** Weniger Marketing-Möglichkeiten (keine E-Mail-Liste aus der App), kein server-seitiges
Feature-Flag-System; dafür stärkstes Differenzierungsmerkmal am Markt und minimale Compliance-Last.

### ADR-011 · Haar in drei ehrlichen Stufen statt einem „magischen" Ergebnis
**Status:** beschlossen
**Kontext:** Einzelhaar-Rekonstruktion aus Handy-Fotos ist ungelöst; falsche Erwartungen erzeugen
Enttäuschung und Support-Aufwand.
**Entscheidung:** Haar-Stufen L1 (Cap) / L2 (Karten) / L3 (Strähnen), sichtbar benannt, mit klarer
Kommunikation, welche Formate welche Stufe transportieren können.
**Konsequenz:** Höhere Zufriedenheit, ehrliches Marketing, natürlicher Aufhänger für die Tiers
(L2 = Creator, L3 = Studio).

### ADR-012 · Design: Jamaika-Flagge + Day-Mode, Text auf Grün/Gold immer schwarz
**Status:** beschlossen
**Kontext:** Weiße Schrift auf `#009B3A` erreicht nur 3,65:1 (AA-Fließtext verfehlt); Gold auf Weiß ist mit
1,46:1 unbrauchbar.
**Entscheidung:** Grün/Gold als **Flächen mit schwarzer Schrift**; Day-Mode mit abgedunkeltem Grün
`#007A2E` (5,49:1) und Gold-Text `#8A6A00` (5,07:1); Rot nur für Fehler.
**Konsequenz:** Ein markantes, wiedererkennbares Design, das trotzdem WCAG 2.2 AA erfüllt.

### ADR-013 · Begriffswelt in Laiensprache + „Was ist das?"-Erklärungen
**Status:** beschlossen
**Kontext:** Zielgruppe sind ausdrücklich Einsteiger:innen.
**Entscheidung:** Kein Fachwort ohne Erklärung (Mesh = 3D-Modell, UV = Verpackung, Rig = Skelett …),
Format-Assistent statt Formatauswahl, Ampeln statt Zahlen.
**Konsequenz:** Mehr Aufwand in UX-Texten und Pflege des Glossars (DE/EN) – der wichtigste Hebel gegen
Abbrüche im Onboarding.

### ADR-014 · C2PA-Content-Credentials mit lokal erzeugtem Schlüssel
**Status:** beschlossen (einfache Form in v1)
**Kontext:** Deepfake-Risiko und Nachweispflichten; gleichzeitig Offline-First.
**Entscheidung:** On-Device-Signierung mit selbst-signiertem Zertifikat (C2PA unterstützt Offline-Workflows
ausdrücklich); später optional ein Server-Zertifikat höherer Vertrauensstufe.
**Konsequenz:** Vertrauensgewinn, erfüllt Transparenzerwartungen; selbst-signierte Credentials sind
schwächer – das wird in der App offengesagt.

### ADR-015 · 16-KB-Page-Size und aktuelle targetSdk ab Tag 1
**Status:** beschlossen
**Kontext:** Google Play verlangt 16-KB-Kompatibilität für Apps mit nativen Bibliotheken, die auf Android 15+
zielen; Fristen wurden mehrfach verlängert.
**Entscheidung:** NDK r28+, `ANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON`, keine hartcodierten 4096, alle
vendorten Bibliotheken selbst gebaut.
**Konsequenz:** Kein Zeitdruck kurz vor Release; Nachbau von Fremd-Bibliotheken kostet einmalig Zeit.

### ADR-016 · Kein GPL/AGPL/LGPL-Code im Produkt (Whitelist in der CI)
**Status:** beschlossen
**Kontext:** VCGLib, MeshLab, Teile von CGAL, ältere COLMAP-Versionen und Blender-Quelltext sind
GPL/AGPL – unvereinbar mit einer kommerziellen Closed-Source-App.
**Entscheidung:** Nur Apache-2.0/MIT/BSD/ISC/CC0/zlib (MPL-2 nur unverändert und dynamisch gelinkt). Die CI
bricht bei jeder anderen Lizenz.
**Konsequenz:** Einige bequeme Abkürzungen sind verboten (z. B. VCGLib-Mesh-Ops, Abschreiben des
Blender-FBX-Exporters). Der FBX-Writer entsteht aus öffentlichen Spezifikationen und Eigenexperimenten.

### ADR-017 · Eigene Basistopologie (Basiskopf) selbst erstellen
**Status:** beschlossen
**Kontext:** Templates aus Forschung/Community sind lizenzrechtlich heikel (ICT-FaceKit: „non-commercial
version"; FLAME/BFM: Forschung) oder an Plattformen gebunden (MetaHuman: Unreal-Ökosystem).
**Entscheidung:** Eigene Kopf-/Körper-Topologie (Blender/Skript), ARKit-Namenskonvention, Verträge mit
Freelancern nur mit vollständiger Rechteübertragung. MakeHuman-CC0-Assets nur nach juristischer
Zweitmeinung.
**Konsequenz:** Einmalige Artist-Kosten (3–6 k€), danach volle Freiheit und ein eigenes Asset.

### ADR-018 · Blender-Add-on „FaceScan Link" als GPL-Bridge
**Status:** beschlossen
**Kontext:** Wir können und wollen nicht `.blend` und alle programmeigenen Formate schreiben.
**Entscheidung:** Ein **eigenes, GPL-lizenziertes Blender-Add-on** liest `.fscan` verlustfrei (inkl. Shape
Keys, Rig, Haar-Curves, Maps); von dort kann Blender alles Weitere exportieren.
**Konsequenz:** Ein zusätzliches (Python-)Artefakt im Projekt, aber: vollständige Abdeckung aller
Zielformate, starkes Argument für Profis, positives Signal in der Community.
