"""
DevTrack — Flask API Server
---------------------------
Your original Python classes are imported as-is.
This file replaces input() calls with JSON request bodies,
and returns JSON responses to the frontend.

Run: python app.py
Open: http://localhost:5000
"""

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from datetime import datetime, date
import requests as req_lib

# ── Import YOUR classes (unchanged files) ────────────────────────────────────
from update_data   import UpdateData
from dashboard     import dashboard
from log_streak    import login
from ManageProjects import ManageProjects
from GoalsTracker  import GoalsTracker
from SkillsProgress import SkillProgress
from GithubStats   import GithubStats
from WeeklyReport  import WeeklyReport

app  = Flask(__name__)
CORS(app)

# ── Shared instances (same pattern as your main.py) ──────────────────────────
ud = UpdateData()
db = dashboard()
lg = login()
mp = ManageProjects()
gt = GoalsTracker()
sp = SkillProgress()
gh = GithubStats()
wr = WeeklyReport()

# ── Helper: serialize data (handles date objects) ────────────────────────────
def serial(obj):
    if isinstance(obj, (date, datetime)):
        return obj.strftime('%Y-%m-%d')
    return str(obj)

def ok(payload=None, msg="ok"):
    return jsonify({"status": "ok", "msg": msg, "data": payload})

def err(msg):
    return jsonify({"status": "error", "msg": msg}), 400


# ══════════════════════════════════════════════════════════════════════════════
# SERVE FRONTEND
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


# ══════════════════════════════════════════════════════════════════════════════
# DATA — load / save  (your UpdateData class)
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/data", methods=["GET"])
def get_data():
    data = ud.load_data()
    return ok(data)


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD — quote  (your dashboard class)
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/quote", methods=["GET"])
def get_quote():
    # dashboard.fetch_quote() uses requests internally — reuse it directly
    quote = db.fetch_quote()
    return ok(quote)


# ══════════════════════════════════════════════════════════════════════════════
# SESSION LOG + STREAK  (your login class)
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/log", methods=["POST"])
def log_session():
    """
    Replaces: lg.log_session(data) which used input()
    Body: { hours_coded, work, learning_outcome, date? }
    """
    body = request.json or {}
    hours   = body.get("hours_coded")
    work    = body.get("work", "").strip()
    outcome = body.get("learning_outcome", "").strip()
    log_date = body.get("date", datetime.now().strftime("%Y-%m-%d"))

    if not hours or not isinstance(hours, int) or not (1 <= hours <= 24):
        return err("hours_coded must be an integer between 1 and 24")
    if not work:
        return err("work field is required")
    if not outcome:
        return err("learning_outcome field is required")

    data = ud.load_data()

    # Replicate what log_streak.py's log_session() does (without input())
    data['daily_data']['date'].append(log_date)
    data['daily_data']['time'].append(datetime.now().strftime("%H:%M:%S"))
    data['daily_data']['hours_coded'].append(hours)
    data['daily_data']['work'].append(work)
    data['daily_data']['learning_outcome'].append(outcome)

    # Replicate streak() logic from log_streak.py
    today = datetime.now().date()
    streak = data['default_data']['streak']

    if not streak.get('last_logged'):
        streak['last_logged'] = today.strftime("%Y-%m-%d")
        streak['current'] = 1
        streak['longest'] = 1
    else:
        prev = datetime.strptime(streak['last_logged'], "%Y-%m-%d").date()
        diff = abs((today - prev).days)
        if diff == 0:
            pass  # already logged today
        elif diff == 1:
            streak['current'] += 1
        else:
            streak['current'] = 1

        if streak['current'] > streak.get('longest', 0):
            streak['longest'] = streak['current']
        streak['last_logged'] = today.strftime("%Y-%m-%d")

    ud.save_data(data)
    return ok({"streak": streak}, msg="Session logged!")


# ══════════════════════════════════════════════════════════════════════════════
# PROJECTS  (your ManageProjects class)
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/projects", methods=["GET"])
def get_projects():
    data = ud.load_data()
    return ok(data.get("project", {}))


@app.route("/api/projects", methods=["POST"])
def add_project():
    """
    Replaces: mp.add_project(data) which used input()
    Body: { name, description, tech_stack[], status, github_url, date_started, last_worked, completed_date }
    """
    body = request.json or {}
    name = body.get("name", "").strip()
    if not name:
        return err("Project name is required")

    data = ud.load_data()
    prev_id = int(data.get("project_id", 0))
    new_id  = str(prev_id + 1)

    data["project"][new_id] = {
        "name":           name,
        "description":    body.get("description", "").strip(),
        "tech_stack":     body.get("tech_stack", []),
        "status":         body.get("status", "active"),
        "github_url":     body.get("github_url", "").strip(),
        "date_started":   body.get("date_started", ""),
        "last_worked":    body.get("last_worked", ""),
        "completed_date": body.get("completed_date", ""),
    }
    data["project_id"] = new_id
    ud.save_data(data)
    return ok({"id": new_id, "project": data["project"][new_id]}, msg="Project added!")


@app.route("/api/projects/<pid>", methods=["PUT"])
def update_project(pid):
    """Replaces: mp.update_project(data) which used input()"""
    body = request.json or {}
    data = ud.load_data()

    if pid not in data["project"]:
        return err(f"Project {pid} not found")

    proj = data["project"][pid]
    for field in ["name", "description", "tech_stack", "status", "github_url",
                  "date_started", "last_worked", "completed_date"]:
        if field in body:
            proj[field] = body[field]

    ud.save_data(data)
    return ok(proj, msg="Project updated!")


@app.route("/api/projects/<pid>", methods=["DELETE"])
def delete_project(pid):
    """Replaces: mp.delete_project(data) which used input()"""
    data = ud.load_data()
    if pid not in data["project"]:
        return err(f"Project {pid} not found")
    del data["project"][pid]
    ud.save_data(data)
    return ok(msg="Project deleted!")


# ══════════════════════════════════════════════════════════════════════════════
# GOALS  (your GoalsTracker class)
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/goals", methods=["GET"])
def get_goals():
    data = ud.load_data()
    # Run view_goals message calculation (reused from GoalsTracker)
    goals = data.get("goals", {})
    today = datetime.now().date()
    for gid, details in goals.items():
        try:
            deadline_obj = datetime.strptime(details['deadline'], '%Y-%m-%d').date()
            diff = (deadline_obj - today).days
            if details['status'] == 'completed':
                details['message'] = '✅ completed'
            elif diff < 0:
                details['message'] = f"⚠️ overdue by {abs(diff)} days"
            elif diff == 0:
                details['message'] = "⚠️ due today"
            else:
                details['message'] = f"🕛 {diff} days left"
        except Exception:
            details['message'] = ''
    return ok(goals)


@app.route("/api/goals", methods=["POST"])
def add_goal():
    """Replaces: gt.add_goals(data) which used input()"""
    body = request.json or {}
    goal     = body.get("goal", "").strip()
    deadline = body.get("deadline", "").strip()

    if not goal:
        return err("Goal text is required")
    if not deadline:
        return err("Deadline is required")
    try:
        datetime.strptime(deadline, "%Y-%m-%d")
    except ValueError:
        return err("Deadline must be YYYY-MM-DD")

    data   = ud.load_data()
    new_id = str(int(data.get("goal_id", 0)) + 1)

    data["goals"][new_id] = {
        "goal":      goal,
        "deadline":  deadline,
        "status":    "pending",
        "created":   datetime.now().date().strftime("%Y-%m-%d"),
        "completed": "",
        "message":   ""
    }
    data["goal_id"] = int(new_id)
    ud.save_data(data)
    return ok({"id": new_id}, msg="Goal added!")


@app.route("/api/goals/<gid>/complete", methods=["POST"])
def complete_goal(gid):
    """Replaces: gt.complete_goals(data) which used input()"""
    data = ud.load_data()
    if gid not in data["goals"]:
        return err(f"Goal {gid} not found")
    if data["goals"][gid]["status"] == "completed":
        return err("Goal is already completed")
    data["goals"][gid]["status"]    = "completed"
    data["goals"][gid]["completed"] = datetime.now().date().strftime("%Y-%m-%d")
    ud.save_data(data)
    return ok(msg="Goal marked complete! 🎉")


@app.route("/api/goals/<gid>", methods=["DELETE"])
def delete_goal(gid):
    """Replaces: gt.delete_goals(data) which used input()"""
    data = ud.load_data()
    if gid not in data["goals"]:
        return err(f"Goal {gid} not found")
    del data["goals"][gid]
    ud.save_data(data)
    return ok(msg="Goal deleted!")


# ══════════════════════════════════════════════════════════════════════════════
# SKILLS  (your SkillProgress class)
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/skills", methods=["GET"])
def get_skills():
    data = ud.load_data()
    return ok(data.get("skills", {}))


@app.route("/api/skills", methods=["POST"])
def add_skill():
    """Replaces: sp.add_skill(data) which used input()"""
    body = request.json or {}
    name = body.get("name", "").strip().lower()
    if not name:
        return err("Skill name required")
    data = ud.load_data()
    if name in data["skills"]:
        return err("Skill already registered")
    data["skills"][name] = []
    ud.save_data(data)
    return ok(msg=f"Skill '{name}' added!")


@app.route("/api/skills/<skill>/topics", methods=["POST"])
def log_topic(skill):
    """Replaces: sp.log_skill_learning(data) which used input()"""
    body  = request.json or {}
    topic = body.get("topic", "").strip()
    if not topic:
        return err("Topic is required")
    data = ud.load_data()
    if skill not in data["skills"]:
        return err(f"Skill '{skill}' not found")
    if topic in data["skills"][skill]:
        return err("Topic already logged")
    data["skills"][skill].append(topic)
    ud.save_data(data)
    return ok(msg="Topic logged!")


@app.route("/api/skills/<skill>", methods=["DELETE"])
def delete_skill(skill):
    """Replaces: sp.remove_skill(data) for entire skill"""
    data = ud.load_data()
    if skill not in data["skills"]:
        return err(f"Skill '{skill}' not found")
    del data["skills"][skill]
    ud.save_data(data)
    return ok(msg="Skill removed!")


@app.route("/api/skills/<skill>/topics/<topic>", methods=["DELETE"])
def delete_topic(skill, topic):
    """Replaces: sp.remove_skill(data) for subskill"""
    data = ud.load_data()
    if skill not in data["skills"]:
        return err(f"Skill '{skill}' not found")
    if topic not in data["skills"][skill]:
        return err(f"Topic '{topic}' not found")
    data["skills"][skill].remove(topic)
    ud.save_data(data)
    return ok(msg="Topic removed!")


# ══════════════════════════════════════════════════════════════════════════════
# GITHUB  (your GithubStats class)
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/github", methods=["GET"])
def get_github():
    data = ud.load_data()
    return ok(data.get("github", {}))


@app.route("/api/github/fetch", methods=["POST"])
def fetch_github():
    """
    Replaces: gh.get_github_stats(data) which used input()
    Body: { username }
    """
    body     = request.json or {}
    username = body.get("username", "").strip()
    if not username:
        data = ud.load_data()
        username = data.get("github", {}).get("username", "")
    if not username:
        return err("GitHub username required")

    data = ud.load_data()

    # Reuse GithubStats class logic directly
    profile_res = req_lib.get(f"https://api.github.com/users/{username}", timeout=8)
    if profile_res.status_code != 200:
        return err("GitHub user not found or API rate limited")

    p = profile_res.json()
    data["github"]["username"] = username
    data["github"]["profile"]  = {
        "username":    p["login"],
        "fullname":    p.get("name") or p["login"],
        "followers":   p["followers"],
        "following":   p["following"],
        "repo_count":  p["public_repos"],
        "joined date": p["created_at"]
    }

    repos_res = req_lib.get(f"https://api.github.com/users/{username}/repos?per_page=100", timeout=8)
    if repos_res.status_code == 200:
        raw_repos = repos_res.json()
        raw_repos.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        data["github"]["repos"] = [
            {
                "repo_name":     r["name"],
                "star_count":    r["stargazers_count"],
                "language_used": r["language"],
                "last_updated":  r["updated_at"]
            }
            for r in raw_repos
        ]

    ud.save_data(data)
    return ok(data["github"], msg="GitHub stats fetched!")


# ══════════════════════════════════════════════════════════════════════════════
# WEEKLY REPORT  (your WeeklyReport class)
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/report", methods=["GET"])
def get_report():
    """Replaces: wr.generate_report(data) + wr.display_report(data)"""
    data   = ud.load_data()
    report = wr.generate_report(data)

    if not report:
        return ok(None, msg="No sessions logged this week yet")

    # Serialize — pandas Timestamp / date objects need converting
    return ok({
        "total_hours":     report["total_hours"],
        "most_productive": str(report["most_productive"]),
        "streak":          report["streak"],
        "goals_completed": report["goals_completed"],
        "total_goals":     report["total_goals"],
        "monday":          str(report["monday"]),
        "today":           str(report["today"]),
        "daily_rows": report["this_week_df"][["date","hours_coded","work","learning_outcome"]]
                            .assign(date=lambda df: df["date"].astype(str))
                            .to_dict(orient="records"),
        "skills": {k: len(v) for k, v in data.get("skills", {}).items()}
    })


# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n  🟢  DevTrack running → http://localhost:5000\n")
    app.run(debug=True, port=5000)
