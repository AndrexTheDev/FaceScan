# Landingpage – FaceScan (Cloudflare Pages)

Statische Seite. **Kein Build-Schritt**, keine Node-Abhängigkeiten, keine externen Skripte, keine Tracker.

```
landing/
├── index.html              Startseite (DE, Standard)
├── 404.html                Fehlerseite
├── en/index.html           Startseite (EN)
├── impressum/index.html    Impressum (DE-Pflicht) – Entwurf, vor Livegang ausfüllen
├── privacy/index.html      Datenschutzerklärung – Entwurf, vor Livegang prüfen lassen
├── terms/index.html        AGB & Lizenzbedingungen – Entwurf, vor Livegang prüfen lassen
├── assets/
│   ├── css/styles.css      Design-Tokens (Jamaika-Farben), Night + Day Mode
│   ├── js/main.js          Theme-Toggle, Vergleichsregler, „Adresse kopieren"
│   └── img/                logo.svg, favicon.svg, QR-Codes, Platzhalter-Grafiken, og-image.png
├── _headers                Security-Header (CSP, HSTS, …)
├── _redirects              Sprach-Routen, 404-Fallback
├── robots.txt · sitemap.xml
└── README.md               diese Datei
```

## Farben (wie in der App)

| Rolle | Hex | Kontrast |
|---|---|---|
| Schwarz (Basis Night) | `#000000` | – |
| Grün (Primär, Night) | `#009B3A` | Schwarz auf Grün **5,75:1** ✔ |
| Grün (Primär, Day) | `#007A2E` | auf Weiß **5,49:1** ✔ |
| Gold (Akzentfläche) | `#FFD100` | Schwarz auf Gold **14,37:1** ✔ |
| Gold als Text (Day) | `#8A6A00` | auf Weiß **5,07:1** ✔ |

**Regel:** Text auf Grün und Gold ist **immer schwarz**. Weiß auf `#009B3A` (3,65:1) und Gold auf Weiß
(1,46:1) bestehen die WCAG-AA-Anforderung für Fließtext nicht und werden vermieden.

## Deployment (Cloudflare Pages)

**Variante A – Git-Integration (empfohlen)**

1. Cloudflare → *Workers & Pages* → *Pages* → *Mit Git verbinden* → Repository `AndrexTheDev/FaceScan`.
2. Build-Einstellungen:
   - Framework-Voreinstellung: **None**
   - Build-Befehl: *(leer lassen)*
   - **Ausgabeverzeichnis:** `landing`
3. Produktions-Branch: `main` (Vorschau-Deployments automatisch je Branch).
4. Eigene Domain: Domain zu Cloudflare hinzufügen → Pages → *Custom domains* → `facescan.app`
   (kostenloses Zertifikat, automatische Verlängerung). `www.` per Redirect-Regel auf die Hauptdomain.

**Variante B – Direkt-Upload (ohne Git)**

```bash
npx wrangler pages deploy landing --project-name facescan
```

**Lokal ansehen**

```bash
cd landing && python3 -m http.server 8080
# http://localhost:8080
```

## Vor dem Livegang (Checkliste)

- [ ] Impressum mit vollständiger Anschrift ausgefüllt (Platzhalter `[…]` ersetzen)
- [ ] Datenschutzerklärung und AGB durch Anwalt prüfen lassen
- [ ] Krypto-Adressen dreifach gegen `docs/08-monetarisierung-crypto.md` abgeglichen
- [ ] QR-Codes mit einem zweiten Wallet gegengelesen
- [ ] Play-Store-Link (`com.andrexthedev.facescan`) korrekt gesetzt
- [ ] Platzhalter-Grafiken (`shot-photo.svg`, `shot-render.svg`) durch echte Beispielscans ersetzen
- [ ] `og-image.png` (1200×630) nach dem Branding-Finale neu erzeugen
- [ ] `_headers` wirksam (Test mit `curl -I https://facescan.app/` oder securityheaders.com)
- [ ] Lighthouse ≥ 95 in allen vier Kategorien, Ansicht bei 360 px geprüft
- [ ] EN-Fassung vollständig (keine „TODO"-Platzhalter)

## Hinweise

- **Keine externen Ressourcen:** keine Web-Fonts, keine CDN-Skripte, keine Tracker. Die Seite besteht
  DSGVO-technisch ohne Cookie-Banner.
- **CSP:** `script-src 'self'` ⇒ Inline-Skripte sind verboten. Ergänzungen gehören in
  `assets/js/main.js`.
- **Barrierefreiheit:** Skip-Link, sichtbarer Fokus (Gold/Grün), Kontraste geprüft, `prefers-reduced-motion`
  wird respektiert, Umschalter mit 44 px Trefferfläche.
- **Mehrsprachigkeit:** DE unter `/`, EN unter `/en/`. Beide Seiten enthalten eigene `<title>`/`<meta>` und
  `hreflang`-Verweise; der Umschalter verlinkt direkt zwischen den Fassungen.
