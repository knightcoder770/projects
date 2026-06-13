// ── LOG SESSION ───────────────────────────────────────────────────────────────
// Calls: POST /api/log  (→ log_streak.py: log_session() + streak())
//        GET  /api/data (→ update_data.py: load_data())

async function renderLog() {
  const el = document.getElementById('page-log');

  const dataRes = await getData();
  const d = dataRes.data || { daily_data: { date:[], hours_coded:[], work:[], learning_outcome:[] } };

  const histHtml = d.daily_data.date.length === 0
    ? empty('📋', 'No sessions logged yet.')
    : d.daily_data.date.slice(-10).reverse().map((dt, i) => {
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

  el.innerHTML = `
    <div class="ph">
      <div><div class="pt">LOG SESSION</div><div class="ps">RECORD TODAY'S CODING SESSION</div></div>
    </div>
    <div class="g2" style="align-items:start">
      <div class="card">
        <div class="ct">New Session</div>
        <div class="fg"><label class="fl">Date</label><input class="fi" type="date" id="l-date" value="${todayStr()}"/></div>
        <div class="fg"><label class="fl">Hours Coded</label><input class="fi" type="number" id="l-hours" min="1" max="24" placeholder="e.g. 3"/></div>
        <div class="fg"><label class="fl">What did you build / work on?</label><textarea class="fta" id="l-work" placeholder="e.g. NumPy broadcasting mini project..."></textarea></div>
        <div class="fg"><label class="fl">What did you learn?</label><textarea class="fta" id="l-outcome" placeholder="e.g. Learned fancy indexing in NumPy..."></textarea></div>
        <button class="btn btn-p" onclick="submitLog()">⬡ Save Session</button>
      </div>
      <div class="card"><div class="ct">Session History</div>${histHtml}</div>
    </div>`;
}

async function submitLog() {
  const date    = document.getElementById('l-date').value;
  const hours   = parseInt(document.getElementById('l-hours').value);
  const work    = document.getElementById('l-work').value.trim();
  const outcome = document.getElementById('l-outcome').value.trim();

  if (!date)                             { toast('Pick a date', true); return; }
  if (!hours || hours < 1 || hours > 24) { toast('Enter valid hours (1–24)', true); return; }
  if (!work)                             { toast('Describe what you worked on', true); return; }
  if (!outcome)                          { toast('Add a learning outcome', true); return; }

  const res = await logSession({ date, hours_coded: hours, work, learning_outcome: outcome });
  if (res.status === 'ok') {
    toast('Session logged! 🔥');
    document.getElementById('streak-num').textContent = res.data?.streak?.current || '?';
    renderLog();
  } else {
    toast(res.msg || 'Error', true);
  }
}
