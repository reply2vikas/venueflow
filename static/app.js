'use strict';

// ── Constants & State ─────────────────────────────────────────────────────────
const API = '';
const CACHE_TTL_MS = 25000; // 25 seconds - zones refresh every 30s on server

// Local cache - stops repeated network calls when switching tabs
const _cache = {
  zones:    { data: null, ts: 0 },
  alerts:   { data: null, ts: 0 },
  waittimes:{ data: null, ts: 0 },
};

// Track shown emergency IDs so alarm only plays ONCE per emergency
const _shownEmergencies = new Set();

let ws = null;
const SESSION_ID = (() => {
  let id = localStorage.getItem('vf_session');
  if (!id) { id = crypto.randomUUID(); localStorage.setItem('vf_session', id); }
  return id;
})();

// ── Cached Fetch ──────────────────────────────────────────────────────────────
// Like a smart assistant who remembers the answer for 25 seconds
// so we don't call Cloud Run on every tab click
async function cachedFetch(url, cacheKey) {
  const entry = _cache[cacheKey];
  const now = Date.now();
  if (entry && entry.data && (now - entry.ts) < CACHE_TTL_MS) {
    return entry.data;  // Return saved answer
  }
  try {
    const res = await fetch(API + url);
    if (!res.ok) return entry.data || [];
    const data = await res.json();
    _cache[cacheKey] = { data, ts: now };
    return data;
  } catch (_) {
    return entry.data || [];  // Return old data if network fails
  }
}

// ── Tab Navigation ────────────────────────────────────────────────────────────
const tabPanels = {
  'tab-zones':    { panel: 'panel-zones',    loader: loadZones },
  'tab-navigate': { panel: 'panel-navigate', loader: null },
  'tab-alerts':   { panel: 'panel-alerts',   loader: loadAlerts },
  'tab-ai':       { panel: 'panel-ai',       loader: null },
};

function switchTab(tabId) {
  // Hide all panels, deactivate all tabs
  Object.values(tabPanels).forEach(({ panel }) => {
    const el = document.getElementById(panel);
    if (el) el.hidden = true;
  });
  document.querySelectorAll('[role="tab"]').forEach(t => {
    t.classList.remove('active');
    t.setAttribute('aria-selected', 'false');
  });

  // Show selected
  const entry = tabPanels[tabId];
  if (!entry) return;
  const tab = document.getElementById(tabId);
  if (tab) { tab.classList.add('active'); tab.setAttribute('aria-selected', 'true'); }
  const panel = document.getElementById(entry.panel);
  if (panel) panel.hidden = false;

  // Load data only if needed (cached fetch handles repeated calls)
  if (entry.loader) entry.loader();
}

document.querySelectorAll('[role="tab"]').forEach(tab => {
  tab.addEventListener('click', () => switchTab(tab.id));
});

// ── Zone Map ──────────────────────────────────────────────────────────────────
const DENSITY_LABELS = ['', 'Clear', 'Light', 'Moderate', 'Busy', 'Packed'];
const DENSITY_COLORS = ['', '#22c55e', '#84cc16', '#eab308', '#f97316', '#ef4444'];

async function loadZones() {
  const zones = await cachedFetch('/api/zones', 'zones');
  if (!zones || !zones.length) return;

  const list = document.getElementById('zoneList');
  if (!list) return;

  list.innerHTML = zones.map(z => `
    <div class="zone-item" role="listitem">
      <div class="density-dot"
           style="background:${DENSITY_COLORS[z.density_level] || '#888'}"
           aria-hidden="true"></div>
      <div class="zone-info">
        <strong>${z.zone_id.replace(/_/g, ' ')}</strong>
        <span class="zone-level">${DENSITY_LABELS[z.density_level] || ''}</span>
        ${z.wait_time_minutes != null
          ? `<span class="zone-wait">~${z.wait_time_minutes} min wait</span>`
          : ''}
      </div>
    </div>`).join('');

  const ts = document.getElementById('zonesLastUpdated');
  if (ts) ts.textContent = 'Updated just now · refreshes every 30s';
}

// ── Route Finder ──────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const routeBtn = document.getElementById('routeBtn');
  if (routeBtn) routeBtn.addEventListener('click', findRoute);
  const aiBtn = document.getElementById('aiBtn');
  if (aiBtn) aiBtn.addEventListener('click', () => {
    const q = document.getElementById('aiQuestion').value.trim();
    if (q.length >= 3) askAI(q);
    else showAIResult('Please type a question first.');
  });
  const aiQ = document.getElementById('aiQuestion');
  if (aiQ) aiQ.addEventListener('keydown', e => {
    if (e.key === 'Enter') document.getElementById('aiBtn').click();
  });
  const wct = document.getElementById('wheelchairToggle');
  if (wct) wct.addEventListener('change', function() {
    this.setAttribute('aria-checked', this.checked ? 'true' : 'false');
  });
  const accessBtn = document.getElementById('accessBtn');
  if (accessBtn) accessBtn.addEventListener('click', function() {
    const big = document.body.classList.toggle('large-text');
    this.setAttribute('aria-pressed', big.toString());
    this.textContent = big ? 'Normal Text' : 'Large Text';
  });
});

async function findRoute() {
  const origin      = (document.getElementById('fromInput').value || '').trim();
  const destination = (document.getElementById('toInput').value || '').trim();
  const wheelchair  = document.getElementById('wheelchairToggle').checked;
  const result      = document.getElementById('routeResult');
  if (!result) return;

  if (!origin || !destination) {
    result.innerHTML = '<div class="alert-item">Please enter both starting point and destination.</div>';
    return;
  }
  result.innerHTML = '<div class="alert-item">Finding best route…</div>';

  try {
    const res = await fetch(`${API}/api/route`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Session-ID': SESSION_ID },
      body: JSON.stringify({ origin, destination, wheelchair }),
    });
    if (!res.ok) {
      const e = await res.json().catch(() => ({ detail: 'Error' }));
      result.innerHTML = `<div class="alert-item alert-emergency">${e.detail}</div>`;
      return;
    }
    const route = await res.json();
    result.innerHTML = `
      <div class="route-result-card">
        <div class="route-path">${route.path.map(p => p.replace(/_/g, ' ')).join(' → ')}</div>
        <div class="route-chips">
          <span class="chip">~${route.distance_meters}m</span>
          <span class="chip">~${route.estimated_minutes} min</span>
          <span class="chip">Crowd ${route.crowd_level}/5</span>
          ${route.accessible ? '<span class="chip chip-green">♿ Step-free</span>' : ''}
        </div>
        ${route.notes ? `<p class="route-note">${route.notes}</p>` : ''}
      </div>`;
  } catch (_) {
    result.innerHTML = '<div class="alert-item alert-emergency">Routing unavailable. Please try again.</div>';
  }
}

function setDest(val) {
  const inp = document.getElementById('toInput');
  if (inp) { inp.value = val; inp.style.color = '#e2e8f0'; }
}

// ── Alerts ────────────────────────────────────────────────────────────────────
async function loadAlerts() {
  const alerts = await cachedFetch('/api/alerts', 'alerts');
  if (!alerts) return;
  const list = document.getElementById('alertList');
  if (!list) return;

  // Only process NEW alerts - don't re-render if same data
  alerts.forEach(a => showAlert(a, false)); // false = don't prepend, just render
  if (!alerts.length) {
    list.innerHTML = '<div class="alert-item">All clear — no active alerts right now.</div>';
  }
}

let _lastAlertIds = new Set();

function showAlert(msg, prepend = true) {
  if (!msg || !msg.message) return;

  // Build stable ID for deduplication
  const alertId = msg.alert_id || (msg.type + '_' + msg.zone_id + '_' + msg.message.slice(0, 20));

  // Emergency: only show banner + play sound ONCE per unique emergency
  if (msg.type === 'emergency' && !_shownEmergencies.has(alertId)) {
    _shownEmergencies.add(alertId);
    showEmergencyBanner(msg.message);
    // Sound + vibrate only on genuinely new emergency
    playEmergencyAlarm();
    if (navigator.vibrate) navigator.vibrate([600, 150, 600, 150, 600]);
  }

  // Add to alert list only if not already shown
  if (_lastAlertIds.has(alertId)) return;
  _lastAlertIds.add(alertId);

  const list = document.getElementById('alertList');
  if (!list) return;
  const div = document.createElement('div');
  div.className = `alert-item ${msg.type === 'emergency' ? 'alert-emergency' : ''}`;
  div.setAttribute('role', 'alert');
  div.innerHTML = `
    <span class="alert-type-badge">${(msg.type || 'info').toUpperCase()}</span>
    <span>${msg.message}</span>
    <div style="font-size:10px;color:#475569;margin-top:3px">${new Date().toLocaleTimeString()}</div>`;
  if (prepend) list.prepend(div);
  else list.appendChild(div);
  if (list.children.length > 8) list.lastChild.remove();
}

// ── Emergency Banner ──────────────────────────────────────────────────────────
function showEmergencyBanner(message) {
  const existing = document.getElementById('emergencyBanner');
  if (existing) existing.remove();

  const banner = document.createElement('div');
  banner.id = 'emergencyBanner';
  banner.setAttribute('role', 'alert');
  banner.setAttribute('aria-live', 'assertive');
  banner.style.cssText = [
    'position:sticky', 'top:0', 'z-index:9999',
    'background:#dc2626', 'color:white',
    'padding:14px 16px', 'text-align:center',
    'font-size:15px', 'font-weight:bold',
    'line-height:1.5', 'border-bottom:3px solid #7f1d1d', 'cursor:pointer',
  ].join(';');
  banner.innerHTML = '&#9888;&#65039; ' + message +
    '<span style="font-size:11px;display:block;margin-top:4px;font-weight:normal">' +
    'Tap to dismiss — Follow steward directions</span>';
  banner.addEventListener('click', () => banner.remove());
  document.body.insertBefore(banner, document.body.firstChild);

  // Speak aloud for accessibility
  if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(message);
    utter.rate = 0.85; utter.lang = 'en-IN';
    window.speechSynthesis.speak(utter);
  }
}

// Emergency alarm — only plays when genuinely triggered
let _audioCtx = null;
function getAudioCtx() {
  if (!_audioCtx) {
    _audioCtx = typeof AudioContext !== 'undefined'
      ? new AudioContext()
      : typeof webkitAudioContext !== 'undefined'
        ? new webkitAudioContext()
        : null;
  }
  return _audioCtx;
}

function playEmergencyAlarm() {
  const ctx = getAudioCtx();
  if (!ctx) return;
  try {
    [880, 660, 880, 660].forEach((freq, i) => {
      const osc  = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.frequency.value = freq;
      osc.type = 'square';
      gain.gain.setValueAtTime(0.25, ctx.currentTime + i * 0.25);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + i * 0.25 + 0.2);
      osc.start(ctx.currentTime + i * 0.25);
      osc.stop(ctx.currentTime + i * 0.25 + 0.25);
    });
  } catch (_) {}
}

// ── AI Assistant ───────────────────────────────────────────────────────────────
async function askAI(question) {
  const wheelchair = document.getElementById('wheelchairToggle')?.checked || false;
  showAIResult('<div class="ai-thinking">Asking Gemini AI…</div>');

  try {
    const res = await fetch(`${API}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Session-ID': SESSION_ID },
      body: JSON.stringify({ question: question.slice(0, 200), wheelchair, language: 'en' }),
    });
    if (!res.ok) {
      showAIResult('<div class="alert-item">AI unavailable. Check the Zones tab for live crowd info.</div>');
      return;
    }
    const data = await res.json();
    const badge = data.source === 'gemini'
      ? '<span class="chip chip-blue">Gemini AI</span>'
      : '<span class="chip">Smart answer</span>';
    showAIResult(`
      <div class="ai-answer-card">
        <div class="ai-answer-chips">${badge}</div>
        <p class="ai-answer-text">${data.answer}</p>
      </div>`);
  } catch (_) {
    showAIResult('<div class="alert-item">AI offline. Try the Zones tab for crowd data.</div>');
  }
}

function showAIResult(html) {
  const el = document.getElementById('aiResult');
  if (el) el.innerHTML = html;
}

window.askQuick = (q) => {
  const inp = document.getElementById('aiQuestion');
  if (inp) inp.value = q;
  askAI(q);
};

// ── WebSocket ─────────────────────────────────────────────────────────────────
function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  try {
    ws = new WebSocket(`${proto}://${location.host}/ws/live`);
    ws.onmessage = e => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type !== 'ping') showAlert(msg);
      } catch (_) {}
    };
    ws.onerror  = () => {};
    ws.onclose  = () => setTimeout(connectWS, 8000);
  } catch (_) { setTimeout(connectWS, 8000); }
}

// ── Initialise ────────────────────────────────────────────────────────────────
loadZones();
setInterval(loadZones, 30000);   // Refresh zones every 30s
setInterval(() => {              // Poll alerts every 25s (uses cache intelligently)
  _cache.alerts.ts = 0;         // Force fresh fetch for alerts
  loadAlerts();
}, 25000);
connectWS();
