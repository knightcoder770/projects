// ── DASHBOARD ─────────────────────────────────────────────────────────────────
// Calls: GET /api/data, GET /api/quote  (→ dashboard.py + update_data.py)

async function renderDashboard() {
  const el = document.getElementById('page-dashboard');
  el.innerHTML = `<div class="ph"><div><div class="pt">DASHBOARD</div><div class="ps">${new Date().toDateString().toUpperCase()}</div></div></div>
    <div class="qbox"><div class="qt" style="color:var(--text3)">Loading quote...</div></div>
    <div class="sg" id="dash-stats"></div>
    <div class="g2" id="dash-bottom"></div>`;

  // Fetch both in parallel
  const [dataRes, quoteRes] = await Promise.all([getData(), getQuote()]);

  // Quote (dashboard.py → fetch_quote())
  if (quoteRes.status === 'ok') {
    const q = quoteRes.data;
    el.querySelector('.qbox').innerHTML =
      `<div class="qt">"${q.quote}"</div><div class="qa">— ${q.author}</div>`;
  }

  if (dataRes.status !== 'ok') return;
  const d = dataRes.data;

  const sessions    = d.daily_data.date.length;
  const totalHours  = d.daily_data.hours_coded.reduce((a, b) => a + b, 0);
  const projects    = Object.keys(d.project).length;
  const doneGoals   = Object.values(d.goals).filter(g => g.status === 'completed').length;
  const totalGoals  = Object.keys(d.goals).length;
  const streak      = d.default_data.streak;

  // Stats
  document.getElementById('dash-stats').innerHTML = `
    <div class="sc"><div class="sl">Current Streak</div><div class="sv">${streak.current}</div><div class="ss">longest: ${streak.longest} days</div></div>
    <div class="sc am"><div class="sl">Total Hours</div><div class="sv">${totalHours}</div><div class="ss">${sessions} sessions</div></div>
    <div class="sc cy"><div class="sl">Projects</div><div class="sv">${projects}</div><div class="ss">tracked</div></div>
    <div class="sc pu"><div class="sl">Goals Done</div><div class="sv">${doneGoals}/${totalGoals}</div><div class="ss">goals</div></div>`;

  // Chart — last 7 sessions
  const last7h = d.daily_data.hours_coded.slice(-7);
  const last7d = d.daily_data.date.slice(-7);
  const maxH = Math.max(...last7h, 1);
  const barsHtml = last7h.length
    ? last7h.map((h, i) => `<div class="bw">
        <div class="bv">${h}h</div>
        <div class="bar" style="height:${Math.round(h/maxH*100)}%"></div>
        <div class="bl">${last7d[i]?.slice(5)||''}</div>
      </div>`).join('')
    : `<div class="tm tsm" style="padding:8px">No sessions yet</div>`;

  // Recent sessions
  const recentHtml = sessions === 0
    ? empty('📋', 'No sessions yet. Hit Log Session!')
    : d.daily_data.date.slice(-5).reverse().map((dt, i) => {
        const ri = d.daily_data.date.length - 1 - i;
        return `<div class="si">
          <div class="si-date">${fmtDate(dt)}</div>
          <div class="si-h">${d.daily_data.hours_coded[ri]}h</div>
          <div>
            <div class="si-work">${d.daily_data.work[ri]||'—'}</div>
            <div class="si-out">↳ ${d.daily_data.learning_outcome[ri]||'—'}</div>
          </div>
        </div>`;
      }).join('');

  document.getElementById('dash-bottom').innerHTML = `
    <div class="card"><div class="ct">Hours (Last 7 Sessions)</div><div class="bars">${barsHtml}</div></div>
    <div class="card"><div class="ct">Recent Sessions</div>${recentHtml}</div>`;
}
