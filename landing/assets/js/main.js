/* FaceScan – Landingpage
   Keine externen Abhängigkeiten, keine Tracker, keine Cookies.
   Features: Tag/Nacht-Umschaltung, Vergleichsregler, Adresse kopieren.
*/
(function () {
  'use strict';

  /* ---------- Theme ---------- */
  var STORAGE_KEY = 'facescan-theme';
  var root = document.documentElement;

  function applyTheme(theme) {
    root.setAttribute('data-theme', theme);
    try { localStorage.setItem(STORAGE_KEY, theme); } catch (e) { /* Storage blockiert – ignorieren */ }
  }

  var stored = null;
  try { stored = localStorage.getItem(STORAGE_KEY); } catch (e) { /* noop */ }

  var prefersLight = window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches;
  applyTheme(stored ? stored : (prefersLight ? 'light' : 'dark'));

  var toggle = document.getElementById('theme-toggle');
  if (toggle) {
    toggle.addEventListener('click', function () {
      var next = root.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
      applyTheme(next);
    });
  }

  /* ---------- Vergleichsregler (Foto ↔ 3D-Modell) ---------- */
  var compare = document.getElementById('compare');
  if (compare) {
    var slider = compare.querySelector('input[type="range"]');
    function update() {
      compare.style.setProperty('--pos', slider.value + '%');
    }
    slider.addEventListener('input', update);
    update();
  }

  /* ---------- Adresse kopieren ---------- */
  Array.prototype.forEach.call(document.querySelectorAll('[data-copy]'), function (btn) {
    btn.addEventListener('click', function () {
      var value = btn.getAttribute('data-copy');
      var original = btn.textContent;
      function done(ok) {
        btn.textContent = ok ? '✔ Kopiert' : (btn.lang === 'en' ? 'Copy failed' : 'Kopieren fehlgeschlagen');
        setTimeout(function () { btn.textContent = original; }, 1800);
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(value).then(function () { done(true); }, function () { done(false); });
      } else {
        // Fallback für alte Browser / unsichere Kontexte
        var ta = document.createElement('textarea');
        ta.value = value;
        ta.setAttribute('readonly', '');
        ta.style.position = 'absolute';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.select();
        var ok = false;
        try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
        document.body.removeChild(ta);
        done(ok);
      }
    });
  });
})();
