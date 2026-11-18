# 12 – Landingpage (Cloudflare Pages)

Stand: 2026-11-15 · Verzeichnis: [`landing/`](../landing) · **Kein Build-Schritt** (reines HTML/CSS/JS)

---

## 1. Entscheidung: statisch ohne Build

| Option | Bewertung |
|---|---|
| **Reines HTML/CSS/JS** (gewählt) | Sofort deploybar, keine Node-Abhängigkeiten, keine Supply-Chain-Risiken, Ladezeit < 100 ms, Cloudflare Pages braucht nur einen Output-Ordner. Ideal für ein Produkt, dessen Versprechen „offline, schnell, kein Schnickschnack" ist. |
| Astro/11ty | Mehr Komfort bei Blog/i18n, aber Build-Pipeline und Node-Abhängigkeiten. Später möglich, wenn ein Blog/Changelog dazukommt. |
| Cloudflare Pages Functions | Nur für den optionalen Verifikations-Endpunkt (siehe 7) – **nicht** für die Kernseite. |

## 2. Seitenstruktur

```
/                        Startseite (DE, Standard; EN über /en/ oder Sprachtoggle)
/en/                     Englische Fassung (eigene HTML, damit SEO sauber ist)
/impressum/              Impressum (DE-Pflicht)
/privacy/                Datenschutzerklärung (DE + EN)
/terms/                  AGB / Lizenzbedingungen
/download/               Verweis auf Google Play (+ Systemanforderungen)
/support/                Kontakt, FAQ, Anleitungen
assets/                  css, js, img (Screenshots, QR-Codes)
_headers                 Security-Header (Cloudflare Pages)
_redirects               Sprach-Redirects, 404-Fallback
robots.txt · sitemap.xml SEO
```

**Sprachumschaltung:** `?lang=en` sowie persistenter Umschalter (localStorage) + `<link rel="alternate"
hreflang>` in beiden Fassungen. Die Sprache wird clientseitig umgeschaltet (Texte liegen als JS-Objekt
vor), damit keine doppelte Inhaltspflege nötig ist; für SEO bekommt `/en/` dennoch eine eigene URL mit
eigenen `<title>`/`<meta>` (die Inhalte kommen aus demselben i18n-Objekt, werden aber serverseitig
„eingefroren", indem `/en/index.html` die Sprache fest auf `en` setzt).

## 3. Inhalt der Startseite (Reihenfolge & Copy-Gerüst)

| # | Sektion | DE | EN |
|---|---|---|---|
| 1 | **Hero** | „Scanne dich in 3D. In einer Minute. Komplett offline." Unterzeile: „Gesicht und Haare als detailreiches 3D-Modell – animierbar, exportierbar in alle Profi-Formate. Ohne Cloud. Ohne Konto." CTA: **„Kostenlos scannen"** (Play-Link) + sekundär „Wie es funktioniert" | "Scan yourself in 3D. In one minute. Fully offline." |
| 2 | **3-Schritte-Animation** (CSS, kein Video) | 1 Aufnehmen (geführt) · 2 Berechnen (auf dem Handy) · 3 Exportieren (dein Format) | Record · Compute · Export |
| 3 | **Vorher/Nachher-Slider** | Foto ↔ 3D-Render (Screenshots aus der App) | before/after |
| 4 | **Funktionen** (6 Karten) | Gesicht + Haar · Animierbar · Alle Formate · Offline & privat · Einsteigerfreundlich · Nachbearbeitbar | face + hair · animatable · every format · offline & private · beginner friendly · pro-editable |
| 5 | **Formate** (Logo-Raster) | Blender · Unreal · Unity · Maya · 3ds Max · Houdini · ZBrush · Substance · Godot · Apple AR · 3D-Druck · Web/Three.js + „u. a. FBX, USD/USDZ, ABC, GLB, OBJ, DAE, PLY, STL" | same |
| 6 | **Animation** (kurzes Loop-Video, lokal gehostet) | „Dein Avatar spricht, lächelt, bewegt sich – live mit deiner Handykamera. Ohne Anzug, ohne Marker, ohne ARCore." | "Your avatar talks, smiles, moves – live from your phone camera. No suit, no markers, no ARCore." |
| 7 | **Offline & Datenschutz** (Vertrauensblock, groß) | „Nichts verlässt dein Handy." 4 Punkte: keine Cloud · kein Konto · verschlüsselter Tresor · kein Tracking | "Nothing leaves your phone." |
| 8 | **Preise** | Starter 0 € · Creator 39 € · Studio 129 € (jeweils Feature-Auszüge + „Crypto-Bonus −20 %") | same |
| 9 | **Krypto-Zahlung** | Drei Karten mit QR-Code, Adresse kopierbar, „Bitte nur den in der App angezeigten Betrag senden – die letzten Stellen sind deine Bestellnummer." Hinweis: „Zahlung erfolgt ausschließlich in der App." | same |
| 10 | **Für Einsteiger** | „Du brauchst kein 3D-Wissen." + 3 Sätze + Verweis auf Anleitung | "No 3D skills needed." |
| 11 | **FAQ** (Akkordeon) | 10 Fragen (siehe unten) | same |
| 12 | **Roadmap** | Öffentlicher Ausblick (M1–M6 grob) + „Wünsch dir ein Feature" | same |
| 13 | **Abschluss-CTA** | „Dein Gesicht in 3D. In einer Minute." + Play-Button | same |
| 14 | **Footer** | Impressum · Datenschutz · AGB · Support · Kontakt · „Entwickelt von AndrexTheDev" · Social-Links (optional) | same |

**FAQ (10):** Brauche ich besondere Hardware? · Wie gut werden Haare? · Funktioniert es ohne Internet? ·
Was passiert mit meinen Bildern? · Kann ich die Modelle verkaufen? · Welche Formate? · Wie animiere ich? ·
Warum Krypto? · Kann ich mein Geld zurückbekommen? · Kommt eine iOS-Version?

## 4. Design auf der Seite

- Gleiche Tokens wie die App: Schwarz `#000000`, Grün `#007A2E` (Text/Buttons auf weißem Grund, AA-konform),
  Gold `#FFD100` als Fläche mit schwarzer Schrift, Akzent `#101010`.
- Ein **Day/Night-Umschalter**, damit Besucher:innen beide Modi sehen (die App hat beides).
- Schrift: System-Font-Stack (keine externen Fonts ⇒ keine DSGVO-Diskussion, kein FOUT, schnell).
- Alle Bilder als **WebP** mit PNG-Fallback, `loading="lazy"`, feste `width/height` (kein Layout-Shift).
- Keine externen Skripte, keine Fonts von Drittanbietern, keine Tracker im Standard-Pfad.

## 5. SEO & Metadaten

- `<title>`: „FaceScan – 3D-Gesichtsscan offline (Android) | Gesicht & Haare als 3D-Modell"
- Meta-Description (≤ 155 Zeichen), Open Graph + Twitter-Card (Bild `assets/img/og-image.png`, 1200×630).
- `structured data` (`SoftwareApplication`): Name, Betriebssystem Android, Kategorie, `offers` mit
  Preis 0/39/129 €, Bewertungen erst wenn vorhanden (keine Fake-Ratings!).
- `sitemap.xml`, `robots.txt`, sprechende URLs, Alt-Texte auf allen Bildern, `/en/` mit `hreflang`.
- Kern-Keywords (natürlich formuliert, kein Stuffing): „3D Gesicht scannen Handy", „Gesicht 3D Modell
  Android", „Haar 3D Scan", „FBX USD GLB Export Avatar", „Gesichtsanimation ohne ARCore", „offline 3D Scan".

## 6. Sicherheit & Header (`_headers`)

```
/*
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=()
  Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
  Content-Security-Policy: default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'
```
Keine Inline-Skripte (CSP ohne `unsafe-inline` für Skripte) – die i18n-Texte liegen in einer externen
`.js`-Datei mit `data-i18n`-Attributen im HTML.

## 7. Deployment (Cloudflare Pages)

**Variante A – Git-Integration (empfohlen):**
1. Cloudflare → Workers & Pages → Pages → „Mit Git verbinden" → Repository `AndrexTheDev/FaceScan`.
2. Build-Einstellungen: Framework = **None**, Build-Befehl = *(leer)*,
   **Ausgabeverzeichnis** = `landing`.
3. Deploy-Branch: `main` (Vorschau-Branches automatisch).
4. Eigene Domain: `facescan.app` → DNS auf Cloudflare, Pages-Custom-Domain hinzufügen (kostenloses
   Zertifikat, Auto-Renew).
5. `www.`-Weiterleitung über `_redirects` oder Cloudflare-Redirect-Regel.

**Variante B – Direkt (ohne Git):**
```
npx wrangler pages deploy landing --project-name facescan
```

**Optionaler Backend-Teil (nur wenn nötig):** ein Pages-Functions-Endpunkt `/api/verify`, der
Krypto-Zahlungen **zusätzlich** zur App prüft (z. B. wenn die App keinen RPC erreichen kann). Er ist
*zusätzlich*, nie zwingend – die App bleibt offline-first. Dafür: `functions/api/verify.ts` +
KV-Binding für verbrauchte Tx-Hashes.

## 8. Rechtliches auf der Seite (DE-Pflicht)

- **Impressum** (Anbieterkennung): Name/Anschrift des Betreibers, Kontakt (E-Mail), ggf. USt-ID,
  Verantwortlicher für den Inhalt. Vor Veröffentlichung mit dem Anwalt abstimmen.
- **Datenschutzerklärung**: Für die Website (Server-Logs/Cloudflare, keine Tracker, keine Cookies) und die
  App (lokale Verarbeitung). Wenn **Cloudflare Web Analytics** genutzt wird: cookie-frei, aber in der
  Erklärung benennen.
- **AGB/Lizenzbedingungen**: Verlinkt aus Footer und Preissektion (EULA-Inhalte aus `09`).
- **Barrierefreiheit** auch auf der Seite: Kontrast, Fokus, Skip-Link, beschriftete Formulare.

## 9. Checkliste vor Livegang

- [ ] Impressum mit vollständiger Anschrift (nicht ohne rechtliche Prüfung)
- [ ] Datenschutzerklärung DE + EN, verlinkt aus Footer *und* im Kauf-/Kontaktbereich
- [ ] Play-Store-Link korrekt, Store-Badge eingebunden
- [ ] Krypto-Adressen **dreifach** gegen `08` abgeglichen und als Text **und** QR geprüft
- [ ] QR-Codes mit einem zweiten Wallet/Scanner gegengelesen
- [ ] OG-Image vorhanden, Vorschau in WhatsApp/Telegram/X geprüft
- [ ] `_headers` wirkt (Test mit `curl -I` oder securityheaders.com)
- [ ] Lighthouse ≥ 95 (Performance/A11y/Best Practices/SEO)
- [ ] Mobile-Ansicht auf 360 px Breite geprüft
- [ ] EN-Fassung vollständig (keine „TODO"-Platzhalter)
- [ ] `sitemap.xml` und `robots.txt` erreichbar
