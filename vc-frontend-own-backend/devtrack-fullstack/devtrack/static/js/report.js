// ── WEEKLY REPORT ─────────────────────────────────────────────────────────────
// Calls: GET /api/report
// → WeeklyReport.py: generate_report() + display_report()

async function renderReport() {
  const el  = document.getElementById('page-report');
  el.innerHTML = `<div class="ph"><div><div class="pt">WEEKLY REPORT</div></div></div><div class="tm tsm" style="padding:20px">Generating report...</div>`;

  const res = await getReport();

  if (res.status !== 'ok' || !res.data) {
    el.innerHTML = `
      <div class="ph"><div><div class="pt">WEEKLY REPORT</div></div></div>
      <div class="card">${empty('◫', 'No sessions logged this week yet.')}</div>`;
    return;
  }

  const r = res.data;

  const tableRows = (r.daily_rows || []).map(row => `
    <tr>
      <td>${fmtDate(row.date)}</td>
      <td><span class="ta">${row.hours_coded}h</span></td>
      <td>${row.work||'—'}</td>
      <td class="tm">${row.learning_outcome||'—'}</td>
    </tr>`).join('');

  const skillsHtml = Object.keys(r.skills||{}).length === 0
    ? `<div class="tm tsm">No skills tracked</div>`
    : Object.entries(r.skills).map(([s,cnt])=>
        `<div class="skr"><div class="sk-name">${s}</div><div class="sk-cnt">${cnt} topics</div></div>`
      ).join('');

  el.innerHTML = `
    <div class="ph">
      <div><div class="pt">WEEKLY REPORT</div><div class="ps">WEEK OF ${fmtDate(r.monday)} → ${fmtDate(r.today)}</div></div>
      <button class="btn btn-s" onclick="downloadReport()">⬇ Save JSON</button>
    </div>

    <div class="sg">
      <div class="sc"><div class="sl">Hours This Week</div><div class="sv">${r.total_hours}</div><div class="ss">${(r.daily_rows||[]).length} sessions</div></div>
      <div class="sc am"><div class="sl">Most Productive</div><div class="sv" style="font-size:14px;line-height:1.3">${fmtDate(r.most_productive)}</div></div>
      <div class="sc cy"><div class="sl">Streak</div><div class="sv">${r.streak}</div><div class="ss">days 🔥</div></div>
      <div class="sc pu"><div class="sl">Goals Done</div><div class="sv">${r.goals_completed}/${r.total_goals}</div></div>
    </div>

    <div class="card" style="margin-bottom:16px">
      <div class="ct">Daily Breakdown</div>
      <table class="dt">
        <thead><tr><th>Date</th><th>Hours</th><th>Work</th><th>Learning</th></tr></thead>
        <tbody>${tableRows}</tbody>
      </table>
    </div>

    <div class="card">
      <div class="ct">Skills Being Tracked</div>
      ${skillsHtml}
    </div>`;

  // stash for download
  window._lastReport = r;
}

function downloadReport() {
  const r = window._lastReport;
  if (!r) return;
  const blob = new Blob([JSON.stringify({
    week: r.monday, total_hours: r.total_hours,
    streak: r.streak, goals_completed: r.goals_completed,
    generated_at: new Date().toISOString()
  }, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `weekly_report_${r.monday}.json`;
  a.click();
  toast('Report downloaded!');
}
