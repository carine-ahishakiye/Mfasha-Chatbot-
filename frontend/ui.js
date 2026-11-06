(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var app = $('app');
  if (!app) return;

  var KEY_SET = 'mfasha-settings', KEY_READ = 'mfasha-notices-read';
  function load(key, fallback) { try { return JSON.parse(localStorage.getItem(key)) || fallback; } catch (e) { return fallback; } }
  function save(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) {} }

  /* ---------- settings ---------- */
  var settings = load(KEY_SET, { size: 'normal', theme: 'dark' });
  var root = document.documentElement;
  function setView() { root.setAttribute('data-view', location.hash === '#chat' ? 'chat' : 'other'); }
  window.addEventListener('hashchange', setView); setView();
  function applySettings() {
    app.setAttribute('data-size', settings.size);
    root.setAttribute('data-theme', settings.theme === 'light' ? 'light' : 'dark');
    document.querySelectorAll('#theme-seg button').forEach(function (b) {
      b.setAttribute('aria-checked', b.dataset.theme === (settings.theme === 'light' ? 'light' : 'dark') ? 'true' : 'false');
    });
    document.querySelectorAll('#size-seg button').forEach(function (b) {
      b.setAttribute('aria-checked', b.dataset.size === settings.size ? 'true' : 'false');
    });
  }
  applySettings();
  document.querySelectorAll('#size-seg button').forEach(function (b) {
    b.addEventListener('click', function () { settings.size = b.dataset.size; save(KEY_SET, settings); applySettings(); });
  });

  document.querySelectorAll('#theme-seg button').forEach(function (b) {
    b.addEventListener('click', function () { settings.theme = b.dataset.theme; save(KEY_SET, settings); applySettings(); });
  });

  /* ---------- panels (one open at a time) ---------- */
  var scrim = $('ui-scrim'), notif = $('notif-panel'), drawer = $('settings-panel');
  var bell = $('open-notif'), gear = $('open-settings'), lastTrigger = null;

  function closeAll() {
    var wasOpen = !notif.hidden || !drawer.hidden;
    if (!notif.hidden) markAllRead();
    notif.hidden = true; drawer.hidden = true; scrim.hidden = true;
    bell.setAttribute('aria-expanded', 'false'); gear.setAttribute('aria-expanded', 'false');
    if (wasOpen && lastTrigger) lastTrigger.focus();
  }
  function open(panel, trigger, focusEl) {
    var same = !panel.hidden;
    closeAll();
    if (same) return;
    lastTrigger = trigger; panel.hidden = false; scrim.hidden = false;
    trigger.setAttribute('aria-expanded', 'true');
    if (focusEl) focusEl.focus();
  }
  scrim.addEventListener('click', closeAll);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && (!notif.hidden || !drawer.hidden)) closeAll(); });
  $('close-settings').addEventListener('click', closeAll);
  gear.addEventListener('click', function () { open(drawer, gear, $('close-settings')); });
  var sideSettings = $('side-settings');
  if (sideSettings) sideSettings.addEventListener('click', function () { app.classList.remove('open'); open(drawer, sideSettings, $('close-settings')); });
  $('settings-clear').addEventListener('click', function () {
    closeAll(); $('clear-history').click();     // reuses the confirm dialog and logic in chat.js
  });

  /* ---------- notifications ---------- */
  var TIPS = [
    'Baza ikibazo kimwe icyarimwe kugira ngo igisubizo kibe kinoze.',
    'Vuga izina ry’igihingwa cyangwa itungo n’ikibazo gihari, bizafasha Mfasha kubona igisubizo.',
    'Aho urusaku ari rwinshi, andika ikibazo aho kukivuga.',
    'Itungo ryarwaye cyane ni ikibazo cyihutirwa: baza veterineri vuba.',
    'Urashobora kugaragaza niba igisubizo cyagufashije, bigatuma Mfasha irushaho kuba nziza.'
  ];
  var health = null;      // null = unknown, false = unreachable, object = ok
  var ICON = {
    hello: '<path d="M12 22V9"/><path d="M12 9c0-3.2 2.1-5.3 5.5-5.5 0 3.4-2.2 5.5-5.5 5.5z"/><path d="M12 14c0-3.2-2.1-5.3-5.5-5.5 0 3.4 2.2 5.5 5.5 5.5z"/>',
    tip: '<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z"/>',
    ok: '<path d="m5 12 5 5L20 7"/>',
    warn: '<path d="M12 4 2.5 20h19z"/><path d="M12 10v4M12 17.5v.01"/>'
  };
  function today() { var d = new Date(); return d.getFullYear() + '-' + (d.getMonth() + 1) + '-' + d.getDate(); }
  function dayNumber() { return Math.floor(Date.now() / 864e5); }

  function notices() {
    var list = [];
    if (health === false) {
      list.push({ id: 'down-' + today(), kind: 'warn', icon: 'warn', title: 'Seriveri ntiboneka',
        text: 'Reba ko murandasi ikora, hanyuma wongere ugerageze. Ibibazo ntibishobora gusubizwa ubu.' });
    } else if (health) {
      list.push({ id: 'ok', kind: 'ok', icon: 'ok', title: 'Mfasha irakora neza',
        text: 'Ifite ibisubizo ' + (health.reviewed_passages || health.passages || 0) + ' byasuzumwe n’abakozi b’ubuhinzi.' });
    }
    list.push({ id: 'tip-' + today(), kind: 'tip', icon: 'tip', title: 'Inama y’uyu munsi', text: TIPS[dayNumber() % TIPS.length] });
    list.push({ id: 'hello', kind: 'ok', icon: 'hello', title: 'Murakaza neza kuri Mfasha',
      text: 'Baza ikibazo ku buhinzi n’ubworozi, wandike cyangwa uvuge mu Kinyarwanda.' });
    return list;
  }
  function readSet() { return load(KEY_READ, []); }
  function unreadCount() { var r = readSet(); return notices().filter(function (n) { return r.indexOf(n.id) < 0 && n.id !== 'ok'; }).length; }

  function renderBadge() {
    var n = unreadCount(), b = $('notif-badge');
    b.hidden = n === 0; b.textContent = n;
    bell.setAttribute('aria-label', n ? 'Ibimenyeshwa, bishya ' + n : 'Ibimenyeshwa');
    $('mark-read').disabled = n === 0;
  }
  function renderList() {
    var r = readSet(), ul = $('notif-list');
    ul.replaceChildren();
    notices().forEach(function (n) {
      var unread = r.indexOf(n.id) < 0 && n.id !== 'ok';
      var li = document.createElement('li');
      li.className = 'notice' + (unread ? ' unread' : '') + (n.kind === 'warn' ? ' warn' : '');
      li.innerHTML = '<span class="n-ic"><svg viewBox="0 0 24 24" aria-hidden="true">' + ICON[n.icon] + '</svg></span>' +
        '<div><h3></h3><p></p></div>';
      li.querySelector('h3').textContent = n.title;
      li.querySelector('p').textContent = n.text;
      ul.appendChild(li);
    });
  }
  function markAllRead() {
    var r = readSet();
    notices().forEach(function (n) { if (r.indexOf(n.id) < 0) r.push(n.id); });
    save(KEY_READ, r.slice(-60)); renderBadge();
  }
  function refreshHealth() {
    return fetch('/api/health').then(function (res) { return res.ok ? res.json() : false; })
      .catch(function () { return false; }).then(function (h) { health = h; renderBadge(); renderList(); });
  }

  bell.addEventListener('click', function () {
    renderList(); open(notif, bell, $('mark-read')); refreshHealth();
  });
  $('mark-read').addEventListener('click', function () { markAllRead(); renderList(); });

  /* ---------- about line in settings ---------- */
  function fillAbout() {
    var el = $('about-line');
    if (health) el.textContent = 'Verisiyo ' + (health.version || '') + ' · ibisubizo ' + (health.reviewed_passages || health.passages || 0);
  }
  gear.addEventListener('click', function () { refreshHealth().then(fillAbout); });
  if (sideSettings) sideSettings.addEventListener('click', function () { refreshHealth().then(fillAbout); });

  refreshHealth();
  renderBadge();
}());
