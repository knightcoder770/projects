// ── PROJECTS ──────────────────────────────────────────────────────────────────
// Calls: GET/POST /api/projects, PUT/DELETE /api/projects/<id>
// → ManageProjects.py: view_projects, add_project, update_project, delete_project

async function renderProjects() {
  const el  = document.getElementById('page-projects');
  const res = await getProjects();
  if (res.status !== 'ok') { el.innerHTML = `<p class="tr">Failed to load projects</p>`; return; }

  const projects = res.data;
  const keys     = Object.keys(projects);

  const listHtml = keys.length === 0
    ? empty('◧', 'No projects yet. Add your first one!')
    : keys.map(pid => {
        const p = projects[pid];
        return `<div class="pi">
          <div class="pi-hdr">
            <span class="pi-name">${p.name||'Untitled'}</span>
            ${statusBadge(p.status||'active')}
            <div class="pi-acts">
              <button class="btn btn-s btn-sm btn-ic" onclick="openEditProject('${pid}')">✎</button>
              <button class="btn btn-d btn-sm btn-ic" onclick="doDeleteProject('${pid}')">✕</button>
            </div>
          </div>
          <div class="pi-desc">${p.description||'—'}</div>
          <div class="pi-meta">
            <span>🗂 ${(p.tech_stack||[]).join(', ')||'—'}</span>
            <span>📅 Started: ${fmtDate(p.date_started)}</span>
            <span>🔄 Last: ${fmtDate(p.last_worked)}</span>
            ${p.completed_date?`<span>✅ Done: ${fmtDate(p.completed_date)}</span>`:''}
            ${p.github_url?`<span><a href="${p.github_url}" target="_blank" class="tc">⬡ GitHub</a></span>`:''}
          </div>
        </div>`;
      }).join('');

  el.innerHTML = `
    <div class="ph">
      <div><div class="pt">PROJECTS</div><div class="ps">${keys.length} PROJECT(S) TRACKED</div></div>
      <button class="btn btn-p" onclick="openAddProject()">+ New Project</button>
    </div>
    <div class="card">${listHtml}</div>`;
}

function projectForm(p = {}, submitFn, title) {
  openModal(`
    <div class="mt">${title}</div>
    <div class="fg"><label class="fl">Project Name</label><input class="fi" id="p-name" value="${p.name||''}" placeholder="e.g. DevTrack"/></div>
    <div class="fg"><label class="fl">Description</label><textarea class="fta" id="p-desc">${p.description||''}</textarea></div>
    <div class="fg"><label class="fl">Tech Stack (comma separated)</label><input class="fi" id="p-stack" value="${(p.tech_stack||[]).join(', ')}" placeholder="Python, Flask, JS"/></div>
    <div class="fg"><label class="fl">Status</label>
      <select class="fs" id="p-status">
        ${['active','paused','completed'].map(s=>`<option value="${s}" ${p.status===s?'selected':''}>${s}</option>`).join('')}
      </select>
    </div>
    <div class="fg"><label class="fl">GitHub URL (optional)</label><input class="fi" id="p-github" value="${p.github_url||''}" placeholder="https://github.com/..."/></div>
    <div class="g2i">
      <div class="fg"><label class="fl">Date Started</label><input class="fi" type="date" id="p-started" value="${p.date_started||todayStr()}"/></div>
      <div class="fg"><label class="fl">Last Worked</label><input class="fi" type="date" id="p-last" value="${p.last_worked||todayStr()}"/></div>
    </div>
    <div class="fg"><label class="fl">Completed Date (blank if ongoing)</label><input class="fi" type="date" id="p-done" value="${p.completed_date||''}"/></div>
    <div class="ma">
      <button class="btn btn-s" onclick="closeModal()">Cancel</button>
      <button class="btn btn-p" onclick="${submitFn}">Save</button>
    </div>`);
}

function openAddProject() {
  projectForm({}, 'saveNewProject()', 'ADD PROJECT');
}

async function saveNewProject() {
  const body = collectProjectForm();
  if (!body) return;
  const res = await addProject(body);
  if (res.status === 'ok') { toast('Project added!'); closeModal(); renderProjects(); }
  else toast(res.msg, true);
}

function openEditProject(pid) {
  getProjects().then(res => {
    const p = res.data[pid];
    projectForm(p, `saveEditProject('${pid}')`, `EDIT PROJECT — #${pid}`);
  });
}

async function saveEditProject(pid) {
  const body = collectProjectForm();
  if (!body) return;
  const res = await updateProject(pid, body);
  if (res.status === 'ok') { toast('Project updated!'); closeModal(); renderProjects(); }
  else toast(res.msg, true);
}

function collectProjectForm() {
  const name = document.getElementById('p-name').value.trim();
  if (!name) { toast('Project name is required', true); return null; }
  return {
    name,
    description:    document.getElementById('p-desc').value.trim(),
    tech_stack:     document.getElementById('p-stack').value.split(',').map(s=>s.trim()).filter(Boolean),
    status:         document.getElementById('p-status').value,
    github_url:     document.getElementById('p-github').value.trim(),
    date_started:   document.getElementById('p-started').value,
    last_worked:    document.getElementById('p-last').value,
    completed_date: document.getElementById('p-done').value,
  };
}

async function doDeleteProject(pid) {
  if (!confirm(`Delete project #${pid}?`)) return;
  const res = await deleteProject(pid);
  if (res.status === 'ok') { toast('Project deleted'); renderProjects(); }
  else toast(res.msg, true);
}
