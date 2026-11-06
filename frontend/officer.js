(function () {
  'use strict';

  var API = window.MFASHA_API || '/api';
  var KEY_STORE = 'mfasha-officer-key', NAME_STORE = 'mfasha-officer-name', ROLE_STORE = 'mfasha-role';
  var $ = function (id) { return document.getElementById(id); };

  var apiKey = '', reviewer = '', current = null, queueAvailable = true;

  /* ---------- helpers ---------- */
  function show(el, on) { el.hidden = !on; }
  function say(el, text) { el.textContent = text || ''; show(el, !!text); }
  function pct(x) { return x == null ? '—' : Math.round(x * 1000) / 10 + '%'; }
  function store(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  function load(k) { try { return localStorage.getItem(k) || ''; } catch (e) { return ''; } }
  function clear(k) { try { localStorage.removeItem(k); } catch (e) {} }

  async function call(path, options) {
    options = options || {};
    options.headers = Object.assign({ 'X-API-Key': apiKey }, options.headers || {});
    var res;
    try { res = await fetch(API + path, options); }
    catch (e) { throw httpError(0); }
    if (!res.ok) {
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
    if (status === 401) return 'Urufunguzo rw’ibanga ntirwemewe.';
    if (status === 503) return 'Igice cy’abakozi ntikirafungurwa kuri seriveri (MFASHA_API_KEY ntiyashyizweho).';
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

  function enter() {
    show($('login-view'), false); show($('app-view'), true);
    $('who').textContent = reviewer;
    loadStats(); loadQueue();
  }

  $('login-form').addEventListener('submit', async function (e) {
    e.preventDefault();
    var btn = $('login-btn'); btn.disabled = true; say($('login-error'), '');
    apiKey = $('apikey').value.trim(); reviewer = $('reviewer').value.trim();
    try {
      await call('/admin/stats');                     // a valid key is the only way this succeeds
      store(KEY_STORE, apiKey); store(NAME_STORE, reviewer); store(ROLE_STORE, 'officer');
      $('apikey').value = '';
      enter();
    } catch (err) { apiKey = ''; say($('login-error'), err.message); }
    finally { btn.disabled = false; }
  });

  $('logout').addEventListener('click', function () {
    clear(KEY_STORE); clear(NAME_STORE); apiKey = ''; reviewer = ''; current = null;
    show($('app-view'), false); show($('login-view'), true); $('reviewer').focus();
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
  function statCard(value, label) {
    var d = document.createElement('div'); d.className = 'o-stat';
    var b = document.createElement('b'); b.textContent = value;
    var s = document.createElement('span'); s.textContent = label;
    d.appendChild(b); d.appendChild(s); return d;
  }
  async function loadStats() {
    say($('stats-error'), '');
    try {
      var s = await call('/admin/stats'), grid = $('stats-grid');
      grid.replaceChildren(
        statCard(s.questions, 'Ibibazo byose'),
        statCard(s.answered, 'Byasubijwe'),
        statCard(s.referred, 'Byoherejwe ku mukozi'),
        statCard(pct(s.referral_rate), 'Igipimo cyo kohereza'),
        statCard(Math.round(s.avg_latency_ms) + ' ms', 'Igihe gisanzwe cyo gusubiza'),
        statCard(s.feedback_count, 'Ibitekerezo by’abahinzi'),
        statCard(pct(s.useful_rate), 'Byafashije abahinzi'),
        statCard(s.expert_reviews, 'Ibisubizo byasuzumwe')
      );
      var rate = s.officer_correct_or_partial_rate, card = $('target-card');
      show(card, true);
      $('target-text').textContent = rate == null
        ? 'Nta bisubizo biraba byasuzumwa.'
        : 'Ibisubizo byemewe (ukuri cyangwa ukuri igice): ' + pct(rate) + ' kuri ' + s.expert_reviews + ' byasuzumwe.';
      var fill = $('target-fill');
      fill.style.width = rate == null ? '0' : Math.min(100, rate * 100) + '%';
      fill.classList.toggle('low', rate != null && rate < 0.7);
    } catch (err) { say($('stats-error'), err.message); }
  }
  $('refresh-stats').addEventListener('click', loadStats);

  /* ---------- review queue ---------- */
  // Expects GET /officer/answers?unreviewed=true&limit=50 returning a list (or {items: [...]}) of
  // {answer_id, question, answer, status, referral_reason, retrieval_score, predicted_category,
  //  passage_id, source, review_status}. If the server does not have it yet (404/405) the
  // officer can still review by typing an answer number.
  async function loadQueue() {
    var list = $('queue-list'); list.replaceChildren();
    var note = function (t) { var p = document.createElement('p'); p.className = 'o-muted'; p.textContent = t; list.appendChild(p); };
    try {
      var data = await call('/officer/answers?unreviewed=true&limit=50');
      var items = Array.isArray(data) ? data : (data.items || []);
      queueAvailable = true;
      if (!items.length) { note('Nta bisubizo bitegereje gusuzumwa.'); return; }
      items.forEach(function (it) {
        var b = document.createElement('button'); b.type = 'button'; b.className = 'o-item';
        var t = document.createElement('b'); t.textContent = it.question || '(nta kibazo)';
        var s = document.createElement('small'); s.textContent = '#' + it.answer_id + ' · ' + (it.status === 'referred' ? 'Cyoherejwe' : 'Cyasubijwe');
        b.appendChild(t); b.appendChild(s);
        b.addEventListener('click', function () { openReview(it, b); });
        list.appendChild(b);
      });
    } catch (err) {
      if (err.status === 404 || err.status === 405) {
        queueAvailable = false;
        note('Urutonde rw’ibitegereje ntiruraboneka kuri seriveri. Andika nimero y’igisubizo hasi.');
      } else note(err.message);
    }
  }
  $('refresh-queue').addEventListener('click', loadQueue);

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
      apiKey = ''; clear(KEY_STORE); show($('login-view'), true); $('reviewer').value = reviewer;
    });
  } else { show($('login-view'), true); $('reviewer').focus(); }
}());