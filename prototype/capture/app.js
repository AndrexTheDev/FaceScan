/* FaceScan – Aufnahme-Assistent
 *
 * Läuft im Browser auf dem Telefon. Zeichnet 52 Mimik-Werte, 478 Messpunkte,
 * Kopfhaltung und Telefonlage auf und rechnet daraus die Kalibrierung
 * (F-402). Alles bleibt im Gerät, bis der Nutzer am Ende auf „Sichern" tippt.
 *
 * Drei Entscheidungen, die man kennen sollte:
 *
 * 1. **Das Bild wird für die Anzeige gespiegelt, nicht für die Rechnung.**
 *    Eine Selfie-Ansicht spiegelt man, sonst kommt sie einem falsch vor.
 *    MediaPipe warnt aber ausdrücklich: ein gespiegeltes Bild vertauscht
 *    links und rechts in den Mimik-Werten. Gespiegelt wird deshalb nur per
 *    CSS — in die Rechnung geht das ungespiegelte Original.
 * 2. **Die Zahlen liegen binär, nicht als JSON.** 478 Punkte × 3 Zahlen × 30
 *    Bilder je Sekunde wären als Text in einer Minute zweistellig
 *    megabytegroß und größtenteils Ziffern. Als int16 sind es 2,9 kB je
 *    Bild. Das Format steht in `FORMAT` unten und wird von
 *    `tools/lese_capture.py` gelesen.
 * 3. **Der Größtwert ist ein 95er-Percentil, kein Maximum.** Ein einzelnes
 *    verreißtes Bild würde als Maximum die ganze Kalibrierung nach oben
 *    ziehen. Das Perzentil nimmt den Wert, den der Nutzer wirklich durchgehend
 *    erreicht hat.
 */

import { FaceLandmarker, FilesetResolver } from './vendor/vision_bundle.mjs';

const MODELL_URL = 'https://storage.googleapis.com/mediapipe-models/'
  + 'face_landmarker/face_landmarker/float16/1/face_landmarker.task';
const WASM_PFAD = './vendor/wasm';

// Mengen: 2^14 = 16384 Einheiten pro 1.0. normalized landmarks liegen in
// [0,1], z etwa in ±0,05 — der Bereich reicht also bequem, und die Auflösung
// (6e-5 der Bildbreite) ist weit unter einem Pixel.
const MENGE = 16384;

/* Binäres Format je Bild, little-endian:
 *   4      float32  Zeit in Sekunden seit Beginn des Schritts
 *   64     float32  4x4-Kopfmatrix (zeilenweise)
 *   12     float32  Telefonlage alpha/beta/gamma in Grad (NaN = unbekannt)
 *   1*n    uint8    Mimik-Werte (0..255 steht für 0..1)
 *   0..1   –        Füllbyte, damit die Punkte an einer GERADEN Adresse
 *                   beginnen (s. unten)
 *   2*3*m  int16    Messpunkte x,y,z je MENGE
 *
 * Das Füllbyte ist keine Kleinigkeit: eine Int16Array-Sicht verlangt einen
 * geraden Byte-Offset und wirft sonst. Bei 52 Kanälen geht die Rechnung
 * zufällig auf, bei 53 nicht — und ob das Modell 52 oder 53 Kanäle liefert,
 * steht in dessen Datei, nicht in unserer. Lieber ein Byte verschenken als
 * an einer Modellversion scheitern.
 */
const FORMAT = 't:f32 | bs:u8[n] | mat:f32[16] | imu:f32[3] | punkte:i16[3m]';

// Die Schritte. Reihenfolge und Dauern nach docs/04 (2.3); die Texte sind
// für Laien geschrieben, nicht als Kanalnamen.
const SCHRITTE = [
  { id: 'neutral', titel: 'Ruhe', dauer: 3, art: 'neutral',
    text: 'Schau entspannt in die Kamera. Mund locker zu, Gesicht ganz ruhig.' },
  { id: 'laecheln', titel: 'Lächeln', dauer: 2, art: 'max',
    text: 'Bitte so breit lächeln, wie du kannst. Richtig breit.' },
  { id: 'augen_zu', titel: 'Augen zu', dauer: 2, art: 'max',
    text: 'Augen fest zukneifen. Ganz fest.' },
  { id: 'brauen_hoch', titel: 'Brauen hoch', dauer: 2, art: 'max',
    text: 'Brauen so weit hoch, wie es geht. Stirn in Falten.' },
  { id: 'brauen_runter', titel: 'Brauen runter', dauer: 2, art: 'max',
    text: 'Brauen fest zusammenziehen. Finster schauen.' },
  { id: 'mund_auf', titel: 'Mund auf', dauer: 2, art: 'max',
    text: 'Mund weit aufmachen, als ob du „Aah" sagst.' },
  { id: 'kussmund', titel: 'Kussmund', dauer: 2, art: 'max',
    text: 'Lippen spitzen, wie für einen Kuss.' },
  { id: 'wangen', titel: 'Wangen aufblasen', dauer: 2, art: 'max',
    text: 'Backen richtig aufblasen und die Luft halten.' },
  { id: 'kopf_drehen', titel: 'Kopf drehen', dauer: 4, art: 'bewegung',
    text: 'Kopf langsam nach links drehen, zurück, dann nach rechts. Ganz ruhig.' },
];

const $ = (id) => document.getElementById(id);
const zeige = (id) => ['s0', 's1', 's2', 's3'].forEach(
  (k) => $(k).classList.toggle('versteckt', k !== id));

let landmarker = null;
let strom = null;
let namen = [];            // Mimik-Kanalnamen, Reihenfolge wie vom Modell
let lage = { alpha: NaN, beta: NaN, gamma: NaN };

/* ------------------------------------------------------------ Kamera --- */
async function kamera_auf() {
  strom = await navigator.mediaDevices.getUserMedia({
    video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } },
    audio: false,
  });
  for (const el of [$('video'), $('video2')]) {
    el.srcObject = strom;
    await el.play().catch(() => {});
  }
  // iOS verlangt eine ausdrückliche Freigabe für die Lage-Sensoren.
  if (typeof DeviceOrientationEvent !== 'undefined'
      && typeof DeviceOrientationEvent.requestPermission === 'function') {
    try {
      const antwort = await DeviceOrientationEvent.requestPermission();
      if (antwort === 'granted') lage_an();
    } catch (_) { /* bleibt NaN, das ist kein Fehler */ }
  } else {
    lage_an();
  }
}

function lage_an() {
  window.addEventListener('deviceorientation', (e) => {
    lage = { alpha: e.alpha ?? NaN, beta: e.beta ?? NaN, gamma: e.gamma ?? NaN };
  });
}

/* ------------------------------------------------------------ Modell --- */
async function modell_laden(pfad = MODELL_URL) {
  const wasm = await FilesetResolver.forVisionTasks(WASM_PFAD);
  landmarker = await FaceLandmarker.createFromOptions(wasm, {
    baseOptions: { modelAssetPath: pfad, delegate: 'GPU' },
    runningMode: 'VIDEO',
    numFaces: 1,
    outputFaceBlendshapes: true,
    outputFacialTransformationMatrixes: true,
  });
}

function fehler(text, technisch) {
  const el = $('fehler');
  el.classList.remove('versteckt');
  el.innerHTML = '<b>' + text + '</b>'
    + (technisch ? '<br><span class="klein">' + technisch + '</span>' : '');
  console.error(text, technisch);
}

/* -------------------------------------------------- Aufzeichnung ------ */
class Aufzeichnung {
  constructor(mit_punkten) { this.mit_punkten = mit_punkten; this.schritte = {}; }
  schritt_auf(id) {
    if (!this.schritte[id]) this.schritte[id] = { bilder: [], punkte: [] };
    return this.schritte[id];
  }
  bild(ziel, t, ergebnis) {
    const bs = new Uint8Array(namen.length);
    const kategorien = ergebnis.faceBlendshapes?.[0]?.categories ?? [];
    for (const k of kategorien) {
      const i = namen.indexOf(k.categoryName);
      if (i >= 0) bs[i] = Math.max(0, Math.min(255, Math.round(k.score * 255)));
    }
    ziel.bilder.push({
      t,
      bs,
      mat: Float32Array.from(ergebnis.facialTransformationMatrixes?.[0]?.data
        ?? new Array(16).fill(NaN)),
      imu: Float32Array.from([lage.alpha, lage.beta, lage.gamma]),
    });
    if (this.mit_punkten) {
      const p = ergebnis.faceLandmarks?.[0] ?? [];
      const q = new Int16Array(p.length * 3);
      for (let i = 0; i < p.length; i++) {
        q[i * 3] = Math.max(-32768, Math.min(32767, Math.round(p[i].x * MENGE)));
        q[i * 3 + 1] = Math.max(-32768, Math.min(32767, Math.round(p[i].y * MENGE)));
        q[i * 3 + 2] = Math.max(-32768, Math.min(32767, Math.round(p[i].z * MENGE)));
      }
      ziel.punkte.push(q);
    }
  }
}

const aufzeichnung = new Aufzeichnung(true);

/* ------------------------------------------------------- Kalibrierung -- */
function perzentil(feld, p) {
  const s = Float64Array.from(feld).sort();
  if (!s.length) return NaN;
  return s[Math.min(s.length - 1, Math.max(0, Math.round((s.length - 1) * p)))];
}

function kalibrieren(auf) {
  const neutral = auf.schritte.neutral?.bilder ?? [];
  const max_bilder = [];
  for (const s of SCHRITTE) {
    if (s.art === 'max') max_bilder.push(...(auf.schritte[s.id]?.bilder ?? []));
  }
  const aus = [];
  for (let k = 0; k < namen.length; k++) {
    const ruhe = perzentil(neutral.map((b) => b.bs[k] / 255), 0.5);
    const max = perzentil(max_bilder.map((b) => b.bs[k] / 255), 0.95);
    const abstand = (isFinite(ruhe) && isFinite(max)) ? max - ruhe : NaN;
    aus.push({ kanal: namen[k], ruhe, max, abstand,
               schwach: !(abstand >= 0.15) });
  }
  return aus;
}

/* ------------------------------------------------------------ Export --- */
function paket_bauen(kalib, bilder_geber) {
  const n = namen.length;
  let m = 0;
  let anzahl = 0;
  const bloecke = [];
  for (const s of SCHRITTE) {
    const ziel = aufzeichnung.schritte[s.id];
    if (!ziel || !ziel.bilder.length) continue;
    // Punktzahl kann zwischen Schritten wechseln (Gesicht kurz weg) — die
    // Schrittweite wird deshalb je Schritt festgehalten.
    m = ziel.punkte.length ? ziel.punkte[0].length : 0;
    const n_pad = n + (n % 2);            // Füllbyte, s. FORMAT
    const schrittweite = 4 + 64 + 12 + n_pad + 2 * m;
    const puffer = new ArrayBuffer(ziel.bilder.length * schrittweite);
    const sicht = new DataView(puffer);
    const bytes = new Uint8Array(puffer);
    let o = 0;
    for (let i = 0; i < ziel.bilder.length; i++) {
      const b = ziel.bilder[i];
      sicht.setFloat32(o, b.t, true); o += 4;
      for (let j = 0; j < 16; j++) { sicht.setFloat32(o, b.mat[j], true); o += 4; }
      for (let j = 0; j < 3; j++) { sicht.setFloat32(o, b.imu[j], true); o += 4; }
      bytes.set(b.bs, o); o += n_pad;
      if (m) {
        const q = ziel.punkte[i] ?? new Int16Array(m);
        new Int16Array(puffer, o, m).set(q); o += 2 * m;
      }
    }
    anzahl += ziel.bilder.length;
    bloecke.push({ schritt: s.id, art: s.art, bilder: ziel.bilder.length,
                   punkte: m / 3, schrittweite,
                   daten: b64(bytes) });
  }
  return {
    format: 'FaceScan Capture',
    schemaVersion: 1,
    erzeuger: 'prototype/capture/app.js',
    zeitstempel: new Date().toISOString(),
    layout: FORMAT,
    menge: MENGE,
    kanaele: { anzahl: n, namen, benennung: 'ARKit (MediaPipe-Reihenfolge)',
               hinweis: '*Left/*Right zaehlen von der Seite der Person, '
                        + 'nicht von der des Betrachters.' },
    bilder_gesamt: anzahl,
    kalibrierung: kalib.map((k) => ({
      kanal: k.kanal, ruhe: runde(k.ruhe), max: runde(k.max),
      abstand: runde(k.abstand), schwach_messbar: k.schwach,
    })),
    schwach_messbar: kalib.filter((k) => k.schwach).map((k) => k.kanal),
    bloecke,
    einzelbilder: bilder_geber ? bilder_geber() : null,
  };
}

const runde = (x) => (isFinite(x) ? Math.round(x * 10000) / 10000 : null);

function b64(bytes) {
  let s = '';
  const st = 0x8000;
  for (let i = 0; i < bytes.length; i += st) {
    s += String.fromCharCode.apply(null, bytes.subarray(i, i + st));
  }
  return btoa(s);
}

/* ------------------------------------------------------- Ablauf ------- */
function warten(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function countdown(sekunden) {
  const el = $('s2-countdown');
  el.classList.remove('versteckt');
  for (let i = sekunden; i > 0; i--) {
    el.textContent = i;
    await warten(1000);
  }
  el.classList.add('versteckt');
}

async function schritt_aufnehmen(schritt, liste_el) {
  $('s2-titel').textContent = schritt.titel;
  $('s2-anweisung').textContent = schritt.text;
  await countdown(3);

  const ziel = aufzeichnung.schritt_auf(schritt.id);
  const start = performance.now();
  const dauer_ms = schritt.dauer * 1000;
  const balken = $('s2-balken');
  const status = $('s2-status');

  return new Promise((fertig) => {
    function rahmen() {
      const jetzt = performance.now();
      const t = (jetzt - start) / 1000;
      const anteil = Math.min(1, (jetzt - start) / dauer_ms);
      balken.style.width = (100 * anteil) + '%';
      if (jetzt - start >= dauer_ms) { fertig(ziel.bilder.length); return; }

      let ergebnis = null;
      try {
        // WICHTIG: das ungespiegelte Original — CSS dreht nur die Anzeige.
        ergebnis = landmarker.detectForVideo($('video2'), jetzt);
      } catch (_) { /* einzelne Bilder dürfen scheitern */ }

      if (ergebnis && ergebnis.faceLandmarks?.length) {
        aufzeichnung.bild(ziel, t, ergebnis);
        status.textContent = 'Gesicht erfasst';
        status.className = 'status ok';
      } else {
        status.textContent = 'Kein Gesicht';
        status.className = 'status schlecht';
      }
      requestAnimationFrame(rahmen);
    }
    requestAnimationFrame(rahmen);
  });
}

async function aufnahme_lauf() {
  const liste = $('s2-liste');
  liste.innerHTML = SCHRITTE.map(
    (s) => '<li data-id="' + s.id + '">' + s.titel
      + ' <span class="klein">(' + s.dauer + ' s)</span></li>').join('');
  const zaehler = {};
  for (const s of SCHRITTE) {
    liste.querySelector('[data-id="' + s.id + '"]').className = 'dran';
    const n = await schritt_aufnehmen(s, liste);
    zaehler[s.id] = n;
    liste.querySelector('[data-id="' + s.id + '"]').className =
      n > 0 ? 'fertig' : '';
    await warten(400);
  }
  return zaehler;
}

function ergebnis_zeigen(zaehler, kalib) {
  const gesamt = Object.values(zaehler).reduce((a, b) => a + b, 0);
  const schwach = kalib.filter((k) => k.schwach);
  $('s3-zusammenfassung').innerHTML =
    gesamt + ' Bilder aufgenommen · ' + namen.length + ' Mimik-Kanäle · '
    + schwach.length + ' davon schwach messbar.';

  const schlechte = Object.entries(zaehler).filter(([, n]) => n === 0);
  const w = $('s3-warnung');
  if (schlechte.length) {
    w.classList.remove('versteckt');
    w.innerHTML = '<b>Kein Gesicht erkannt bei:</b> '
      + schlechte.map(([id]) => SCHRITTE.find((s) => s.id === id).titel).join(', ')
      + '<br>Versuch es nochmal mit mehr Licht und dem Gesmittig im Oval.';
  } else if (schwach.length > namen.length / 2) {
    w.classList.remove('versteckt');
    w.innerHTML = '<b>Über die Hälfte der Kanäle ist schwach messbar.</b> '
      + 'Meist hilft es, die Ausdrücke wirklich übertrieben zu machen.';
  } else {
    w.classList.add('versteckt');
  }

  $('s3-tabelle').innerHTML = kalib.map((k) => {
    const klasse = !isFinite(k.abstand) ? 'schwach'
      : k.abstand >= 0.30 ? 'gut' : k.abstand >= 0.15 ? 'knapp' : 'schwach';
    return '<tr><td>' + k.kanal + '</td>'
      + '<td class="zahl">' + runde(k.ruhe) + '</td>'
      + '<td class="zahl">' + runde(k.max) + '</td>'
      + '<td class="zahl ' + klasse + '">' + runde(k.abstand) + '</td></tr>';
  }).join('');
  zeige('s3');
}

/* ------------------------------------------------------------ Start --- */
async function haupt() {
  $('b-start').onclick = async () => {
    zeige('s1');
    $('s1-text').textContent = 'Kamera wird geöffnet …';
    try {
      await kamera_auf();
    } catch (e) {
      $('s1-text').textContent = 'Die Kamera ließ sich nicht öffnen.';
      fehler('Kein Zugriff auf die Kamera.',
        'Der Browser muss die Kamera freigeben. Prüfe in den Einstellungen, '
        + 'ob diese Seite die Kamera darf. ' + e.message);
      return;
    }
    $('s1-text').textContent = 'Bring dein Gesicht ins Oval.';
    try {
      await modell_laden();
    } catch (e) {
      $('s1-text').textContent = 'Das Gesichtsmodell ließ sich nicht laden.';
      fehler('Das Gesichtsmodell konnte nicht geladen werden.',
        'Es wird von Google-Servern geholt. Ist das Telefon online? '
        + 'Technisch: ' + e.message);
      return;
    }
    // Erstes Bild liefert die Kanalnamen — die Reihenfolge ist Teil des
    // Modells und darf nicht geraten werden.
    await warten(600);
    const probe = landmarker.detectForVideo($('video'), performance.now());
    namen = (probe?.faceBlendshapes?.[0]?.categories ?? []).map((k) => k.categoryName);
    if (!namen.length) {
      $('s1-text').textContent = 'Bitte ins Oval schauen …';
    }

    setInterval(() => {
      let ok = false;
      try {
        ok = !!landmarker.detectForVideo($('video'), performance.now())
          .faceLandmarks?.length;
      } catch (_) { /* ignorieren */ }
      if (ok && !namen.length) {
        const p = landmarker.detectForVideo($('video'), performance.now());
        namen = (p?.faceBlendshapes?.[0]?.categories ?? []).map((k) => k.categoryName);
      }
      const el = $('s1-status');
      el.textContent = ok ? 'Gesicht erfasst' : 'Kein Gesicht';
      el.className = 'status ' + (ok ? 'ok' : 'schlecht');
      $('b-weiter').disabled = !ok;
    }, 250);
  };

  $('b-weiter').onclick = async () => {
    zeige('s2');
    const zaehler = await aufnahme_lauf();
    const kalib = kalibrieren(aufzeichnung);
    window.__kalib = kalib;
    window.__zaehler = zaehler;
    ergebnis_zeigen(zaehler, kalib);
  };

  $('b-sichern').onclick = async () => {
    const mit_bildern = $('s3-bilder').checked;
    let bilder_geber = null;
    if (mit_bildern) {
      const liste = [];
      for (const s of SCHRITTE) {
        const ziel = aufzeichnung.schritte[s.id];
        if (!ziel) continue;
        for (let i = 0; i < ziel.bilder.length; i += 6) {
          const c = document.createElement('canvas');
          const quelle = $('video2');
          c.width = 320;
          c.height = Math.round(320 * (quelle.videoHeight || 720)
                                / Math.max(1, quelle.videoWidth || 1280));
          c.getContext('2d').drawImage(quelle, 0, 0, c.width, c.height);
          liste.push({ schritt: s.id, t: ziel.bilder[i].t,
                       jpeg: c.toDataURL('image/jpeg', 0.7) });
        }
      }
      bilder_geber = () => liste;
    }
    const paket = paket_bauen(window.__kalib, bilder_geber);
    const blob = new Blob([JSON.stringify(paket)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'facescan-aufnahme-'
      + new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-') + '.json';
    a.click();
    URL.revokeObjectURL(a.href);
  };

  $('b-nochmal').onclick = () => location.reload();
}

if (!('mediaDevices' in navigator)) {
  fehler('Dieser Browser kennt keine Kamera.',
    'getUserMedia fehlt. Bitte Chrome oder Safari benutzen.');
} else {
  haupt();
}
