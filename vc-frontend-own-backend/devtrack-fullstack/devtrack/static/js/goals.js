// ── GOALS ─────────────────────────────────────────────────────────────────────
// Calls: GET /api/goals, POST /api/goals, POST /api/goals/<id>/complete, DELETE /api/goals/<id>
// → GoalsTracker.py: view_goals, add_goals, complete_goals, delete_goals

async function renderGoals() {
  const el  = document.getElementById('page-goals');
  const res = await getGoals();
  if (res.status !== 'ok') { el.innerHTML = `<p class="tr">Failed to load goals</p>`; return; }

  const goals   = res.data;
  const keys    = Object.keys(goals);
  const pending = keys.filter(k => goals[k].status === 'pending').length;
  const done    = keys.filter(k => goals[k].status === 'completed').length;

  const listHtml = keys.length === 0
    ? empty('◎', 'No goals yet. Set one and crush it!')
    : keys.map(gid => {
        const g = goals[gid];
        return `<div class="gi">
          <div class="gi-id">#${gid}</div>
          <div style="flex:1">
            <div class="gi-txt">${g.goal}</div>
            <div class="gi-meta">
              ${goalBadge(g)}
              <span class="tm tsm">deadline: ${fmtDate(g.deadline)}</span>
              <span class="tm tsm">created: ${fmtDate(g.created)}</span>
              ${g.completed && g.completed!=="'" ? `<span class="tg tsm">✓ done: ${fmtDate(g.completed)}</span>` : ''}
            </div>
          </div>
          <div class="gi-acts">
            ${g.status !== 'completed' ? `<button class="btn btn-s btn-sm" onclick="doCompleteGoal('${gid}')">✓</button>` : ''}
            <button class="btn btn-d btn-sm btn-ic" onclick="doDeleteGoal('${gid}')">✕</button>
          </div>
        </div>`;
      }).join('');

  el.innerHTML = `
    <div class="ph">
      <div><div class="pt">GOAL TRACKER</div><div class="ps">${pending} PENDING · ${done} COMPLETED</div></div>
      <button class="btn btn-p" onclick="openAddGoal()">+ New Goal</button>
    </div>
    <div class="card">${listHtml}</div>`;
}

function openAddGoal() {
  openModal(`
    <div class="mt">ADD GOAL</div>
    <div class="fg"><label class="fl">Goal</label><input class="fi" id="g-goal" placeholder="e.g. Complete NumPy week"/></div>
    <div class="fg"><label class="fl">Deadline</label><input class="fi" type="date" id="g-deadline" value="${todayStr()}"/></div>
    <div class="ma">
      <button class="btn btn-s" onclick="closeModal()">Cancel</button>
      <button class="btn btn-p" onclick="saveNewGoal()">Add Goal</button>
    </div>`);
}

async function saveNewGoal() {
  const goal     = document.getElementById('g-goal').value.trim();
  const deadline = document.getElementById('g-deadline').value;
  if (!goal)     { toast('Enter a goal', true); return; }
  if (!deadline) { toast('Pick a deadline', true); return; }

  const res = await addGoal({ goal, deadline });
  if (res.status === 'ok') { toast('Goal added!'); closeModal(); renderGoals(); }
  else toast(res.msg, true);
}

async function doCompleteGoal(gid) {
  const res = await completeGoal(gid);
  if (res.status === 'ok') { toast('Goal completed! 🎉'); renderGoals(); }
  else toast(res.msg, true);
}

async function doDeleteGoal(gid) {
  if (!confirm(`Delete goal #${gid}?`)) return;
  const res = await deleteGoal(gid);
  if (res.status === 'ok') { toast('Goal deleted'); renderGoals(); }
  else toast(res.msg, true);
}
