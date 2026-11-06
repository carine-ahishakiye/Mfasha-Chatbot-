(function () {
  'use strict';

  var API = window.MFASHA_API || '/api';
  var KEY_STORE = 'mfasha-officer-token', NAME_STORE = 'mfasha-officer-name', ROLE_STORE = 'mfasha-role';
  var $ = function (id) { return document.getElementById(id); };

  var apiKey = '', reviewer = '', current = null, queueAvailable = true, queueFilter = 'pending';

  /* ---------- helpers ---------- */
  function show(el, on) { el.hidden = !on; }
  function say(el, text) { el.textContent = text || ''; show(el, !!text); }
  function pct(x) { return x == null ? '—' : Math.round(x * 1000) / 10 + '%'; }
  function store(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  function load(k) { try { return localStorage.getItem(k) || ''; } catch (e) { return ''; } }
  function clear(k) { try { localStorage.removeItem(k); } catch (e) {} }
  function two(n) { return (n < 10 ? '0' : '') + n; }
  function stamp(id) { var d = new Date(); $(id).textContent = 'Byavuguruwe saa ' + two(d.getHours()) + ':' + two(d.getMinutes()) + ':' + two(d.getSeconds()); }
  // Runs a refresh with a visible spinner (kept at least 500 ms so the click is noticeable).
  async function refreshWith(btn, stampId, job) {
    if (btn.disabled) return;
    btn.disabled = true; btn.classList.add('busy'); $(stampId).textContent = 'Ndimo kuvugurura…';
    var started = Date.now(), ok = false;
    try { ok = await job(); } catch (e) { ok = false; }
    var wait = Math.max(0, 500 - (Date.now() - started));
    setTimeout(function () {
      btn.disabled = false; btn.classList.remove('busy');
      if (ok) stamp(stampId); else $(stampId).textContent = 'Ntibyavuguruwe. Ongera ugerageze.';
    }, wait);
  }

  async function call(path, options) {
    options = options || {};
    options.cache = 'no-store';
    options.headers = Object.assign(apiKey ? { 'Authorization': 'Bearer ' + apiKey } : {}, options.headers || {});
    var res;
    try { res = await fetch(API + path, options); }
    catch (e) { throw httpError(0); }
    if (!res.ok) {
      if (res.status === 401 && apiKey && !options.isLogin) { sessionExpired(); }
      var info = await res.json().catch(function () { return {}; });
      var detail = Array.isArray(info.detail) ? info.detail.map(function (d) { return d.msg; }).join('; ') : info.detail;
      throw httpError(res.status, detail);
    }
    return res.json();
  }
  function httpError(status, detail) {
    var e = new Error(message(status, detail)); e.status = status; return e;
  }
  function message(status, detail) {
    if (status === 0) return 'Ntabwo bishoboka kugera kuri seriveri. Reba murandasi yawe.';
    if (status === 401) return 'Igihe cyo kwinjira cyarangiye. Ongera winjire.';
    if (status === 429) return 'Wagerageje kenshi PIN itari yo. Ongera ugerageze nyuma y’iminota 5.';
    if (status === 503) return 'Igice cy’abakozi ntikirafungurwa kuri seriveri.';
    if (status === 404) return 'Iki gisubizo ntikibonetse.';
    return detail || 'Habaye ikibazo. Ongera ugerageze.';
  }

  /* ---------- role / login ---------- */
  function switchRole(e) {
    if (e) e.preventDefault();
    clear(ROLE_STORE); try { sessionStorage.removeItem(ROLE_STORE); } catch (e) {} clear(KEY_STORE); clear(NAME_STORE);
    location.href = 'index.html';
  }
  $('switch-role-login').addEventListener('click', switchRole);

  /* ---------- sign in / create account tabs ---------- */
  function showForm(which) {
    var reg = which === 'register';
    show($('login-form'), !reg); show($('register-form'), reg);
    $('tab-login').setAttribute('aria-selected', reg ? 'false' : 'true');
    $('tab-register').setAttribute('aria-selected', reg ? 'true' : 'false');
    say($('login-error'), ''); say($('register-error'), '');
    $(reg ? 'reg-name' : 'phone').focus();
  }
  $('tab-login').addEventListener('click', function () { showForm('login'); });
  $('tab-register').addEventListener('click', function () { showForm('register'); });

  function signedIn(r) {
    apiKey = r.token; reviewer = r.name;
    store(KEY_STORE, apiKey); store(NAME_STORE, reviewer); store(ROLE_STORE, 'officer');
    enter();
  }

  $('register-form').addEventListener('submit', async function (e) {
    e.preventDefault();
    var btn = $('register-btn'); btn.disabled = true; say($('register-error'), '');
    var pin = $('reg-pin').value.trim();
    if (!/^\d{4,6}$/.test(pin)) { say($('register-error'), 'PIN igomba kuba imibare 4 kugeza kuri 6.'); btn.disabled = false; return; }
    if (pin !== $('reg-pin2').value.trim()) { say($('register-error'), 'PIN zombi ntizihuye. Ongera ubyandike.'); btn.disabled = false; return; }
    try {
      var r = await call('/officer/register', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, isLogin: true,
        body: JSON.stringify({ name: $('reg-name').value.trim(), phone: $('reg-phone').value.trim(), pin: pin, code: $('reg-code').value.trim() })
      });
      $('register-form').reset();
      signedIn(r);
    } catch (err) {
      var msg = err.message;
      if (err.status === 401) msg = 'Kode yo kwiyandikisha si yo.';
      else if (err.status === 409) msg = 'Iyi nimero ya telefone isanzwe ifite konti. Koresha “Injira”.';
      else if (err.status === 503) msg = 'Kwiyandikisha ntibirafungurwa kuri seriveri. Baza umuyobozi wawe.';
      else if (err.status === 429) msg = 'Wagerageje kode itari yo kenshi. Ongera ugerageze nyuma y’iminota 5.';
      else if (err.status === 422) msg = 'Reba amazina, nimero ya telefone na PIN.';
      say($('register-error'), msg);
    }
    finally { btn.disabled = false; }
  });

  function enter() {
    show($('login-view'), false); show($('app-view'), true);
    $('who').textContent = reviewer;
    var first = reviewer.split(' ')[0];
    $('hello').textContent = first ? 'Muraho, ' + first : 'Muraho';
    loadStats().then(function (ok) { if (ok) stamp('stats-stamp'); });
    loadQueue().then(function (ok) { if (ok) stamp('queue-stamp'); });
  }

  $('login-form').addEventListener('submit', async function (e) {
    e.preventDefault();
    var btn = $('login-btn'); btn.disabled = true; say($('login-error'), '');
    var phone = $('phone').value.trim(), pin = $('pin').value.trim();
    if (!/^\d{4,6}$/.test(pin)) { say($('login-error'), 'PIN igomba kuba imibare 4 kugeza kuri 6.'); btn.disabled = false; return; }
    try {
      var r = await call('/officer/login', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone: phone, pin: pin }), isLogin: true
      });
      $('pin').value = '';
      signedIn(r);
    } catch (err) {
      apiKey = '';
      say($('login-error'), err.status === 401 ? 'Nimero ya telefone cyangwa PIN si byo.' : err.message);
      $('pin').value = '';
    }
    finally { btn.disabled = false; }
  });

  function sessionExpired() {
    clear(KEY_STORE); apiKey = ''; current = null;
    show($('app-view'), false); show($('login-view'), true);
    say($('login-error'), 'Igihe cyo kwinjira cyarangiye. Ongera winjire.');
  }

  $('logout').addEventListener('click', function () {
    clear(KEY_STORE); clear(NAME_STORE); apiKey = ''; reviewer = ''; current = null;
    show($('app-view'), false); show($('login-view'), true); $('phone').focus();
  });

  /* ---------- tabs ---------- */
  function selectTab(name) {
    ['overview', 'review'].forEach(function (t) {
      $('tab-' + t).setAttribute('aria-selected', t === name ? 'true' : 'false');
      show($(t + '-view'), t === name);
    });
  }
  $('tab-overview').addEventListener('click', function () { selectTab('overview'); });
  $('tab-review').addEventListener('click', function () { selectTab('review'); });

  /* ---------- overview ---------- */
  function big(value, label) {
    var d = document.createElement('div'); d.className = 'o-big-item';
    var b = document.createElement('b'); b.textContent = value;
    var s = document.createElement('span'); s.textContent = label;
    d.appendChild(b); d.appendChild(s); return d;
  }
  function ledgerRow(dl, label, value) {
    var dt = document.createElement('dt'); dt.textContent = label;
    var dd = document.createElement('dd'); dd.textContent = value;
    dl.appendChild(dt); dl.appendChild(dd);
  }
  async function loadStats() {
    say($('stats-error'), '');
    try {
      var s = await call('/admin/stats'), grid = $('stats-grid');
      var top = document.createElement('div'); top.className = 'o-big';
      top.appendChild(big(s.questions, 'Ibibazo byose'));
      top.appendChild(big(s.referred, 'Byoherejwe ku mukozi'));
      top.appendChild(big(s.expert_reviews, 'Ibisubizo byasuzumwe'));
      var dl = document.createElement('dl'); dl.className = 'o-ledger';
      ledgerRow(dl, 'Byasubijwe', s.answered);
      ledgerRow(dl, 'Igipimo cyo kohereza', pct(s.referral_rate));
      ledgerRow(dl, 'Igihe gisanzwe cyo gusubiza', Math.round(s.avg_latency_ms) + ' ms');
      ledgerRow(dl, 'Ibitekerezo by’abahinzi', s.feedback_count);
      ledgerRow(dl, 'Byafashije abahinzi', pct(s.useful_rate));
      grid.replaceChildren(top, dl);
      var rate = s.officer_correct_or_partial_rate, card = $('target-card');
      show(card, true);
      $('target-text').textContent = rate == null
        ? 'Nta bisubizo biraba byasuzumwa.'
        : 'Ibisubizo byemewe (ukuri cyangwa ukuri igice): ' + pct(rate) + ' kuri ' + s.expert_reviews + ' byasuzumwe.';
      var fill = $('target-fill');
      fill.style.width = rate == null ? '0' : Math.min(100, rate * 100) + '%';
      fill.classList.toggle('low', rate != null && rate < 0.7);
      return true;
    } catch (err) { say($('stats-error'), err.message); return false; }
  }
  $('refresh-stats').addEventListener('click', function () { refreshWith(this, 'stats-stamp', loadStats); });

  /* ---------- review queue ---------- */
  // Expects GET /officer/answers?unreviewed=true&limit=50 returning a list (or {items: [...]}) of
  // {answer_id, question, answer, status, referral_reason, retrieval_score, predicted_category,
  //  passage_id, source, review_status}. If the server does not have it yet (404/405) the
  // officer can still review by typing an answer number.
  async function loadQueue() {
    var list = $('queue-list'); list.replaceChildren();
    var note = function (t) { var p = document.createElement('p'); p.className = 'o-muted'; p.textContent = t; list.appendChild(p); };
    try {
      var data = await call('/officer/answers?unreviewed=' + (queueFilter === 'pending') + '&limit=50');
      var items = Array.isArray(data) ? data : (data.items || []);
      queueAvailable = true;
      var count = $('queue-count'); count.textContent = items.length; show(count, items.length > 0);
      if (!items.length) { note(queueFilter === 'pending' ? 'Nta bisubizo bitegereje gusuzumwa. Hitamo “Byose” kugira ngo urebe ibisubizo byose.' : 'Nta bisubizo biraboneka. Abahinzi nibabaza ibibazo, bizagaragara hano.'); return true; }
      items.forEach(function (it) {
        var b = document.createElement('button'); b.type = 'button'; b.className = 'o-item';
        var t = document.createElement('b'); t.textContent = it.question || '(nta kibazo)';
        var s = document.createElement('small'); s.textContent = '#' + it.answer_id + ' · ' + (it.status === 'referred' ? 'Cyoherejwe' : 'Cyasubijwe');
        b.appendChild(t); b.appendChild(s);
        b.addEventListener('click', function () { openReview(it, b); });
        list.appendChild(b);
      });
      return true;
    } catch (err) {
      show($('queue-count'), false);
      if (err.status === 404 || err.status === 405) {
        queueAvailable = false;
        note('Urutonde rw’ibitegereje ntiruraboneka kuri seriveri. Andika nimero y’igisubizo hasi.');
      } else note(err.message);
      return false;
    }
  }
  document.querySelectorAll('.o-filter button').forEach(function (b) {
    b.addEventListener('click', function () {
      queueFilter = b.getAttribute('data-f');
      document.querySelectorAll('.o-filter button').forEach(function (x) { x.setAttribute('aria-checked', x === b ? 'true' : 'false'); });
      loadQueue().then(function (ok) { if (ok) stamp('queue-stamp'); });
    });
  });
  $('refresh-queue').addEventListener('click', function () { refreshWith(this, 'queue-stamp', loadQueue); });

  $('lookup-form').addEventListener('submit', async function (e) {
    e.preventDefault();
    var id = parseInt($('answer-id').value, 10);
    if (!id || id < 1) return;
    try {
      var it = await call('/officer/answers/' + id);
      openReview(it, null);
    } catch (err) {
      if (err.status === 404 || err.status === 405) {
        // No lookup endpoint: still allow reviewing by number; the server validates the id on submit.
        openReview({ answer_id: id, question: '', answer: '' }, null);
      } else say($('review-error'), err.message);
    }
  });

  /* ---------- review form ---------- */
  function openReview(it, button) {
    current = it;
    document.querySelectorAll('.o-item.active').forEach(function (n) { n.classList.remove('active'); });
    if (button) button.classList.add('active');
    show($('review-empty'), false); show($('review-body'), true);
    say($('review-error'), ''); say($('review-ok'), '');
    $('r-question').textContent = it.question || 'Ikibazo ntikigaragara. Gisuzume ukoresheje nimero #' + it.answer_id + '.';
    $('r-answer').textContent = it.answer || 'Igisubizo ntikigaragara.';
    var meta = $('review-meta'); meta.replaceChildren();
    var chip = function (t, warn) { var s = document.createElement('span'); s.className = 'o-chip' + (warn ? ' warn' : ''); s.textContent = t; meta.appendChild(s); };
    chip('Igisubizo #' + it.answer_id);
    if (it.status === 'referred') chip('Cyoherejwe ku mukozi', true);
    if (it.predicted_category) chip('Ubwoko: ' + it.predicted_category);
    if (typeof it.retrieval_score === 'number') chip('Amanota: ' + it.retrieval_score.toFixed(2));
    if (it.passage_id) chip('Inyandiko: ' + it.passage_id);
    $('review-form').reset();
    $('review-body').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  $('review-form').addEventListener('submit', async function (e) {
    e.preventDefault();
    if (!current) return;
    var verdict = document.querySelector('input[name=verdict]:checked');
    if (!verdict) { say($('review-error'), 'Hitamo icyemezo cyawe.'); return; }
    var btn = $('submit-review'); btn.disabled = true; say($('review-error'), ''); say($('review-ok'), '');
    var remarks = $('remarks').value.trim();
    try {
      await call('/officer/reviews', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          answer_id: current.answer_id, reviewer: reviewer, verdict: verdict.value,
          is_relevant: $('is-relevant').checked, is_clear: $('is-clear').checked, is_safe: $('is-safe').checked,
          remarks: remarks || null
        })
      });
      say($('review-ok'), 'Isuzuma ryabitswe. Murakoze.');
      $('review-form').reset(); current = null; show($('review-body'), false); show($('review-empty'), true);
      loadQueue(); loadStats();
      say($('review-error'), '');
    } catch (err) { say($('review-error'), err.message); }
    finally { btn.disabled = false; }
  });

  /* ---------- start ---------- */
  apiKey = load(KEY_STORE); reviewer = load(NAME_STORE);
  if (apiKey && reviewer) {
    call('/admin/stats').then(enter).catch(function () {
      apiKey = ''; clear(KEY_STORE); show($('login-view'), true); $('phone').focus();
    });
  } else { show($('login-view'), true); $('phone').focus(); }
}());