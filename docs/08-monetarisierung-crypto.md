# 08 – Monetarisierung (Freemium) & Krypto-Zahlungen

Stand: 2026-11-15 · Modul `:feature:paywall` · Verantwortlich: AndrexTheDev

**Empfangsadressen (fest, im App-Code mit Prüfsumme verankert):**

| Coin | Adresse |
|---|---|
| **SOL** (Solana, native) | `79KsqtJJdhKFJ9woxnYgtf3nq7HxQveafWBCtC3mxWi8` |
| **BTC** (native SegWit, P2WPKH) | `bc1qeqzrlfg3edrydk4s0hecakc82gp26n5p7hkc7f` |
| **ETH** (EVM) | `0xBC3fab34f69bc9f6661608C3FB36dDdC313C42F7` |

---

## 1. Produktdesign der Monetarisierung

Krypto-Zahlungen sind **Einmalzahlungen** – es gibt keinen automatischen Wiedereinzug. Daraus folgt eine
klare Produktentscheidung: **Lifetime-Tiers statt Abo**, ergänzt um **Credit-Packs** für Gelegenheitsnutzer
und optionale **Update-Pässe** (freiwillig, für den Zugang zu künftigen großen Versionssprüngen).

### 1.1 Tiers

| | **Starter** (Free) | **Creator** (Lifetime) | **Studio** (Lifetime) |
|---|---|---|---|
| **Preis (EUR-Äquivalent)** | 0 € | **39 €** | **129 €** |
| Scans | unbegrenzt | unbegrenzt | unbegrenzt |
| Gespeicherte Avatare | 3 | unbegrenzt | unbegrenzt |
| Scan-Modi | Quick, Standard | Quick, Standard, **Profi** | alle + Batch |
| Geometrie-Detail | Standard | Hoch (4K, Displacement) | **Maximal (8K, Poren-Detail)** |
| Texturauflösung | 2K | 4K | **8K** |
| Haar-Stufen | L1 (Cap) | **L2 (Karten)** | **L3 (Strähnen)** |
| Blendshapes | 52 (ARKit) | 52 + personalisiert | 52 + personalisiert + Korrektur-Shapes |
| Formate | GLB, OBJ, PLY, STL, `.fscan` | **+ FBX, USD, USDZ, DAE** | **+ ABC, BVH, VRM, CSV/JSON** |
| Rig & Skin | – | ✔ | ✔ + Full-Body |
| Gesichts-Animation | Live-Vorschau | Live + Aufnahme + Export | alles + Feinregler |
| Körper-Mocap | – | Vorschau | **Aufnahme + Export** |
| C2PA-Herkunft | – | ✔ | ✔ |
| Wasserzeichen im Render-Bild | ja (dezent, unten rechts) | nein | nein |
| Kommerzielle Nutzung | **nur privat** | **Indie** (Umsatz < 100 k €/Jahr) | **unbegrenzt** |
| Support | Community | E-Mail | E-Mail + vorrangig |
| Update-Pass | – | optional 19 €/Jahr | **inklusive** |

### 1.2 Credit-Packs (für Gelegenheitsnutzer und Testkäufer)

| Pack | Inhalt | Preis |
|---|---|---|
| **Export 10** | 10 Exporte in beliebigen Formaten (unabhängig vom Tier) | 4,90 € |
| **Haar-Detail** | Einmalig Haar-Stufe 3 für einen Avatar | 3,90 € |
| **Motion 30** | 30 Minuten Mocap-Aufnahme + Export | 6,90 € |
| **Druck-Paket** | Ein Avatar als druckfertiges STL-Set (mit Sockel) | 2,90 € |

Credits verfallen nicht, sind an das Gerät gebunden und mit dem Konzept „Lizenz-Token" (Kapitel 3)
gespeichert. **Begründung:** Viele Nutzer wollen erst *ein* Format ausprobieren – ein 39-€-Kauf ist dafür
eine zu hohe Hürde, ein 4,90-€-Kauf nicht.

### 1.3 Krypto-Vorteil sichtbar machen

„Crypto-Bonus: −20 % gegenüber dem kalkulierten Kartenpreis (keine Zahlungsdienstgebühren, keine
Rückbuchungskosten)." Konkret: Creator 39 € statt 49 €, Studio 129 € statt 159 €. Das ist ein ehrliches,
nachvollziehbares Argument und erhöht die Zahlungsbereitschaft.

---

## 2. Kauf-Ablauf in der App (UX)

```
[Pro freischalten]
   │
   ├─ Tier wählen (Karten mit einem Satz Nutzen, Empfehlung markiert: „Creator – für die meisten")
   │
   ├─ Coin wählen
   │     ● SOL   „Empfohlen: in ~10 Sekunden bestätigt, Cent-Gebühren"
   │     ○ BTC   „Sicher, aber langsamer (10–60 Min.), höhere Gebühren"
   │     ○ ETH   „Schnell, Gebühren schwanken stark"
   │
   ├─ [Betrag & QR]
   │     „Sende genau 0,2143 SOL an:"   [QR-Code]   [Adresse kopieren]
   │     „Betrag ist 15 Minuten gültig (Kurs 1 SOL = 182,10 €, Stand 15.11.2026 14:32)."
   │     ⓘ „Warum ein krummer Betrag? Die letzten Stellen sind deine Bestellnummer – so finden wir
   │         deine Zahlung automatisch. Bitte sende den Betrag exakt."
   │     [Im Wallet öffnen]  (Deep Link)   [Ich habe gesendet]
   │
   ├─ [Warten auf Bestätigung]
   │     „Wir schauen auf die Blockchain …" (Fortschritt: 0/1 Bestätigungen)
   │     „Du kannst zwischendurch weiter scannen – der Kauf läuft weiter."   [Im Hintergrund]
   │     Manueller Pfad: [Transaktions-ID einfügen]
   │
   └─ [Fertig]
         ✅ „Creator ist frei – danke!"
         „Deine Quittung: 5K7x…9Qd (Solana). Bitte aufbewahren: Damit kannst du deinen Kauf auf einem
          neuen Handy wiederherstellen."   [Quittung kopieren]  [Als PDF sichern]
```

**Prinzip:** Nie blockieren, nie nerven, immer Auswege. Wenn die Verifikation nicht klappt, bleibt die App
voll nutzbar und der Nutzer kann die Tx-ID manuell einreichen (Support-Pfad per E-Mail).

---

## 3. Entitlement-Modell (Offline-First-Lizenz)

Wir betreiben **keine Konten und keine Lizenz-Server-Pflicht**. Stattdessen:

```
Bestellung (lokal erzeugt)
   orderId     = UUID4
   reference   = 32-Byte-Zufall (nur bei SOL als Solana-Pay-Referenz-Key = base58-Pubkey)
   amountFp    = Preis + eindeutiger Cent-/Satoshi-/Wei-Offset pro Bestellung
        ↓  (Nutzer zahlt)
Verifikation (einmalig online)
   Prüfung: Empfänger = unsere Adresse? Betrag ≥ Preis (Toleranz)? Finalität? Referenz/Fingerprint dabei?
        ↓
Quittung (lokal, signiert)
   {
     "v":1, "tier":"CREATOR", "orderId":"…", "chain":"SOL",
     "tx":"5K7x…9Qd", "amount":"0.214300000", "ts":"2026-11-15T14:33:11Z",
     "eurValue":"39.00", "rateSource":"…", "device":"<hash(deviceId+salt)>",
     "sig":"<Ed25519 über obige Felder, Schlüssel im Backend/Offline-Signer>"
   }
```
- Der private Ed25519-Signierschlüssel liegt **nicht** in der App; die App prüft nur die Signatur mit dem
  fest verankerten Public Key.
- **Offline gültig:** Die App vertraut der signierten Quittung. Einmal pro 30 Tagen (wenn Netz da ist)
  wird sie gegen die Chain nachgeprüft (Betrag/Empfänger stimmen, nicht doppelt verwendet). Gibt es 90 Tage
  lang keine Prüfung, bleibt die Lizenz **trotzdem gültig** (Grace) – Offline-First schlägt Kopierschutz.
- **Geräteumzug:** „Kauf wiederherstellen" ⇒ Nutzer gibt Tx-Hash ein (oder importiert die Quittungsdatei)
  ⇒ App prüft on-chain + unsere Signatur ⇒ neue Quittung für dieses Gerät. Alte Geräte behalten ihre
  Quittung (Familienszenarien sind eingeplant, keine Rechtsverfolgung wegen Kleinstbeträgen).
- **Transparenz:** Der Nutzer sieht in „Lizenzen & Quittungen" alle Käufe mit Tx-Hash, Betrag, EUR-Wert
  und Datum – und kann sie als PDF exportieren (Buchhaltungs-/Steuerbeleg).

---

## 4. Zahlungswege im Detail

### 4.1 SOL (Hauptpfad – beste Nutzererfahrung)

**Solana Pay**-Mechanik [6](https://devrels.xyz/articles/solana-pay-the-spec) [7](https://stablecoininsider.org/solana-pay-usdc/):

```
solana:79KsqtJJdhKFJ9woxnYgtf3nq7HxQveafWBCtC3mxWi8
       ?amount=0.2143
       &reference=<base58 32-Byte-Referenz-Key>      # pro Bestellung neu, nur der Public Key wichtig
       &label=FaceScan
       &message=Creator-Lizenz%20Bestellung%20<orderId>
       &memo=fs-<orderId>
```
1. App erzeugt `reference` (nur der Public Key wird gebraucht; der geheime Teil wird verworfen).
2. QR-Code + Deep Link (`solana:` URI; für Phantom/Solflare zusätzlich `https://phantom.app/ul/v1/…`).
3. Verifikation: `getSignaturesForAddress(reference)` (oder WebSocket-`logsSubscribe`) ⇒ gefundene
   Transaktion ⇒ Prüfen mit `validateTransfer`-Logik: Empfänger = unsere Adresse, Betrag ≥ Preis,
   `finality=confirmed` (Target ≈ 5–15 s), `err == null`.
4. **Eine Signatur = eine Bestellung** (Signatur wird als verbraucht gespeichert, Wiederverwendung abgelehnt).
5. Optional zusätzlich: **SPL/USDC** auf derselben Wallet (ATA der Adresse) – Kursstabilität für Käufer,
   die nicht in SOL schwanken wollen. Empfehlung: USDC als „stabil"-Option anbieten, sobald die
   Verifikationslogik steht (M6.2).

**Sonderfälle:** Zahlung per Börsenauszahlung ⇒ kein Referenz-Key möglich ⇒ Betrags-Fingerprint (wie BTC)
als Rückfall + manueller Tx-ID-Pfad.

### 4.2 BTC (eine statische Adresse)

Herausforderung: **eine** Adresse für alle Kunden ⇒ Zuordnung nur über **Betrag + optional Memo**.

1. **Betrags-Fingerprint:** Der Bestellbetrag enthält einen eindeutigen Offset.
   Beispiel: Preis 39,00 € ⇒ 0,00039000 BTC + `offset` (1…9999 Satoshi, aus `orderId` abgeleitet).
   Der Nutzer sieht „Sende genau **0,00039417 BTC**" (Betrag in BTC, nicht EUR, mit Warnung:
   „Der BTC-Kurs schwankt – der EUR-Gegenwert wird zum Zeitpunkt des Eingangs berechnet.").
2. **OP_RETURN-Memo** (optional, wenn das Wallet es kann): `FS|<orderId>` – beschleunigt die Zuordnung,
   ist aber **nie Voraussetzung** (Börsen können das meist nicht).
3. **Beobachtung:** öffentliche ESPLORA-/Esplora-Endpunkte (mempool.space, blockstream.info) – der Nutzer
   kann den Endpunkt wählen; wir fragen **2 von 3** ab und verlangen Übereinstimmung.
4. **Bestätigungen:** Freischaltung ab **1 Bestätigung** (Beträge < 200 €; Restrisiko wird bewusst getragen),
   Anzeige „2/3 Bestätigungen" bis zur endgültigen Freigabe.
5. **RBF/Replace-by-Fee:** Transaktionen mit `sequence < 0xfffffffe` werden als „noch nicht sicher"
   markiert; Freischaltung erst nach 1 Bestätigung.
6. **Unter-/Überzahlung:** < 98 % ⇒ Hinweis + „Fehlbetrag nachsenden" (neue Bestellung mit Restbetrag).
   ≥ 98 % ⇒ Freischaltung + ggf. Gutschrift des Überschusses als Credits.

### 4.3 ETH (eine statische Adresse)

1. **EIP-681-Zahlungs-URI:** `ethereum:0xBC3f…42F7?value=<wei>&label=FaceScan` – funktioniert mit den
   meisten mobilen Wallets.
2. **Zuordnung:** Wie bei BTC über den **Betrags-Fingerprint** (Offset in Wei, z. B. letzte 4–6 Stellen) –
   zusätzlich können wir **ERC-20-Transfers** (USDC/USDT) über das `Transfer`-Log derselben Adresse
   erkennen (das ist bei ETH sogar noch zuverlässiger als der native Transfer, weil Logs gut indiziert sind).
3. **Beobachtung:** öffentliche JSON-RPC-Endpunkte (mehrere, 2-von-3-Abgleich) oder ein
   Block-Explorer-API-Key des Betreibers (kein Geld-Zugriff, nur Lesezugriff).
4. **Bestätigungen:** 12 Blöcke (≈ 3 Min.) für ETH, 32 für L2-Arbitrum/Base/OP falls später ergänzt.
   **Hinweis an Nutzer:** Gebühren (Gas) schwanken – im Auswahl-Screen als Warnung anzeigen.
5. **L2-Option (später):** Selbst wenn die Hauptadresse auf Ethereum-Mainnet liegt, erreichen die meisten
   Nutzer sie über CEX-Auszahlungen. Optional: zusätzliche Adressen auf Arbitrum/Base (dieselbe Adresse
   funktioniert dort technisch – **nur mit ausdrücklichem Hinweis** und getrennter Verifikationslogik, weil
   Chain-ID-bezogen).

### 4.4 Kurs & Betragsberechnung

- Quelle: mehrere öffentliche Kurs-APIs, Median, Caching 60 s, **Quote-Lock 15 Minuten**.
- Bei Kursbewegung > 2 % innerhalb des Locks ⇒ neue Quote mit Hinweis („Kurs hat sich bewegt – neuer
  Betrag: …"). Ein bereits gesendeter, geringfügig abweichender Betrag wird trotzdem akzeptiert
  (Toleranzregel in 4.5).
- Die EUR-Basispreise bleiben konstant; die Krypto-Menge ändert sich. Buchhalterisch zählt immer der
  EUR-Wert zum Empfangszeitpunkt (Kapitel 6).

### 4.5 Verifikationsregeln (alle Chains)

| Regel | Wert |
|---|---|
| Empfänger | Exakt unsere Adresse (Vergleich normalisiert, bei EVM: kleingeschrieben mit Prüfsummen-Validierung) |
| Mindestbetrag | 98 % des Quoted-Betrags (Toleranz für Wallet-Rundungen/Gebührenabzug bei Börsenauszahlungen) |
| Finalität | SOL: `confirmed` · BTC: ≥ 1 Conf. · ETH: ≥ 12 Blöcke |
| Eindeutigkeit | Tx-Hash wird global als „verbraucht" gespeichert (lokal + optionaler Server-Index) |
| Zeitfenster | Bestellung 60 Minuten gültig; danach neue Quote. Bereits gesendete Zahlungen werden trotzdem zugeordnet. |
| Ende-zu-Ende-Prüfung | 2 von 3 unabhängigen Endpunkten müssen übereinstimmen |
| Fehlerfall | Nie blockierend; immer „Tx-ID manuell einreichen" (→ E-Mail-Support mit lokalem Nachweis) |

---

## 5. Betrieb & Support

| Thema | Regelung |
|---|---|
| **Support** | E-Mail hippie.highho@gmail.com; im Support-Fall darf der Nutzer die Quittung/Tx-ID mitschicken (freiwillig) |
| **Rückerstattung** | Freiwillige 14-Tage-Geld-zurück-Möglichkeit an die **Absenderadresse** (abzüglich Netzwerkgebühren). Kursdifferenz trägt der Betreiber; bei BTC/ETH wird der EUR-Wert erstattet. |
| **Doppelzahlung** | Automatische Erkennung ⇒ zweiter Betrag wird als Guthaben (Credits) verbucht oder auf Wunsch erstattet |
| **Verlorene Quittung** | Support kann über Tx-Hash eine neue signierte Quittung ausstellen (Server-Signer) |
| **Betrugsversuche** (gefälschte Quittungen) | Signaturprüfung schlägt fehl ⇒ keine Freischaltung. Server-Index prüft bei Online-Checks auf Doppelverwendung. |
| **Schutz der Adressen** | Adressen sind im Code konstant + Prüfsumme. Die App zeigt sie mit QR **und** zum Abgleich die ersten/letzten Zeichen. Kein Clipboard-Hijacking-Schutz möglich – deshalb Hinweis „Bitte die ersten und letzten 6 Zeichen im Wallet vergleichen". |
| **Treasury** | Hardware-Wallet (z. B. Ledger/Trezor) oder Multisig (z. B. Squads auf Solana). **Keine** privaten Schlüssel in App, Repo oder Cloud. Regelmäßige Auszahlung in Fiat über eine lizenzierte Börse (MiCA-konform). |

---

## 6. Steuern, Buchhaltung, Regulierung (DE/EU) – Überblick, keine Rechtsberatung

| Thema | Stand / Handlungsbedarf |
|---|---|
| **Umsatzsteuer** | Rechnungen werden in **EUR** gestellt (Netto + USt.), auch wenn in Krypto gezahlt wird. Für digitale Leistungen an Endkunden (B2C) in der EU gilt der Steuersatz des Kundenlands; bei Überschreiten von 10.000 € unionsweiter B2C-Umsätze ist das **OSS-Verfahren** (One-Stop-Shop) zu nutzen; Anbieter digitaler Dienstleistungen müssen ggf. ab der ersten Leistung registriert sein [8](https://flexlogistique.fr/crypto-payments-and-vat-what-sellers-should-know/) [9](https://norman.finance/de/en/blog/accepting-cryptocurrency-payments-germany). |
| **Tausch (Barter)** | Zahlung in Krypto gilt umsatzsteuerlich als Tausch (§ 3 Abs. 12 UStG); Bemessungsgrundlage ist der EUR-Wert. Der Kurs (Quelle + Zeitpunkt) ist zu dokumentieren [9](https://norman.finance/de/en/blog/accepting-cryptocurrency-payments-germany). |
| **Ertragssteuer** | Einnahmen sind Betriebseinnahmen in EUR zum Zeitpunkt des Zuflusses; späterer Kursgewinn/-verlust der gehaltenen Coins ist gesondert zu erfassen (bei Gewerbebetrieb steuerpflichtig). |
| **Aufzeichnungspflicht** | Je Transaktion: Datum, Uhrzeit, Coin, Menge, EUR-Wert, Kursquelle, Tx-ID, Wallet-Adressen. Aufbewahrung nach nationalen Fristen (in DE regelmäßig 10 Jahre für Buchungsbelege). |
| **DAC8 / CARF** | Seit 1.1.2026 melden Krypto-Dienstleister (CASPs) Transaktionen automatisch; erste Meldungen 2027. Die Pflicht trifft primär die Dienstleister – Selbstverwahrung ist nicht automatisch ein CASP, aber die **Sichtbarkeit** für Behörden steigt deutlich [10](https://www.icon.partners/post/dac8-in-the-eu-crypto-transactions-now-reported-to-tax-authorities) [8](https://flexlogistique.fr/crypto-payments-and-vat-what-sellers-should-know/). |
| **MiCA** | EU-Verordnung für Krypto-Dienstleister; in DE überwacht durch die BaFin. Wer nur Zahlungen auf die eigene Wallet empfängt und keine Verwahrung/Handel für Dritte betreibt, fällt grundsätzlich nicht unter die CASP-Lizenzpflicht – **das ist aber im Einzelfall zu prüfen** [11](https://tangem.com/en/learning-hub/post/mica-crypto-rules-germany/). |
| **Pflicht: Impressum & Datenschutz** | Für die Website (Impressumspflicht) und die App (Datenschutzerklärung, ggf. Impressum) – siehe `09` und `12`. |
| **Konkrete To-dos vor dem ersten Verkauf** | 1) Gewerbe anmelden/Kleinunternehmerregelung prüfen (§ 19 UStG – Achtung: bei OSS-Tatbeständen kritisch), 2) OSS-Registrierung prüfen, 3) Steuerberater mit Krypto-Erfahrung binden, 4) Buchhaltungs-Export in der App (CSV/PDF) bereitstellen, 5) AGB & Widerrufsbelehrung erstellen lassen. |

> **Hinweis:** Diese Tabelle ist eine Arbeitsgrundlage, **keine Steuerberatung**. Vor dem ersten Verkauf
> ist eine verbindliche Klärung mit einem Steuerberater (Krypto/Digital Services) zwingend.

---

## 7. Kennzahlen (Zielwerte 12 Monate nach Launch)

| Kennzahl | Ziel |
|---|---|
| Install → abgeschlossener erster Scan | ≥ 55 % |
| Erster Scan → Export | ≥ 45 % |
| Export → Kauf (Conversion Free→Paid) | 4–8 % |
| Anteil SOL am Zahlungsvolumen | ≥ 60 % |
| Support-Fälle je 100 Verkäufe (Zuordnungsprobleme) | ≤ 6 |
| Rückerstattungsquote | ≤ 3 % |
| ARPU (bezahlt) | ≈ 55 € |

## 8. Erweiterungen (nach dem Launch)

- **Team-/Studio-Lizenzen** (3/10 Plätze) mit zentralem Lizenz-File.
- **Asset-Packs** (Haar-Vorlagen, Outfits, Beleuchtungs-Presets) – eigene, lizenzfreie Inhalte.
- **Blender-Add-on „FaceScan Link Pro"** (kostenlos; Pro-Funktionen gegen Studio-Lizenz).
- **Bildungs-Rabatt** (Studierende/Schulen) – manuell gegen Nachweis.
- **Regionale Preisanpassung** (Kaufkraft) – optional, mit klarer Kommunikation.
