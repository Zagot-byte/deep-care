'use strict';
// ── DOM refs ────────────────────────────────────────────────
const micBtn     = document.getElementById('mic-btn');
const micIcon    = document.getElementById('mic-icon');
const micStatus  = document.getElementById('mic-status');
const endBtn     = document.getElementById('end-btn');
const sysDot     = document.getElementById('sys-dot');
const sysLabel   = document.getElementById('sys-label');
const elapsed    = document.getElementById('elapsed');
const turnsDisp  = document.getElementById('turns-disp');
const langDisp   = document.getElementById('lang-disp');
const liveDot    = document.getElementById('live-dot');
const liveTx     = document.getElementById('live-tx');
const convoLog   = document.getElementById('convo-log');
const convoCount = document.getElementById('convo-count');
const sumBadge   = document.getElementById('sum-badge');
const sumLocked  = document.getElementById('sum-locked');
const sumPartial = document.getElementById('sum-partial');
const sumFull    = document.getElementById('sum-full');

// ── State ───────────────────────────────────────────────────
let sessionId    = null;
let sessionReady = false;
let callEnded    = false;
let recording    = false;
let recorder, chunks = [], stream;
let currentAudio = null;
let sessionStart = null;
let turnCount    = 0;
let elapsedTimer = null;
let micLocked = false;
let convoEmpty   = document.getElementById('convo-empty');

// ── Mic lock: true while processing or audio is playing ─────

function lockMic(status) {
  micLocked = true;
  micBtn.disabled = true;
  micStatus.textContent = status || 'PROCESSING…';
}

function unlockMic() {
  micLocked = false;
  if (!callEnded) {
    micBtn.disabled = false;
    micStatus.textContent = 'TAP TO SPEAK';
    setSys('ok', langDisp.textContent && langDisp.textContent !== 'EN'
      ? 'ACTIVE · ' + langDisp.textContent : 'ACTIVE');
  }
}

// ── Session start ───────────────────────────────────────────
window.addEventListener('load', async () => {
  setSys('wait', 'CONNECTING');
  try {
    const res  = await fetch('/session/start', { method: 'POST' });
    const data = await res.json();
    sessionId    = data.session_id;
    sessionStart = Date.now();
    sessionReady = true;
    startTimer();
    if (!data.stt_ready) {
      setSys('wait', 'STT LOADING');
      await waitSTT();
    }
    setSys('ok', 'READY');
    micBtn.disabled = false;
    endBtn.disabled = false;
    if (data.audio_b64) playAudio(data.audio_b64);
  } catch (e) {
    setSys('error', 'OFFLINE');
    liveTx.textContent = 'Cannot reach server — is uvicorn running?';
  }
});

async function waitSTT() {
  for (let i = 0; i < 60; i++) {
    await sleep(2000);
    try {
      const d = await (await fetch('/health')).json();
      if (d.stt === 'ready') return;
      setSys('wait', `STT ${i * 2}s`);
    } catch {}
  }
}

// ── Timer ───────────────────────────────────────────────────
function startTimer() {
  elapsedTimer = setInterval(() => {
    const s = Math.floor((Date.now() - sessionStart) / 1000);
    elapsed.textContent = pad(Math.floor(s / 60)) + ':' + pad(s % 60);
  }, 1000);
}

// ── Mic ─────────────────────────────────────────────────────
micBtn.addEventListener('click', async () => {
  if (!sessionReady || callEnded || micLocked) return;
  if (currentAudio) { currentAudio.pause(); currentAudio = null; }
  recording ? stopRec() : await startRec();
});

async function startRec() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    setSys('error', 'MIC DENIED');
    liveTx.textContent = e.message;
    return;
  }
  chunks   = [];
  recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
  recorder.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
  recorder.onstop = sendAudio;
  recorder.start();
  recording = true;
  micBtn.classList.add('recording');
  micStatus.textContent = 'TAP TO STOP';
  liveDot.classList.add('on');
  liveTx.textContent = '…';
  liveTx.classList.add('on');
  setSys('active', 'RECORDING');
  setMicIcon('stop');
}

function stopRec() {
  recorder?.stop();
  stream?.getTracks().forEach(t => t.stop());
  recording = false;
  micBtn.classList.remove('recording');
  setMicIcon('mic');
  liveDot.classList.remove('on');
  liveTx.classList.remove('on');
  // Lock mic immediately — unlocks only after audio finishes
  lockMic('PROCESSING…');
  setSys('wait', 'PROCESSING');
}

// ── Send audio ──────────────────────────────────────────────
async function sendAudio() {
  if (callEnded) return;
  const blob = new Blob(chunks, { type: 'audio/webm' });
  try {
    const res  = await fetch('/send', {
      method:  'POST',
      headers: { 'Content-Type': 'audio/webm', 'x-session-id': sessionId || '' },
      body:    blob,
    });
    const data = await res.json();
    if (data.session_id) sessionId = data.session_id;

    // Live transcript
    if (data.transcript) {
      liveTx.textContent = data.transcript;
      liveTx.classList.add('on');
      setTimeout(() => liveTx.classList.remove('on'), 3000);
    }

    // Language
    if (data.language) langDisp.textContent = data.language.toUpperCase();

    // Conversation turns
    if (data.transcript) addTurn('user', data.transcript);
    if (data.response)   addTurn('bot',  data.response);

    // Partial summary after auth
    if (data.summary) renderPartial(data.summary);

    // Auto end on goodbye intent
    if (data.intent === 'goodbye' || data.ended) setTimeout(endCall, 2000);

    // Play audio — mic unlocks only after playback finishes
    if (data.audio_b64) {
      lockMic('SPEAKING…');
      playAudio(data.audio_b64, unlockMic);
    } else {
      unlockMic();
    }

  } catch (e) {
    console.error(e);
    setSys('error', 'ERROR');
    unlockMic();   // always unblock on error
  }
}

// ── End call ────────────────────────────────────────────────
endBtn.addEventListener('click', endCall);
async function endCall() {
  if (callEnded) return;
  callEnded = true;
  if (recording) stopRec();
  if (currentAudio) { currentAudio.pause(); currentAudio = null; }
  clearInterval(elapsedTimer);
  micBtn.disabled = true;
  endBtn.disabled = true;
  setSys('error', 'ENDING');
  micStatus.textContent = 'CALL ENDED';
  addTurn('sys', '— Call ended · Generating handoff card —');
  try {
    const res  = await fetch('/session/end', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ session_id: sessionId }),
    });
    const data = await res.json();
    if (data.audio_b64) playAudio(data.audio_b64);
    if (data.summary)   renderFull(data.summary);
    setSys('ok', 'COMPLETE');
  } catch (e) {
    console.error(e);
    setSys('error', 'END FAILED');
  }
}

// ── Audio ───────────────────────────────────────────────────
function playAudio(b64, onFinished) {
  const bin   = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  const url = URL.createObjectURL(new Blob([bytes], { type: 'audio/mpeg' }));
  if (currentAudio) { currentAudio.pause(); currentAudio = null; }
  currentAudio = new Audio(url);
  currentAudio.play().catch(e => {
    console.warn(e);
    if (onFinished) onFinished();   // unblock even if autoplay fails
  });
  currentAudio.onended = () => {
    URL.revokeObjectURL(url);
    currentAudio = null;
    if (onFinished) onFinished();
  };
}

// ── Conversation ────────────────────────────────────────────
function addTurn(role, text) {
  turnCount++;
  turnsDisp.textContent  = turnCount;
  convoCount.textContent = turnCount + ' turns';
  if (convoEmpty) { convoEmpty.remove(); convoEmpty = null; }
  const ts  = new Date().toLocaleTimeString('en-IN', { hour:'2-digit', minute:'2-digit', second:'2-digit' });
  const tag = role === 'user' ? 'CALLER' : role === 'bot' ? 'DEEP CARE AI' : 'SYSTEM';
  const div = document.createElement('div');
  div.className = 'turn ' + role;
  div.innerHTML = `
    <div class="turn-meta">
      <span class="turn-tag">${tag}</span>
      <span class="turn-ts">${ts}</span>
    </div>
    <div class="turn-text">${esc(text)}</div>`;
  convoLog.appendChild(div);
  convoLog.scrollTop = convoLog.scrollHeight;
}

// ── Summary partial (after auth) ────────────────────────────
function renderPartial(data) {
  sumLocked.classList.add('hidden');
  sumPartial.classList.remove('hidden');
  sumBadge.textContent = 'LIVE';
  sumBadge.className   = 'badge partial';
  setText('s-name', data.name);
  setText('s-cid',  data.customer_id);
  setText('s-dob',  data.dob);
  setText('s-lang', (data.language || 'en').toUpperCase());
  const iw = document.getElementById('s-intents');
  iw.innerHTML = '';
  (data.intents || []).forEach(i => {
    const c = document.createElement('span');
    c.className = 'chip'; c.textContent = i.toUpperCase();
    iw.appendChild(c);
  });
  const sent = data.sentiment || 'neutral';
  document.getElementById('s-sentiment').innerHTML =
    `<span class="sent ${sent}">${sent.toUpperCase()}</span>`;
}

// ── Summary full (after end call) ───────────────────────────
function renderFull(data) {
  renderPartial(data);
  sumFull.classList.remove('hidden');
  sumBadge.textContent = 'READY';
  sumBadge.className   = 'badge ready';
  setText('s-duration', data.duration);
  setText('s-turns',    data.turns || turnCount);
  setText('s-time',     data.time  || new Date().toLocaleTimeString());
  setText('s-esc',      data.escalated ? 'YES' : 'NO');
  setText('s-summary',  data.summary);
  setText('s-action',   data.suggested_action);
  const kl = document.getElementById('s-keypoints');
  kl.innerHTML = '';
  (data.key_points || []).forEach(p => {
    const li = document.createElement('li');
    li.textContent = p; kl.appendChild(li);
  });
}

// ── Helpers ─────────────────────────────────────────────────
function setSys(state, label) {
  sysDot.className    = 'sys-dot '   + state;
  sysLabel.className  = 'sys-label ' + state;
  sysLabel.textContent = label;
}
function setMicIcon(mode) {
  micIcon.innerHTML = mode === 'stop'
    ? '<rect x="6" y="6" width="12" height="12" rx="2"/>'
    : `<path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
       <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
       <line x1="12" y1="19" x2="12" y2="23"/>
       <line x1="8" y1="23" x2="16" y2="23"/>`;
}
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val || '—';
}
function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function pad(n) { return String(n).padStart(2, '0'); }
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
