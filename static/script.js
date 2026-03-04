const btn = document.getElementById('mic-btn');
const wrap = document.getElementById('mic-wrap');
const status = document.getElementById('call-status');
const waveform = document.getElementById('waveform');
const liveText = document.getElementById('live-transcript');
const convoLog = document.getElementById('convo-log');
const sysStatus = document.getElementById('sys-status');

let recorder, chunks = [], stream, recording = false;
let sessionId = null;
let currentAudio = null;
let sessionStart = null;
let turnCount = 0;

// ── START SESSION ON PAGE LOAD ────────────────
window.addEventListener('load', async () => {
    try {
        const res = await fetch('/session/start', { method: 'POST' });
        const data = await res.json();
        sessionId = data.session_id;
        sessionStart = new Date();
        sysStatus.textContent = 'Session Started';
        if (data.audio_b64) playAudio(data.audio_b64);
    } catch (e) {
        console.error('Session start failed:', e);
        sysStatus.textContent = 'Server Offline';
    }
});

// ── MIC BUTTON ────────────────────────────────
btn.addEventListener('click', async () => {
    if (currentAudio) { currentAudio.pause(); currentAudio = null; }
    recording ? stopRecording() : await startRecording();
});

async function startRecording() {
    try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
        setStatus(`${err.name}: ${err.message}`, 'error');
        return;
    }
    chunks = [];
    recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
    recorder.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
    recorder.onstop = sendAudio;
    recorder.start();
    recording = true;
    btn.classList.add('recording');
    wrap.classList.add('recording');
    waveform.classList.add('active');
    setStatus('Recording… tap to stop', 'active');
    sysStatus.textContent = 'Recording';
}

function stopRecording() {
    recorder?.stop();
    stream?.getTracks().forEach(t => t.stop());
    recording = false;
    btn.classList.remove('recording');
    wrap.classList.remove('recording');
    waveform.classList.remove('active');
    setStatus('Processing…', 'waiting');
    sysStatus.textContent = 'Processing';
}

// ── SEND AUDIO ────────────────────────────────
async function sendAudio() {
    const blob = new Blob(chunks, { type: 'audio/webm' });
    try {
        const res = await fetch('/send', {
            method: 'POST',
            headers: {
                'Content-Type': 'audio/webm',
                'x-session-id': sessionId || ''
            },
            body: blob,
        });

        const data = await res.json();

        // Update session ID if server issued new one
        if (data.session_id) sessionId = data.session_id;

        const transcript = data.transcript || '';
        const botReply = data.response || '';

        updateLiveTranscript(transcript);
        if (transcript) addTurn('user', transcript);
        if (botReply) addTurn('bot', botReply);

        // Play audio
        if (data.audio_b64) playAudio(data.audio_b64);

        setStatus('Received ✓', 'ok');
        sysStatus.textContent = 'Active';
        setTimeout(() => setStatus('Tap to speak', ''), 3500);

        // Render summary — prefer server summary, fallback to local
        if (data.summary) renderSummary(data.summary);
        else updateSummaryFromConvo();

    } catch (e) {
        console.error(e);
        setStatus('Error — check server', 'error');
        sysStatus.textContent = 'Error';
    }
}

// ── PLAY AUDIO ────────────────────────────────
function playAudio(b64) {
    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const blob = new Blob([bytes], { type: 'audio/mpeg' });
    const url = URL.createObjectURL(blob);
    currentAudio = new Audio(url);
    currentAudio.play();
    currentAudio.onended = () => URL.revokeObjectURL(url);
}

// ── CONVERSATION LOG ──────────────────────────
function addTurn(role, text) {
    turnCount++;
    const div = document.createElement('div');
    div.className = `turn ${role}`;
    div.innerHTML = `
<div class="turn-label">${role === 'user' ? 'You' : 'Deep Care AI'}</div>
<div class="turn-text">${escHtml(text)}</div>
`;
    convoLog.appendChild(div);
    convoLog.scrollTop = convoLog.scrollHeight;
}

function updateLiveTranscript(text) {
    liveText.textContent = text || '—';
}

// ── SUMMARY ───────────────────────────────────
function renderSummary(data) {
    document.getElementById('summary-empty').style.display = 'none';
    const card = document.getElementById('summary-card');
    card.classList.add('visible');

    document.getElementById('s-name').textContent = data.name || '—';
    document.getElementById('s-dob').textContent = data.dob || data.customer_id || '—';
    document.getElementById('s-duration').textContent = data.duration || formatDuration(new Date() - sessionStart);
    document.getElementById('s-time').textContent = data.time || new Date().toLocaleTimeString();
    document.getElementById('s-summary').textContent = data.summary || '—';
    document.getElementById('s-action').textContent = data.suggested_action || data.action || '—';
    document.getElementById('s-footer').textContent = `Session · ${data.duration || '—'} · ${turnCount} turns`;

    const badge = document.getElementById('s-sentiment');
    const sent = data.sentiment || 'neutral';
    badge.textContent = sent.charAt(0).toUpperCase() + sent.slice(1);
    badge.className = `sentiment-badge ${sent}`;

    const intentRow = document.getElementById('s-intents');
    intentRow.innerHTML = '';
    (data.intents || data.intents_seen || []).forEach(i => {
        const tag = document.createElement('span');
        tag.className = 'intent-tag';
        tag.textContent = i;
        intentRow.appendChild(tag);
    });

    const kpList = document.getElementById('s-keypoints');
    kpList.innerHTML = '';
    (data.key_points || data.keyPoints || []).forEach(p => {
        const li = document.createElement('li');
        li.textContent = p;
        kpList.appendChild(li);
    });
}

function updateSummaryFromConvo() {
    const userTexts = [...convoLog.querySelectorAll('.turn.user .turn-text')].map(el => el.textContent);
    if (!userTexts.length) return;
    const combined = userTexts.join(' ').toLowerCase();
    const neg = ['frustrated', 'wrong', 'problem', 'complaint', 'issue'].filter(w => combined.includes(w)).length;
    const pos = ['thank', 'great', 'happy', 'resolved'].filter(w => combined.includes(w)).length;
    renderSummary({
        name: document.getElementById('s-name').textContent || 'Customer',
        sentiment: neg > 1 ? 'negative' : pos > 0 ? 'positive' : 'neutral',
        duration: formatDuration(new Date() - sessionStart),
        intents: [],
        key_points: [...convoLog.querySelectorAll('.turn.bot .turn-text')].slice(-3).map(el => el.textContent.slice(0, 80)),
        summary: `${turnCount} turns completed.`,
        suggested_action: neg > 1 ? 'Follow up within 24 hours.' : 'No immediate action needed.'
    });
}

// ── HELPERS ───────────────────────────────────
function setStatus(msg, cls = '') {
    status.textContent = msg;
    status.className = cls;
}
function escHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function formatDuration(ms) {
    const s = Math.floor(ms / 1000);
    return `${Math.floor(s / 60)}m ${s % 60}s`;
}
