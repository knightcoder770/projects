// ── UTILS ─────────────────────────────────────────────────────────────────────

let currentPage = 'dashboard';

function nav(page) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
  document.getElementById('page-' + page).classList.add('active');
  document.querySelector(`[data-page="${page}"]`).classList.add('active');
  currentPage = page;
  renderPage(page);
}

function renderPage(page) {
  const map = {
    dashboard: renderDashboard,
    log:       renderLog,
    projects:  renderProjects,
    goals:     renderGoals,
    skills:    renderSkills,
    github:    renderGithub,
    report:    renderReport,
  };
  if (map[page]) map[page]();
}

// ── MODAL ─────────────────────────────────────────────────────────────────────
function openModal(html) {
  document.getElementById('modal-body').innerHTML = html;
  document.getElementById('modal-bg').classList.add('open');
}
function closeModal() {
  document.getElementById('modal-bg').classList.remove('open');
}

// ── TOAST ─────────────────────────────────────────────────────────────────────
function toast(msg, isErr = false) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = isErr ? 'err show' : 'show';
  clearTimeout(t._tid);
  t._tid = setTimeout(() => t.classList.remove('show'), 2600);
}

// ── DATE ──────────────────────────────────────────────────────────────────────
function todayStr() { return new Date().toISOString().split('T')[0]; }
function fmtDate(s) {
  if (!s) return '—';
  return new Date(s).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}
function daysDiff(s) {
  return Math.round((new Date(s) - new Date(todayStr())) / 86400000);
}

// ── BADGE HELPERS ─────────────────────────────────────────────────────────────
function statusBadge(st) {
  const m = { completed:'bg', active:'bc', pending:'ba', paused:'bx' };
  return `<span class="badge ${m[st]||'bx'}">${st||'—'}</span>`;
}
function goalBadge(g) {
  if (g.status === 'completed') return `<span class="badge bg">✓ done</span>`;
  const d = daysDiff(g.deadline);
  if (d < 0) return `<span class="badge br">overdue ${Math.abs(d)}d</span>`;
  if (d === 0) return `<span class="badge ba">due today</span>`;
  return `<span class="badge bc">${d}d left</span>`;
}

// ── EMPTY STATE ───────────────────────────────────────────────────────────────
function empty(icon, msg) {
  return `<div class="empty"><div class="empty-i">${icon}</div><div class="empty-t">${msg}</div></div>`;
}

// ── UPDATE STREAK BADGE ───────────────────────────────────────────────────────
async function refreshStreak() {
  const res = await getData();
  if (res.status === 'ok') {
    const streak = res.data?.default_data?.streak?.current || 0;
    document.getElementById('streak-num').textContent = streak;
  }
}
