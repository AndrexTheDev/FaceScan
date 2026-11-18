# 11 – Roadmap, Team, Kosten

Stand: 2026-11-15 · Start: November 2026 · Public Release: Q1 2028 (Ziel)

---

## 1. Phasenplan

| Phase | Dauer | Kalender | Inhalt | Abgeschlossen wenn |
|---|---|---|---|---|
| **M0 – Machbarkeit** | 6 W | Nov–Dez 2026 | 3DMM-Fit + EPnP-Posen + erstes MVS auf 3 Geräten; synthetischer Datensatz; Geräte-Self-Benchmark | Reprojektionsfehler ≤ 3 px; Gesicht ist „eindeutig erkennbar"; Zeitbudget grob bekannt |
| **M1 – Vertikaler Schnitt** | 10 W | Jan–Mitte März 2027 | Kamera-Assistent (Quick), Pipeline bis Mesh, GLB/OBJ/PLY/STL-Export, Tresor, `.fscan` | Ein durchgängiger Weg: Scan → Datei, auf 3 Geräten, offline |
| **M2 – Haar & Textur** | 10 W | März–Mai 2027 | Haar-L1/L2, Textur-Baking (Albedo/Normal/Rough/AO), Qualitätsbericht, Vergleichsslider | „Sieht aus wie ich"-Ergebnisse bei ≥ 15 von 20 Personen |
| **M3 – Rig & Animation (Gesicht)** | 8 W | Juni–Juli 2027 | Basiskopf-Topologie, NRICP, 52 Blendshapes, Live-Animation, `.fsmc`, Kalibrierung | Avatar zwinkert/lächelt live mit ≥ 25 fps; Export als GLB mit Morphs |
| **M4 – Export-Suite** | 8 W | Aug–Sep 2027 | FBX (binär), USDA/USDZ, DAE, ABC, Format-Assistent, Achsen/Einheiten, C2PA | Alle Zielprogramme öffnen die Dateien (Protokoll) |
| **M5 – Körper, UI, i18n** | 8 W | Okt–Nov 2027 | Pose/Hand-Tracking, Retargeting, Mocap-Export (BVH/ABC/CSV), Designsystem-Finalisierung, DE/EN, Barrierefreiheit | Closed Beta mit 200 Testern; SUS ≥ 80 |
| **M6 – Monetarisierung & Launch** | 8 W | Dez 2027–Jan 2028 | Krypto-Flows (SOL/BTC/ETH), Lizenz-Token, Rechtstexte, Landingpage, Play-Release | App im Store, Landingpage live, erste zahlende Kunden |

**Puffer:** 6 Wochen eingeplant (Krankheit, Play-Review-Schleifen, Lizenzklärungen). Summe **≈ 64 Wochen**.

## 2. Meilenstein-Abhängigkeiten (kritischer Pfad)

```
Basiskopf-Topologie (3D-Artist) ──► NRICP ──► Blendshapes ──► Animation ──► FBX/ABC-Export
                                                                   │
Synthetischer Datensatz ──► 3DMM ──► MVS ──► TSDF ────────────────┤
                                        └──► Haar L1/L2/L3 ───────┤
                                                                   ▼
Kamera-Assistent ──► Pipeline-Orchestrierung ──► Qualitätsbericht ──► Release
Rechts-/Lizenzklärung ──► 3DMM-Entscheidung ──► (kritisch! früh klären)
```

**Der kritische Pfad ist die Haar-Pipeline und die juristische Klärung der 3DMM-Quellen.** Beides muss
**parallel zu M0** starten, nicht später.

## 3. Team & Rollen

| Rolle | Umfang | Wer |
|---|---|---|
| Entwicklung (Android, C++, Pipeline) | Vollzeit | AndrexTheDev |
| 3D-Artist (Basiskopf-Topologie, Rig-Vorlage, Haar-Vorlagen, Bewertung) | ~120 h über das Projekt | Freelance (Vertrag mit Rechteübertragung!) |
| Modell-Erhebung (3DMM-Trainingsdaten) | 20–40 Personen, Einwilligungen, Studio-Scans | externer Dienstleister / Kooperation |
| Recht (AGB, Datenschutz, Lizenzprüfung, Impressum) | ~20 h | Fachanwalt IT/Medien |
| Steuern (Krypto, OSS, Buchhaltung) | laufend | Steuerberater mit Krypto-Erfahrung |
| Lektorat DE/EN, UX-Tests | ~40 h | Freelance |
| Support | ab Beta | AndrexTheDev |

**Wichtig:** Bei allen externen Beteiligten eine **schriftliche Rechteübertragung** (Nutzungs-, Leistungs-
und Urheberrechte, uneingeschränkt, übertragbar) vertraglich sichern. Sonst ist das kommerzielle Produkt
rechtlich angreifbar – das ist der häufigste Fehler bei Kleinst-Teams.

## 4. Kosten (Schätzung, einmalig + laufend)

| Posten | Betrag | Zeitpunkt |
|---|---|---|
| Google Play Developer-Konto | 25 $ einmalig | vor Release |
| Domain (`.app`/`.de`) | 15–40 €/Jahr | M6 |
| Cloudflare Pages | 0 € (Free-Tier ausreichend) | M6 |
| 3D-Artist | 3.000–6.000 € | M1–M3 |
| Studio-Referenzscans (20 Personen) | 2.000–5.000 € | M0/M2 |
| Modell-Erhebung & Einwilligungsmanagement | 1.500–4.000 € | M0–M3 |
| Testgeräte (3–4 gebrauchte Mittelklasse-Geräte) | 800–2.000 € | M0 |
| Anwalt (AGB, Datenschutz, Lizenzprüfung, Markenrecherche) | 3.000–6.000 € | M0, M6 |
| Steuerberater (Krypto/OSS) | 1.500–3.000 €/Jahr | ab M6 |
| Grafik/Branding (Logo, Store-Grafiken, Screenshots) | 500–2.000 € | M6 |
| Versicherung (IT-/Medienhaftpflicht) | 300–900 €/Jahr | ab M6 |
| **Summe (einmalig, bis Launch)** | **≈ 12.000–27.000 €** | |
| **Laufend (Jahr 1 nach Launch)** | **≈ 2.500–6.500 €** | |

*Ohne eigene Arbeitszeit gerechnet. Bei komplettem Solo-Bootstrapping (eigener 3D-Artist-Anteil, keine
Studio-Scans, Minimal-Rechtsberatung) ist ein Start mit **≈ 3.000–5.000 €** möglich – dann dauert es länger
und die Qualitätsziele (Haar, 3DMM) sind anspruchsvoller. Empfehlung: mindestens die **3DMM-/Lizenzklärung**
und die **Studio-Referenzscans** nicht einsparen.*

## 5. KPIs nach Launch

| Kennzahl | Ziel (12 Monate) |
|---|---|
| Installationen | 25.000 |
| Abgeschlossene Scans | 15.000 |
| Bezahlte Käufe | 600–1.200 |
| Umsatz | 25.000–50.000 € |
| Bewertung im Play Store | ≥ 4,4 (bei ≥ 300 Bewertungen) |
| Crash-free Sessions | ≥ 99,5 % |
| Support-Mails/Woche | < 15 |
| Share of SOL-Zahlungen | ≥ 60 % |

## 6. Nach dem Launch (Backlog, priorisiert)

1. **iOS-Port** (Kamera- und Storyboard-Anpassung; gleiche C++-Kernbibliothek).
2. **Desktop-Begleit-App** (Windows/macOS/Linux): `.fscan` öffnen, größere Rechnungen (Pro-Modus mit 8K+
   auf der GPU), Import in Blender direkt, USDC-Export über das USD-SDK.
3. **USDC (Solana) als stabiler Zahlungsweg** und optional L2 für ETH.
4. **Kleidungs-/Oberkörper-Scan** (gleiche Pipeline, anderer Template-Körper).
5. **Audio-Lip-Sync** (Viseme on-device).
6. **Mehrpersonen-Scan** (nacheinander, Familien-Set).
7. **Avatar-Varianten** (Altersvarianten, Stilisierung) – nur mit klarer Kennzeichnung (C2PA + Wasserzeichen)
   und **nie** ohne Zustimmung.
8. **Community-Formate**: VRM 1.0 final, MetaHuman-Übergabeprofil, Ready-Player-Me-Import.
