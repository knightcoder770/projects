# DevTrack 🟢

A developer journey tracker. Log your coding sessions, track projects, goals, skills, and GitHub stats — all in one place.

**Backend:** Python (your original classes) + Flask API  
**Frontend:** Vanilla HTML/CSS/JS — vibe coded

---

## Project Structure

```
devtrack/
├── app.py                  ← Flask server (API routes)
├── requirements.txt
├── devtrack_data.json      ← your data file
│
├── dashboard.py            ← Quote of the day
├── log_streak.py           ← Session logging + streak logic
├── ManageProjects.py       ← Project CRUD
├── GoalsTracker.py         ← Goal tracking
├── SkillsProgress.py       ← Skill + topic tracking
├── GithubStats.py          ← GitHub API integration
├── WeeklyReport.py         ← Weekly summary generation
├── update_data.py          ← JSON load/save
│
├── templates/
│   └── index.html          ← Frontend entry point
└── static/
    ├── css/style.css
    └── js/
        ├── api.js          ← All fetch() calls to Flask
        ├── utils.js        ← Navigation, modal, toast
        ├── dashboard.js
        ├── log.js
        ├── projects.js
        ├── goals.js
        ├── skills.js
        ├── github.js
        └── report.js
```

---

## Setup & Run

```bash
pip install -r requirements.txt
python app.py
```

Then open **http://localhost:5000** in your browser.

---

## API Endpoints

| Method | Route | Python Class |
|--------|-------|-------------|
| GET | `/api/data` | `UpdateData.load_data()` |
| GET | `/api/quote` | `dashboard.fetch_quote()` |
| POST | `/api/log` | `login.log_session()` + `login.streak()` |
| GET/POST | `/api/projects` | `ManageProjects` |
| PUT/DELETE | `/api/projects/<id>` | `ManageProjects` |
| GET/POST | `/api/goals` | `GoalsTracker` |
| POST | `/api/goals/<id>/complete` | `GoalsTracker.complete_goals()` |
| DELETE | `/api/goals/<id>` | `GoalsTracker.delete_goals()` |
| GET/POST | `/api/skills` | `SkillProgress` |
| POST | `/api/skills/<s>/topics` | `SkillProgress.log_skill_learning()` |
| DELETE | `/api/skills/<s>` | `SkillProgress.remove_skill()` |
| DELETE | `/api/skills/<s>/topics/<t>` | `SkillProgress.remove_skill()` |
| GET | `/api/github` | `GithubStats.github_dashboard()` |
| POST | `/api/github/fetch` | `GithubStats.get_github_stats()` |
| GET | `/api/report` | `WeeklyReport.generate_report()` |
