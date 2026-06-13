// ── GITHUB STATS ──────────────────────────────────────────────────────────────
// Calls: GET /api/github, POST /api/github/fetch
// → GithubStats.py: get_github_stats(), github_dashboard()

async function renderGithub() {
  const el  = document.getElementById('page-github');
  const res = await getGithub();
  const gh  = (res.status === 'ok' ? res.data : {}) || {};
  const profile = gh.profile;
  const repos   = gh.repos || [];

  const profileHtml = profile
    ? `<div class="gh-prof">
        <div class="gh-av">${(profile.username||'U')[0].toUpperCase()}</div>
        <div>
          <div class="gh-name">${profile.fullname||profile.username}</div>
          <div class="gh-user">@${profile.username}</div>
          <div class="gh-join">Joined: ${fmtDate((profile['joined date']||'').split('T')[0])}</div>
        </div>
      </div>
      <div class="sg" style="margin-bottom:0">
        <div class="sc"><div class="sl">Followers</div><div class="sv">${profile.followers}</div></div>
        <div class="sc am"><div class="sl">Following</div><div class="sv">${profile.following}</div></div>
        <div class="sc cy"><div class="sl">Public Repos</div><div class="sv">${profile.repo_count}</div></div>
      </div>`
    : `<div class="tm tsm">No profile loaded. Enter your username and hit Fetch.</div>`;

  const reposHtml = repos.length === 0
    ? empty('⬡', 'No repos loaded yet.')
    : `<table class="dt">
        <thead><tr><th>#</th><th>Repo</th><th>Stars</th><th>Language</th><th>Last Updated</th></tr></thead>
        <tbody>
          ${repos.map((r,i)=>`<tr>
            <td class="tm">${i+1}</td>
            <td class="tg">${r.repo_name}</td>
            <td>⭐ ${r.star_count}</td>
            <td>${r.language_used||'—'}</td>
            <td class="tm">${fmtDate((r.last_updated||'').split('T')[0])}</td>
          </tr>`).join('')}
        </tbody>
      </table>`;

  el.innerHTML = `
    <div class="ph">
      <div><div class="pt">GITHUB STATS</div><div class="ps">${gh.username ? '@'+gh.username : 'NOT CONNECTED'}</div></div>
    </div>
    <div class="card" style="margin-bottom:16px">
      <div class="ct">Fetch GitHub Stats</div>
      <div class="row">
        <input class="fi" id="gh-user" placeholder="GitHub username" value="${gh.username||''}" style="flex:1"/>
        <button class="btn btn-p" onclick="doFetchGithub()">⬡ Fetch</button>
      </div>
      <div id="gh-msg" style="margin-top:8px;font-size:11px;color:var(--text3)"></div>
    </div>
    <div class="card" style="margin-bottom:16px">
      <div class="ct">Profile</div>
      ${profileHtml}
    </div>
    <div class="card">
      <div class="ct">Repositories</div>
      ${reposHtml}
    </div>`;
}

async function doFetchGithub() {
  const username = document.getElementById('gh-user').value.trim();
  if (!username) { toast('Enter a GitHub username', true); return; }
  document.getElementById('gh-msg').textContent = 'Fetching...';
  const res = await fetchGithub({ username });
  if (res.status === 'ok') { toast('GitHub stats fetched!'); renderGithub(); }
  else { toast(res.msg, true); document.getElementById('gh-msg').textContent = res.msg; }
}
