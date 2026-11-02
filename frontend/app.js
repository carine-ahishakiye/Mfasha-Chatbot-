// Browser client. Talks to the FastAPI backend with fetch(); no framework needed.
const $ = (id) => document.getElementById(id);
const API = "/api";
let lastAnswerId = null, recorder = null, chunks = [];

function setStatus(text) { $("status").textContent = text; }

function show(data) {
  $("result").classList.remove("hidden");
  $("heard").textContent = data.heard ? `Numvise: "${data.heard}"` : "";
  $("badge").textContent = data.status === "answered" ? "Igisubizo" : "Kohereza ku mu agoronome";
  $("badge").className = data.status;
  $("answer").textContent = data.answer;       // textContent, never innerHTML: no script injection
  $("meta").textContent = `Igihe: ${Math.round(data.latency_ms)} ms` + (data.review_status ? ` · ${data.review_status}` : "");
  const player = $("player");
  if (data.audio_base64) {
    player.src = "data:audio/wav;base64," + data.audio_base64;
    player.classList.remove("hidden");
    player.play().catch(() => {});             // autoplay may be blocked; the controls remain
  } else { player.classList.add("hidden"); player.removeAttribute("src"); }
  lastAnswerId = data.answer_id;
  $("feedback").classList.remove("hidden");
}

async function call(path, options) {
  const res = await fetch(API + path, options);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = Array.isArray(body.detail) ? body.detail.map((d) => d.msg).join("; ") : body.detail;
    throw new Error(detail || `Ikibazo (${res.status})`);
  }
  return body;
}

async function sendText() {
  const question = $("question").value.trim();
  if (!question) { setStatus("Andika ikibazo mbere."); return; }
  setStatus("Birimo gushakisha…"); $("send").disabled = true;
  try {
    show(await call("/ask/text", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, with_audio: $("withAudio").checked }) }));
    setStatus("");
  } catch (e) { setStatus("Ntibyakunze: " + e.message); } finally { $("send").disabled = false; }
}

// voice: record, convert to 16 kHz mono WAV in the browser, upload 
async function toWav(blob) {
  const ctx = new AudioContext();
  const decoded = await ctx.decodeAudioData(await blob.arrayBuffer());
  await ctx.close();
  const length = Math.ceil(decoded.duration * 16000);
  const offline = new OfflineAudioContext(1, length, 16000);   // resamples and mixes down to mono
  const source = offline.createBufferSource();
  source.buffer = decoded; source.connect(offline.destination); source.start();
  return encodeWav((await offline.startRendering()).getChannelData(0), 16000);
}

function encodeWav(samples, rate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2), view = new DataView(buffer);
  const text = (o, s) => [...s].forEach((c, i) => view.setUint8(o + i, c.charCodeAt(0)));
  text(0, "RIFF"); view.setUint32(4, 36 + samples.length * 2, true); text(8, "WAVEfmt ");
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, rate, true); view.setUint32(28, rate * 2, true); view.setUint16(32, 2, true);
  view.setUint16(34, 16, true); text(36, "data"); view.setUint32(40, samples.length * 2, true);
  samples.forEach((s, i) => view.setInt16(44 + i * 2, Math.max(-1, Math.min(1, s)) * 0x7fff, true));
  return new Blob([buffer], { type: "audio/wav" });
}

async function toggleRecording() {
  const button = $("record");
  if (recorder && recorder.state === "recording") { recorder.stop(); return; }
  if (!navigator.mediaDevices || !window.MediaRecorder) { setStatus("Telefoni yawe ntishyigikira gufata ijwi."); return; }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    recorder = new MediaRecorder(stream); chunks = [];
    recorder.ondataavailable = (e) => chunks.push(e.data);
    recorder.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      button.classList.remove("recording"); button.textContent = "🎤 Fata ijwi";
      setStatus("Birimo gutegura ijwi…");
      try {
        const form = new FormData();
        form.append("audio", await toWav(new Blob(chunks)), "question.wav");
        form.append("with_audio", $("withAudio").checked);
        show(await call("/ask/voice", { method: "POST", body: form })); setStatus("");
      } catch (e) { setStatus("Ntibyakunze: " + e.message); }
    };
    recorder.start(); button.classList.add("recording"); button.textContent = "⏹ Hagarika";
    setStatus("Vuga ikibazo cyawe…");
  } catch { setStatus("Nta burenganzira bwo gukoresha mikoro."); }
}

async function sendFeedback(event) {
  const button = event.target.closest("button[data-rating]");
  if (!button || lastAnswerId === null) return;
  try {
    await call("/feedback", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answer_id: lastAnswerId, rating: +button.dataset.rating,
                             is_useful: button.dataset.useful === "true" }) });
    $("feedback").classList.add("hidden"); setStatus("Murakoze ku bitekerezo byanyu.");
  } catch (e) { setStatus("Ntibyakunze: " + e.message); }
}

$("send").addEventListener("click", sendText);
$("record").addEventListener("click", toggleRecording);
$("feedback").addEventListener("click", sendFeedback);
