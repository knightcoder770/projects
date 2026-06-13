// ── API CALLS → your Flask routes ────────────────────────────────────────────
// Every function here calls an endpoint defined in app.py
// which in turn calls your original Python classes

const API = {
  async get(path) {
    const r = await fetch(path);
    return r.json();
  },
  async post(path, body) {
    const r = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    return r.json();
  },
  async put(path, body) {
    const r = await fetch(path, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    return r.json();
  },
  async del(path) {
    const r = await fetch(path, { method: 'DELETE' });
    return r.json();
  }
};

// Shorthand wrappers — maps to app.py routes
const getData        = ()      => API.get('/api/data');
const getQuote       = ()      => API.get('/api/quote');
const logSession     = (body)  => API.post('/api/log', body);
const getProjects    = ()      => API.get('/api/projects');
const addProject     = (body)  => API.post('/api/projects', body);
const updateProject  = (id, b) => API.put(`/api/projects/${id}`, b);
const deleteProject  = (id)    => API.del(`/api/projects/${id}`);
const getGoals       = ()      => API.get('/api/goals');
const addGoal        = (body)  => API.post('/api/goals', body);
const completeGoal   = (id)    => API.post(`/api/goals/${id}/complete`, {});
const deleteGoal     = (id)    => API.del(`/api/goals/${id}`);
const getSkills      = ()      => API.get('/api/skills');
const addSkill       = (body)  => API.post('/api/skills', body);
const logTopic       = (s, b)  => API.post(`/api/skills/${s}/topics`, b);
const deleteSkill    = (s)     => API.del(`/api/skills/${s}`);
const deleteTopic    = (s, t)  => API.del(`/api/skills/${encodeURIComponent(s)}/topics/${encodeURIComponent(t)}`);
const getGithub      = ()      => API.get('/api/github');
const fetchGithub    = (body)  => API.post('/api/github/fetch', body);
const getReport      = ()      => API.get('/api/report');
