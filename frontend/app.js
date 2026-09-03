/**
 * app.js — ContractGuard Frontend Logic
 * Flow:
 *  1. User submits address → POST /investigate → receive job_id
 *  2. Open EventSource on /stream/{job_id} → render steps live
 *  3. On "complete" event → GET /report/{job_id} → render report card
 */

const API_BASE = window.location.origin;

// ── DOM refs ──────────────────────────────────────────────────────────────────
const form          = document.getElementById('investigate-form');
const addressInput  = document.getElementById('contract-address');
const investigateBtn= document.getElementById('investigate-btn');
const btnText       = investigateBtn.querySelector('.btn-text');
const btnSpinner    = investigateBtn.querySelector('.btn-spinner');
const btnIcon       = investigateBtn.querySelector('.btn-icon');
const inputError    = document.getElementById('input-error');

const panel         = document.getElementById('investigation-panel');
const statusDot     = document.getElementById('status-dot');
const statusLabel   = document.getElementById('status-label');
const statusAddress = document.getElementById('status-address');
const suspicionFill = document.getElementById('suspicion-fill');
const suspicionValue= document.getElementById('suspicion-value');
const traceLog      = document.getElementById('trace-log');

const reportCard    = document.getElementById('report-card');
const newBtn        = document.getElementById('new-investigation-btn');

// Demo address buttons (populated after deployment)
const demoCleanBtn    = document.getElementById('demo-clean-btn');
const demoBdoorBtn    = document.getElementById('demo-backdoor-btn');

let currentEventSource = null;

// ── Step type config ──────────────────────────────────────────────────────────
const STEP_ICONS = {
  decision:         { icon: '◎', cls: 'step-icon-decision',    label: 'Decision' },
  tool_call:        { icon: '⚙', cls: 'step-icon-tool_call',   label: 'Tool Call' },
  agent_invocation: { icon: '🤖', cls: 'step-icon-agent',       label: 'Agent' },
  threshold_check:  { icon: '⚖', cls: 'step-icon-threshold',   label: 'Threshold' },
  termination:      { icon: '✓', cls: 'step-icon-termination',  label: 'Done' },
  error:            { icon: '✗', cls: 'step-icon-threshold',    label: 'Error' },
};

// ── Validation ────────────────────────────────────────────────────────────────
function validateAddress(addr) {
  if (!addr) return 'Please enter a contract address.';
  if (!addr.startsWith('0x')) return 'Address must start with 0x.';
  if (addr.length !== 42) return `Address must be 42 characters (got ${addr.length}).`;
  if (!/^0x[0-9a-fA-F]{40}$/.test(addr)) return 'Address contains invalid characters.';
  return null;
}

// ── UI state helpers ──────────────────────────────────────────────────────────
function setLoading(on) {
  investigateBtn.disabled = on;
  btnText.textContent = on ? 'Investigating...' : 'Investigate';
  btnSpinner.classList.toggle('hidden', !on);
  btnIcon.classList.toggle('hidden', on);
}

function showError(msg) {
  inputError.textContent = msg;
  inputError.classList.remove('hidden');
}

function clearError() {
  inputError.classList.add('hidden');
  inputError.textContent = '';
}

function updateSuspicion(score) {
  if (score == null) return;
  const pct = Math.min(100, Math.max(0, score));
  suspicionFill.style.width = `${pct}%`;
  suspicionValue.textContent = pct;

  // Color the score value
  if (pct >= 70) suspicionValue.style.color = 'var(--risk-high)';
  else if (pct >= 31) suspicionValue.style.color = 'var(--risk-medium)';
  else suspicionValue.style.color = 'var(--risk-low)';
}

// ── Trace step renderer ───────────────────────────────────────────────────────
function appendTraceStep(step) {
  // Remove typing indicator if present
  const typing = traceLog.querySelector('.typing-indicator');
  if (typing) typing.remove();

  const config = STEP_ICONS[step.step_type] || STEP_ICONS.decision;
  const text = step.output_summary || step.decision || step.action || '';

  const el = document.createElement('div');
  el.className = 'trace-step';
  el.innerHTML = `
    <div class="step-icon ${config.cls}">${config.icon}</div>
    <div class="step-body">
      <div class="step-action">${config.label} · ${step.action || ''}</div>
      <div class="step-content">${escapeHtml(text)}</div>
      <div class="step-meta">
        <span class="step-index">#${step.step_index ?? ''}</span>
        ${step.suspicion_after != null ? `<span class="step-score">Score: ${step.suspicion_after}/100</span>` : ''}
        ${step.suspicion_delta != null && step.suspicion_delta !== 0
          ? `<span class="step-score" style="color:${step.suspicion_delta > 0 ? 'var(--risk-high)' : 'var(--risk-low)'}">
              ${step.suspicion_delta > 0 ? '+' : ''}${step.suspicion_delta}
             </span>`
          : ''}
      </div>
    </div>
  `;
  traceLog.appendChild(el);

  // Keep scroll at bottom
  traceLog.scrollTop = traceLog.scrollHeight;

  // Update suspicion meter
  if (step.suspicion_after != null) {
    updateSuspicion(step.suspicion_after);
  }

  // Re-add typing indicator if not done
  if (step.step_type !== 'termination') {
    addTypingIndicator();
  }
}

function addTypingIndicator() {
  const existing = traceLog.querySelector('.typing-indicator');
  if (existing) return;
  const el = document.createElement('div');
  el.className = 'typing-indicator';
  el.innerHTML = `
    <div class="typing-dot"></div>
    <div class="typing-dot"></div>
    <div class="typing-dot"></div>
    <span>Agent working...</span>
  `;
  traceLog.appendChild(el);
  traceLog.scrollTop = traceLog.scrollHeight;
}

// ── Report card renderer ──────────────────────────────────────────────────────
function renderReport(report) {
  reportCard.classList.remove('hidden', 'verdict-HIGH', 'verdict-MEDIUM', 'verdict-LOW', 'verdict-INSUFFICIENT_DATA');
  reportCard.classList.add(`verdict-${report.verdict}`);

  // Verdict icon
  const icons = { HIGH: '🚨', MEDIUM: '⚠️', LOW: '✅', INSUFFICIENT_DATA: '❓' };
  document.getElementById('report-verdict-icon').textContent = icons[report.verdict] || '❓';
  document.getElementById('report-verdict-label').textContent = report.verdict_label;
  document.getElementById('report-score').textContent =
    `Risk Score: ${report.overall_suspicion_score}/100 · Confidence: ${report.confidence}`;

  document.getElementById('report-agents').textContent =
    `Agents: ${report.agents_invoked.join(', ')}`;
  document.getElementById('report-depth').textContent =
    `Investigation depth: ${report.investigation_depth}`;

  document.getElementById('report-reasoning').textContent = report.reasoning_trail;

  // Findings
  const findingsEl = document.getElementById('report-findings');
  findingsEl.innerHTML = '';
  if (report.key_findings && report.key_findings.length > 0) {
    report.key_findings.forEach(f => {
      const item = document.createElement('div');
      item.className = `finding-item sev-${f.severity}`;
      item.innerHTML = `
        <span class="finding-severity">${f.severity}</span>
        <div class="finding-content">
          <div class="finding-title">${escapeHtml(f.title)}</div>
          <div class="finding-agent">Detected by: ${f.agent.replace('_', ' ')} agent</div>
        </div>
      `;
      findingsEl.appendChild(item);
    });
  } else {
    findingsEl.innerHTML = '<p style="color:var(--text-muted);font-size:0.85rem;padding:8px 0">No critical findings detected.</p>';
  }

  // Flags
  const flagsEl = document.getElementById('report-flags');
  if (report.insufficient_data_flags && report.insufficient_data_flags.length > 0) {
    flagsEl.textContent = `⚠ Data unavailable from: ${report.insufficient_data_flags.join(', ')}`;
  } else {
    flagsEl.textContent = '✓ All data sources responded successfully';
  }

  reportCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ── Investigation flow ────────────────────────────────────────────────────────
async function startInvestigation(address) {
  clearError();
  const validationErr = validateAddress(address);
  if (validationErr) { showError(validationErr); return; }

  // Close any existing SSE connection
  if (currentEventSource) {
    currentEventSource.close();
    currentEventSource = null;
  }

  setLoading(true);

  // Show investigation panel
  panel.classList.remove('hidden');
  reportCard.classList.add('hidden');
  traceLog.innerHTML = '';

  // Set address display (truncated)
  statusAddress.textContent = `${address.slice(0,8)}...${address.slice(-6)}`;
  statusDot.className = 'status-dot';
  statusLabel.textContent = 'Connecting to agent...';
  updateSuspicion(0);

  // POST /investigate
  let jobId;
  try {
    const resp = await fetch(`${API_BASE}/investigate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address, chain: 'sepolia' }),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }

    const data = await resp.json();
    jobId = data.job_id;
  } catch (err) {
    setLoading(false);
    showError(`Failed to start investigation: ${err.message}`);
    panel.classList.add('hidden');
    return;
  }

  statusLabel.textContent = 'Investigation running...';
  addTypingIndicator();

  // Open SSE stream
  const es = new EventSource(`${API_BASE}/stream/${jobId}`);
  currentEventSource = es;

  es.onmessage = (event) => {
    let data;
    try { data = JSON.parse(event.data); } catch { return; }

    if (data.step_type === 'complete') {
      es.close();
      currentEventSource = null;
      // Remove typing indicator
      const typing = traceLog.querySelector('.typing-indicator');
      if (typing) typing.remove();

      statusLabel.textContent = 'Investigation complete — fetching report...';
      statusDot.className = 'status-dot done';
      setLoading(false);

      // Fetch final report
      fetchReport(jobId);
      return;
    }

    appendTraceStep(data);
  };

  es.onerror = (err) => {
    es.close();
    currentEventSource = null;
    setLoading(false);
    statusLabel.textContent = 'Stream error — retrying report fetch...';
    statusDot.className = 'status-dot failed';
    // Fallback: try to fetch the report anyway (may be complete)
    setTimeout(() => fetchReport(jobId), 2000);
  };
}

async function fetchReport(jobId) {
  // Poll up to 10 times (30s) for the report
  for (let i = 0; i < 10; i++) {
    try {
      const resp = await fetch(`${API_BASE}/report/${jobId}`);
      if (resp.status === 202) {
        // Still running
        await sleep(3000);
        continue;
      }
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const report = await resp.json();
      statusLabel.textContent = `Verdict: ${report.verdict_label}`;
      updateSuspicion(report.overall_suspicion_score);
      renderReport(report);
      return;
    } catch (err) {
      console.error('Report fetch error:', err);
      await sleep(3000);
    }
  }
  statusLabel.textContent = 'Report fetch timed out. Please check /docs for manual query.';
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function escapeHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Event Listeners ───────────────────────────────────────────────────────────
form.addEventListener('submit', (e) => {
  e.preventDefault();
  const address = addressInput.value.trim();
  startInvestigation(address);
});

newBtn.addEventListener('click', () => {
  panel.classList.add('hidden');
  reportCard.classList.add('hidden');
  addressInput.value = '';
  addressInput.focus();
  window.scrollTo({ top: 0, behavior: 'smooth' });
});

// Demo buttons — load addresses from demo_addresses.txt if present
async function loadDemoAddresses() {
  try {
    const resp = await fetch('/static/demo_addresses.txt');
    if (!resp.ok) return;
    const text = await resp.text();
    const lines = text.split('\n').map(l => l.trim()).filter(Boolean);
    // Expected format:
    // CLEAN=0x...
    // BACKDOORED=0x...
    lines.forEach(line => {
      if (line.startsWith('CLEAN=')) {
        const addr = line.split('=')[1];
        demoCleanBtn.dataset.address = addr;
        demoCleanBtn.title = addr;
      }
      if (line.startsWith('BACKDOORED=')) {
        const addr = line.split('=')[1];
        demoBdoorBtn.dataset.address = addr;
        demoBdoorBtn.title = addr;
      }
    });
  } catch { /* demo addresses file not present yet */ }
}

demoCleanBtn.addEventListener('click', () => {
  const addr = demoCleanBtn.dataset.address;
  if (addr) {
    addressInput.value = addr;
    startInvestigation(addr);
  } else {
    showError('Demo address not configured yet. Edit demo_addresses.txt after deploying contracts to Sepolia.');
  }
});

demoBdoorBtn.addEventListener('click', () => {
  const addr = demoBdoorBtn.dataset.address;
  if (addr) {
    addressInput.value = addr;
    startInvestigation(addr);
  } else {
    showError('Demo address not configured yet. Edit demo_addresses.txt after deploying contracts to Sepolia.');
  }
});

// Init
loadDemoAddresses();
addressInput.focus();
