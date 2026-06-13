// ── SKILLS ────────────────────────────────────────────────────────────────────
// Calls: GET /api/skills, POST /api/skills, POST /api/skills/<s>/topics
//        DELETE /api/skills/<s>, DELETE /api/skills/<s>/topics/<t>
// → SkillsProgress.py: view_skill, add_skill, log_skill_learning, remove_skill

async function renderSkills() {
  const el  = document.getElementById('page-skills');
  const res = await getSkills();
  if (res.status !== 'ok') { el.innerHTML = `<p class="tr">Failed to load skills</p>`; return; }

  const skills     = res.data;
  const keys       = Object.keys(skills);
  const totalTopics = keys.reduce((a, k) => a + skills[k].length, 0);

  const listHtml = keys.length === 0
    ? empty('◬', 'No skills tracked yet. Add one!')
    : keys.map(sk => {
        const topics = skills[sk];
        const chips  = topics.length
          ? topics.map(t => `<span class="chip">${t}<button onclick="doDeleteTopic('${sk}','${t}')">✕</button></span>`).join('')
          : `<span class="tm tsm">No topics yet</span>`;
        return `<div class="skr">
          <div class="sk-name">${sk}</div>
          <div class="sk-chips">${chips}</div>
          <div class="sk-cnt">${topics.length} topics</div>
          <div class="row">
            <button class="btn btn-s btn-sm" onclick="openLogTopic('${sk}')">+ Topic</button>
            <button class="btn btn-d btn-sm btn-ic" onclick="doDeleteSkill('${sk}')">✕</button>
          </div>
        </div>`;
      }).join('');

  el.innerHTML = `
    <div class="ph">
      <div><div class="pt">SKILL PROGRESS</div><div class="ps">${keys.length} SKILL(S) · ${totalTopics} TOPICS</div></div>
      <button class="btn btn-p" onclick="openAddSkill()">+ Add Skill</button>
    </div>
    <div class="card">${listHtml}</div>`;
}

function openAddSkill() {
  openModal(`
    <div class="mt">ADD SKILL</div>
    <div class="fg"><label class="fl">Skill Name</label><input class="fi" id="s-name" placeholder="e.g. NumPy, Pandas, SQL"/></div>
    <div class="ma">
      <button class="btn btn-s" onclick="closeModal()">Cancel</button>
      <button class="btn btn-p" onclick="saveNewSkill()">Add</button>
    </div>`);
}

async function saveNewSkill() {
  const name = document.getElementById('s-name').value.trim();
  if (!name) { toast('Enter a skill name', true); return; }
  const res = await addSkill({ name });
  if (res.status === 'ok') { toast('Skill added!'); closeModal(); renderSkills(); }
  else toast(res.msg, true);
}

function openLogTopic(skill) {
  openModal(`
    <div class="mt">LOG TOPIC — ${skill.toUpperCase()}</div>
    <div class="fg"><label class="fl">Topic / Sub-skill learned</label><input class="fi" id="t-topic" placeholder="e.g. Broadcasting, fancy indexing..."/></div>
    <div class="ma">
      <button class="btn btn-s" onclick="closeModal()">Cancel</button>
      <button class="btn btn-p" onclick="saveNewTopic('${skill}')">Log</button>
    </div>`);
}

async function saveNewTopic(skill) {
  const topic = document.getElementById('t-topic').value.trim();
  if (!topic) { toast('Enter a topic', true); return; }
  const res = await logTopic(skill, { topic });
  if (res.status === 'ok') { toast('Topic logged!'); closeModal(); renderSkills(); }
  else toast(res.msg, true);
}

async function doDeleteSkill(skill) {
  if (!confirm(`Delete skill "${skill}" and all topics?`)) return;
  const res = await deleteSkill(skill);
  if (res.status === 'ok') { toast('Skill removed'); renderSkills(); }
  else toast(res.msg, true);
}

async function doDeleteTopic(skill, topic) {
  const res = await deleteTopic(skill, topic);
  if (res.status === 'ok') { toast('Topic removed'); renderSkills(); }
  else toast(res.msg, true);
}
