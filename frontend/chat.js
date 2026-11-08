(function () {
  'use strict';

  var API = (location.pathname.indexOf('/mfasha/') === 0 ? '/mfasha' : '') + '/api';
  var STORAGE_KEY = 'mfasha-conversations-v2';
  // Put a real email address or phone number here. While it is empty, the deletion-request line stays hidden.
  var PRIVACY_CONTACT = '';
  var MAX_CHARS = 500;
  // Confidence badge, derived from the retriever score (0..1) of an answered question.
  // Anything below the server's referral threshold is already referred, so "low" is rare.
  var HIGH_SCORE = 0.6, MEDIUM_SCORE = 0.35;

  var $ = function (id) { return document.getElementById(id); };
  var app = $('app'), chatForm = $('chat-form'), questionBox = $('question'), sendButton = $('send-button'),
      microphoneButton = $('microphone'), micIcon = $('mic-icon'), micLabel = $('mic-label'),
      statusLine = $('status-line'), thread = $('thread'), emptyState = $('empty-state'),
      historyList = $('history-list'), chatScroll = $('chat-scroll'), historySearch = $('history-search');

  var conversations = [], activeConversationId = null, isBusy = false;
  var recorder = null, micStream = null, recordTimer = null;

  /*  helpers */
  function setStatus(text) { statusLine.textContent = text || ''; }

  async function api(path, options, fallbackMessage) {
    var response = await fetch(API + path, options);
    if (!response.ok) {
      var info = await response.json().catch(function () { return {}; });
      var detail = Array.isArray(info.detail) ? info.detail.map(function (d) { return d.msg; }).join('; ') : info.detail;
      throw new Error(detail || fallbackMessage);
    }
    return response;
  }

  function tierOf(answer) {
    if (answer.status !== 'answered' || typeof answer.retrieval_score !== 'number') return null;
    return answer.retrieval_score >= HIGH_SCORE ? 'high' : answer.retrieval_score >= MEDIUM_SCORE ? 'medium' : 'low';
  }

  /*  storage  */
  function saveConversations() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations)); }
    catch (e) { setStatus('Ntabwo amateka yabitswe kuri iki gikoresho.'); }
  }
  function loadConversations() {
    try {
      var saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
      if (Array.isArray(saved)) conversations = saved;
    } catch (e) { conversations = []; }
    conversations = conversations.filter(function (c) { return c && c.id && Array.isArray(c.items); });
    renderHistory();
  }
  function getActiveConversation() {
    return conversations.find(function (c) { return c.id === activeConversationId; }) || null;
  }

  /* history sidebar  */
  function renderHistory() {
    historyList.replaceChildren();
    if (!conversations.length) {
      var empty = document.createElement('p');
      empty.className = 'no-history'; empty.textContent = 'Nta kiganiro kiraboneka.';
      historyList.appendChild(empty); return;
    }
    var term = (historySearch.value || '').trim().toLowerCase();
    var shown = conversations.filter(function (c) { return !term || (c.title || '').toLowerCase().indexOf(term) !== -1; });
    if (!shown.length) {
      var none = document.createElement('p');
      none.className = 'no-history'; none.textContent = 'Nta kiganiro cyabonetse.';
      historyList.appendChild(none); return;
    }
    shown.sort(function (a, b) {
      return (b.updated || b.created || 0) - (a.updated || a.created || 0);
    }).forEach(function (c) {
      var row = document.createElement('div'); row.className = 'history-row';
      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'history-item' + (c.id === activeConversationId ? ' active' : '');
      button.textContent = c.title || 'Ikiganiro gishya'; button.title = button.textContent;
      button.addEventListener('click', function () { openConversation(c.id); });
      var del = document.createElement('button');
      del.type = 'button'; del.className = 'history-del';
      del.setAttribute('aria-label', 'Siba iki kiganiro'); del.title = 'Siba iki kiganiro';
      del.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"/></svg>';
      del.addEventListener('click', function (ev) { ev.stopPropagation(); deleteConversation(c.id); });
      row.appendChild(button); row.appendChild(del); historyList.appendChild(row);
    });
  }

  function deleteConversation(id) {
    if (!window.confirm('Iki kiganiro kiraseswa kuri telefone yawe gusa. Kopi iri kuri seriveri ya Mfasha ntisibwa. Komeza?')) return;
    conversations = conversations.filter(function (c) { return c.id !== id; });
    saveConversations();
    if (id === activeConversationId) beginNewChat(); else renderHistory();
  }
  function showEmpty(show) { emptyState.hidden = !show; }
  function beginNewChat() {
    activeConversationId = null; thread.replaceChildren(); showEmpty(true);
    renderHistory(); chatScroll.scrollTop = 0; app.classList.remove('open'); questionBox.focus();
  }
  function openConversation(id) {
    var c = conversations.find(function (item) { return item.id === id; });
    if (!c) return;
    activeConversationId = id; thread.replaceChildren(); showEmpty(false);
    c.items.forEach(function (item) {
      var turn = createTurn(item.question);
      if (item.answer) renderAnswer(turn, item.answer, item, true);
      else showAnswerError(turn, 'Iki gisubizo nticyabitswe.');
    });
    renderHistory(); chatScroll.scrollTop = chatScroll.scrollHeight; app.classList.remove('open');
  }

  /* ---------- rendering ---------- */
  function createTurn(question) {
    var article = document.createElement('article'); article.className = 'turn';
    var row = document.createElement('div'); row.className = 'question';
    var bubble = document.createElement('div'); bubble.textContent = question;
    row.appendChild(bubble); article.appendChild(row);
    var card = document.createElement('section'); card.className = 'answer';
    var body = document.createElement('div'); card.appendChild(body); article.appendChild(card);
    thread.appendChild(article);
    return { article: article, card: card, body: body, bubble: bubble };
  }
  function showThinking(turn) {
    var p = document.createElement('p'); p.className = 'thinking'; p.textContent = 'Ndimo gushaka igisubizo…';
    turn.body.appendChild(p); chatScroll.scrollTop = chatScroll.scrollHeight;
  }
  var THUMB = '<svg class="%C" viewBox="0 0 24 24" aria-hidden="true"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>';
  // thumb: 'up' | 'down' | undefined (plain text button)
  function makeButton(text, thumb) {
    var b = document.createElement('button'); b.type = 'button'; b.className = 'tool';
    if (thumb) b.innerHTML = THUMB.replace('%C', thumb);
    var label = document.createElement('span'); label.textContent = text; b.appendChild(label);
    return b;
  }

  async function sendFeedback(item, answerId, useful, button) {
    if (item.vote || item.feedbackPending || answerId == null) return;
    item.feedbackPending = true; button.disabled = true;
    try {
      await api('/feedback', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answer_id: answerId, rating: useful ? 5 : 1, is_useful: useful })
      }, 'Ntabwo igitekerezo cyawe cyabitswe. Ongera ugerageze.');
      item.vote = useful ? 'helpful' : 'not_helpful';
      button.classList.add('selected'); saveConversations(); setStatus('Murakoze ku gitekerezo cyanyu.');
    } catch (error) {
      setStatus(error.message || 'Ntabwo igitekerezo cyawe cyabitswe. Ongera ugerageze.');
    } finally {
      item.feedbackPending = false; button.disabled = !!item.vote;
    }
  }

  function renderAnswer(turn, answer, item, quiet) {
    var refused = answer.status === 'referred';
    turn.body.replaceChildren(); turn.card.classList.toggle('refused', refused);

    var tier = tierOf(answer);
    if (tier) {
      var badge = document.createElement('span');
      badge.className = 'badge ' + tier;
      badge.textContent = 'Icyizere: ' + { high: 'kinshi', medium: 'giciriritse', low: 'gike' }[tier];
      turn.body.appendChild(badge);
      if (tier === 'medium' || tier === 'low') {
        var note = document.createElement('p'); note.className = 'note';
        note.textContent = tier === 'low'
          ? 'Iki gisubizo nticyizewe bihagije. Genzura n’andi makuru.'
          : 'Genzura n’andi makuru kugira ngo wemeze iki gisubizo.';
        turn.body.appendChild(note);
      }
    }

    if (answer.status === 'answered') {
      var rv = document.createElement('p');
      var reviewed = answer.review_status === 'reviewed';
      rv.className = 'review-label ' + (reviewed ? 'ok' : 'pending');
      rv.textContent = reviewed
        ? 'Cyasuzumwe n’umukozi w’ubuhinzi'
        : 'Ntikirasuzumwa n’umukozi w’ubuhinzi. Ntukishingikirize kuri cyo wenyine.';
      turn.body.appendChild(rv);
    }

    var text = document.createElement('p'); text.className = 'answer-text';
    text.textContent = answer.answer || 'Nta gisubizo cyagarutse.'; turn.body.appendChild(text);

    var tools = document.createElement('div'); tools.className = 'tools';

    if (!refused) {
      var yes = makeButton('Byamfashije', 'up');
      yes.disabled = !!item.vote; yes.classList.toggle('selected', item.vote === 'helpful');
      yes.addEventListener('click', function () { sendFeedback(item, answer.answer_id, true, yes); });
      var no = makeButton('Ntibyamfashije', 'down');
      no.disabled = !!item.vote; no.classList.toggle('selected', item.vote === 'not_helpful');
      no.addEventListener('click', function () { sendFeedback(item, answer.answer_id, false, no); });
      var copy = makeButton('Koporora');
      copy.addEventListener('click', function () {
        if (!navigator.clipboard) { setStatus('Iyi mushakisha ntishobora gukoporora.'); return; }
        navigator.clipboard.writeText(answer.answer || '').then(function () {
          setStatus('Igisubizo cyakoporowe.'); setTimeout(function () { setStatus(''); }, 1600);
        }).catch(function () { setStatus('Ntabwo igisubizo cyakoporowe.'); });
      });
      tools.appendChild(yes); tools.appendChild(no); tools.appendChild(copy);
    }
    turn.body.appendChild(tools);
    if (answer.status === 'answered') {
      var urgent = document.createElement('p'); urgent.className = 'urgent-note';
      urgent.textContent = 'Ikibazo cyihutirwa? Baza umukozi w’ubuhinzi cyangwa veterineri. Ku miti, imiti y’amatungo n’indwara, ntukishingikirize kuri Mfasha yonyine.';
      turn.body.appendChild(urgent);
    }
    if (!quiet) turn.article.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  function showAnswerError(turn, message) {
    turn.body.replaceChildren();
    var p = document.createElement('p'); p.className = 'error'; p.textContent = message; turn.body.appendChild(p);
  }

  /* ---------- composer ---------- */
  function resizeQuestion() {
    questionBox.style.height = 'auto';
    questionBox.style.height = Math.min(questionBox.scrollHeight, 140) + 'px';
  }
  function setMicIcon(recording) {
    microphoneButton.classList.toggle('recording', recording);
    microphoneButton.setAttribute('aria-label', recording ? 'Hagarika gufata amajwi' : 'Tangira gufata amajwi');
    micLabel.textContent = recording ? 'Rangiza' : 'Vuga';
    micIcon.innerHTML = recording
      ? '<rect x="6" y="6" width="12" height="12" rx="2"/>'
      : '<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3m-4 0h8"/>';
  }
  function stopMicStream() {
    if (recordTimer) { clearTimeout(recordTimer); recordTimer = null; }
    if (micStream) { micStream.getTracks().forEach(function (t) { t.stop(); }); micStream = null; }
  }
  function releaseControls() { microphoneButton.disabled = false; sendButton.disabled = false; }

  // The backend wants 16 kHz mono WAV, so convert whatever the browser recorded.
  async function toWav(blob) {
    var ctx = new (window.AudioContext || window.webkitAudioContext)();
    var decoded = await ctx.decodeAudioData(await blob.arrayBuffer());
    await ctx.close();
    var offline = new OfflineAudioContext(1, Math.max(1, Math.ceil(decoded.duration * 16000)), 16000);
    var source = offline.createBufferSource();
    source.buffer = decoded; source.connect(offline.destination); source.start();
    return encodeWav((await offline.startRendering()).getChannelData(0), 16000);
  }
  function encodeWav(samples, rate) {
    var buffer = new ArrayBuffer(44 + samples.length * 2), view = new DataView(buffer);
    var write = function (o, s) { for (var i = 0; i < s.length; i++) view.setUint8(o + i, s.charCodeAt(i)); };
    write(0, 'RIFF'); view.setUint32(4, 36 + samples.length * 2, true); write(8, 'WAVEfmt ');
    view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
    view.setUint32(24, rate, true); view.setUint32(28, rate * 2, true); view.setUint16(32, 2, true);
    view.setUint16(34, 16, true); write(36, 'data'); view.setUint32(40, samples.length * 2, true);
    for (var i = 0; i < samples.length; i++) {
      view.setInt16(44 + i * 2, Math.max(-1, Math.min(1, samples[i])) * 0x7fff, true);
    }
    return new Blob([buffer], { type: 'audio/wav' });
  }

  function stopRecording() {
    if (!recorder || recorder.state !== 'recording') return;
    microphoneButton.disabled = true; setStatus('Ndimo gutegura amajwi yawe…');
    try { recorder.stop(); }
    catch (error) {
      recorder = null; stopMicStream(); setMicIcon(false); releaseControls();
      setStatus('Ntabwo amajwi yafashwe. Ongera ugerageze.');
    }
  }

  async function startRecording() {
    if (isBusy || recorder) return;
    if (window.isSecureContext === false && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {
      setStatus('Koresha uru rubuga kuri HTTPS cyangwa localhost kugira ngo ufungure mikoro.'); return;
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
      setStatus('Iyi mushakisha ntishobora gufata amajwi.'); return;
    }
    setStatus('Emera gukoresha mikoro nibigusabwa.');
    try {
      micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      var supported = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4'];
      var mimeType = MediaRecorder.isTypeSupported
        ? (supported.find(function (t) { return MediaRecorder.isTypeSupported(t); }) || '') : '';
      recorder = new MediaRecorder(micStream, mimeType ? { mimeType: mimeType } : undefined);
      var activeRecorder = recorder, chunks = [], failed = false;

      activeRecorder.ondataavailable = function (e) { if (e.data && e.data.size) chunks.push(e.data); };
      activeRecorder.onerror = function () {
        failed = true; recorder = null; stopMicStream(); setMicIcon(false); releaseControls();
        setStatus('Ntabwo amajwi yafashwe. Reba uruhushya rwa mikoro.');
      };
      activeRecorder.onstop = async function () {
        var contentType = activeRecorder.mimeType || mimeType || 'audio/webm';
        recorder = null; stopMicStream(); setMicIcon(false);
        if (failed) return;
        var raw = new Blob(chunks, { type: contentType });
        if (!raw.size) { releaseControls(); setStatus('Nta majwi yafashwe. Ongera ugerageze.'); return; }
        try {
          setStatus('Ndimo kumva ibyo wavuze…');
          var wav = await toWav(raw);
          askVoice(wav);
        } catch (error) {
          releaseControls(); setStatus('Ntabwo amajwi yahinduwe inyandiko. Ongera ugerageze.');
        }
      };
      recorder.start(); sendButton.disabled = true; setMicIcon(true);
      setStatus('Ndakumva. Kanda “Rangiza” nurangiza kuvuga.');
      recordTimer = setTimeout(function () { if (recorder && recorder.state === 'recording') stopRecording(); }, 30000);
    } catch (error) {
      stopMicStream(); recorder = null; setMicIcon(false); microphoneButton.disabled = false;
      setStatus('Ntabwo nashoboye gukoresha mikoro. Reba uruhushya rwa mushakisha.');
    }
  }

  /* ---------- asking ---------- */
  // Shared by text and voice: creates the turn, runs `request`, renders the result.
  async function runTurn(initialQuestion, request) {
    setStatus(''); isBusy = true; sendButton.disabled = true; microphoneButton.disabled = true;
    emptyState.hidden = true; questionBox.value = ''; resizeQuestion();

    var conversation = getActiveConversation();
    if (!conversation) {
      conversation = {
        id: 'c' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7),
        title: initialQuestion.slice(0, 70), created: Date.now(), updated: Date.now(), items: []
      };
      conversations.unshift(conversation); activeConversationId = conversation.id;
    }
    var item = { question: initialQuestion, answer: null, vote: null };
    conversation.items.push(item);
    var turn = createTurn(initialQuestion); showThinking(turn); saveConversations(); renderHistory();

    try {
      var answer = await request();
      if (answer.heard) {                       // voice: show what the server understood
        item.question = answer.heard; turn.bubble.textContent = answer.heard;
        if (conversation.items.length === 1) conversation.title = answer.heard.slice(0, 70);
      }
      item.answer = answer; conversation.updated = Date.now();
      saveConversations(); renderHistory(); renderAnswer(turn, answer, item, false);
    } catch (error) {
      showAnswerError(turn, error.message || 'Habaye ikibazo. Ongera ugerageze.');
    } finally {
      isBusy = false; releaseControls(); questionBox.focus();
    }
  }

  function askQuestion(question) {
    question = (question || '').trim();
    if (question.length > MAX_CHARS) { setStatus('Ikibazo kirenze inyuguti 500. Gabanya inyandiko mbere yo kohereza.'); return; }
    if (!question || isBusy) return;
    runTurn(question, async function () {
      var response = await api('/ask/text', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: question })
      }, 'Habaye ikibazo mu gushaka igisubizo.');
      return response.json();
    });
  }

  function askVoice(wavBlob) {
    runTurn('Ijwi ryawe…', async function () {
      var form = new FormData();
      form.append('audio', wavBlob, 'question.wav');
      var response = await api('/ask/voice', { method: 'POST', body: form }, 'Ntabwo amajwi yahinduwe inyandiko.');
      return response.json();
    });
  }

  /* ---------- wiring ---------- */
  document.querySelectorAll('[data-question]').forEach(function (button) {
    button.addEventListener('click', function () { askQuestion(button.getAttribute('data-question') || ''); });
  });
  chatForm.addEventListener('submit', function (e) { e.preventDefault(); askQuestion(questionBox.value); });
  questionBox.addEventListener('input', resizeQuestion);
  questionBox.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); askQuestion(questionBox.value); }
  });
  microphoneButton.addEventListener('click', function () {
    if (recorder && recorder.state === 'recording') stopRecording();
    else if (!recorder && !microphoneButton.disabled) startRecording();
  });
  $('new-chat').addEventListener('click', beginNewChat);
  historySearch.addEventListener('input', renderHistory);

  var menuButtons = [$('toggle-history'), $('collapse-sidebar')];
  var desktopQuery = window.matchMedia('(min-width:821px)');
  function syncMenu() {
    var expanded = desktopQuery.matches ? !app.classList.contains('collapsed') : app.classList.contains('open');
    var label = expanded ? 'Funga ibiganiro byashize' : 'Fungura ibiganiro byashize';
    menuButtons.forEach(function (b) { b.setAttribute('aria-expanded', expanded ? 'true' : 'false'); b.setAttribute('aria-label', label); b.title = label; });
  }
  function toggleMenu() {
    if (desktopQuery.matches) {
      app.classList.toggle('collapsed');
      try { localStorage.setItem('mfasha-sidebar', app.classList.contains('collapsed') ? 'closed' : 'open'); } catch (e) {}
    } else { app.classList.toggle('open'); }
  }
  try { if (localStorage.getItem('mfasha-sidebar') === 'closed') app.classList.add('collapsed'); } catch (e) {}
  menuButtons.forEach(function (b) { b.addEventListener('click', toggleMenu); });
  new MutationObserver(syncMenu).observe(app, { attributes: true, attributeFilter: ['class'] });
  if (desktopQuery.addEventListener) desktopQuery.addEventListener('change', syncMenu);
  syncMenu();

  $('scrim').addEventListener('click', function () { app.classList.remove('open'); });
  $('clear-history').addEventListener('click', function () {
    if (!conversations.length) { setStatus('Nta biganiro bihari byo gusiba.'); return; }
    if (!window.confirm('Ibiganiro byose biraseswa kuri telefone yawe gusa. Kopi ziri kuri seriveri ya Mfasha ntizisibwa. Komeza?')) return;
    conversations = []; activeConversationId = null; saveConversations(); beginNewChat(); renderHistory();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && app.classList.contains('open')) { app.classList.remove('open'); $('toggle-history').focus(); }
  });

  var pv = $('privacy-dialog');
  if (PRIVACY_CONTACT) { $('privacy-contact').textContent = PRIVACY_CONTACT; $('privacy-contact-row').hidden = false; }
  document.querySelectorAll('[data-open-privacy]').forEach(function (a) {
    a.addEventListener('click', function (e) {
      e.preventDefault(); app.classList.remove('open');
      if (pv.showModal) pv.showModal(); else pv.setAttribute('open', '');
    });
  });
  $('privacy-close').addEventListener('click', function () {
    if (pv.close) pv.close(); else pv.removeAttribute('open');
  });

  document.title = 'Baza Mfasha – Umufasha wawe mu buhinzi n’ubworozi';
  questionBox.focus();

  loadConversations();
}());