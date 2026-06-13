from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime, date

# ── Import YOUR classes exactly as they are ──────────────────────────────────
from update_data import UpdateData
from log_streak import login
from ManageProjects import ManageProjects
from GoalsTracker import GoalsTracker
from SkillsProgress import SkillProgress
from GithubStats import GithubStats
from WeeklyReport import WeeklyReport
from dashboard import dashboard

app = Flask(__name__)
CORS(app)  # allow frontend to talk to backend

# Instantiate your classes (same as main.py does)
ud = UpdateData()
lg = login()
mp = ManageProjects()
gt = GoalsTracker()
sp = SkillProgress()
gh = GithubStats()
wr = WeeklyReport()
db = dashboard()


# ── HELPER: date-safe JSON ────────────────────────────────────────────────────
def safe_json(data):
    """Convert date/datetime objects to strings before jsonify."""
    import json
    def default(obj):
        if isinstance(obj, (date, datetime)):
            return obj.strftime('%Y-%m-%d')
        return str(obj)
    return json.loads(json.dumps(data, default=default))


# ── DATA ──────────────────────────────────────────────────────────────────────
@app.route('/api/data', methods=['GET'])
def get_data():
    """Return the full devtrack_data.json — same as UpdateData.load_data()"""
    data = ud.load_data()
    return jsonify(safe_json(data))


# ── DASHBOARD / QUOTE ─────────────────────────────────────────────────────────
@app.route('/api/quote', methods=['GET'])
def get_quote():
    """Calls dashboard.fetch_quote() — your class, your logic"""
    quote = db.fetch_quote()
    return jsonify(quote)


# ── LOG SESSION ───────────────────────────────────────────────────────────────
@app.route('/api/log', methods=['POST'])
def log_session():
    """
    Mirrors log_streak.login.log_session() and login.streak().
    Instead of input(), takes JSON body from frontend.
    """
    body = request.json
    hours    = body.get('hours_coded')
    work     = body.get('work', '').strip()
    outcome  = body.get('learning_outcome', '').strip()
    log_date = body.get('date', datetime.now().strftime('%Y-%m-%d'))

    if not hours or not work or not outcome:
        return jsonify({'error': 'hours_coded, work, and learning_outcome are required'}), 400
    if not (1 <= int(hours) <= 24):
        return jsonify({'error': 'hours must be between 1 and 24'}), 400

    data = ud.load_data()

    # Replicate log_session logic (same fields your class appends)
    data['daily_data']['date'].append(log_date)
    data['daily_data']['time'].append(datetime.now().strftime('%H:%M:%S'))
    data['daily_data']['hours_coded'].append(int(hours))
    data['daily_data']['work'].append(work)
    data['daily_data']['learning_outcome'].append(outcome)

    # Replicate streak logic from login.streak()
    today_date = datetime.now().date()
    streak = data['default_data']['streak']
    if not streak['last_logged']:
        streak['current'] = 1
        streak['longest'] = 1
        streak['last_logged'] = today_date.strftime('%Y-%m-%d')
    else:
        prev = datetime.strptime(streak['last_logged'], '%Y-%m-%d').date()
        diff = abs((today_date - prev).days)
        if diff == 0:
            pass  # already logged today
        elif diff == 1:
            streak['current'] += 1
        else:
            streak['current'] = 1
        if streak['current'] > streak['longest']:
            streak['longest'] = streak['current']
        streak['last_logged'] = today_date.strftime('%Y-%m-%d')

    ud.save_data(data)
    return jsonify({'success': True, 'streak': safe_json(streak)})


# ── PROJECTS ──────────────────────────────────────────────────────────────────
@app.route('/api/projects', methods=['GET'])
def get_projects():
    data = ud.load_data()
    return jsonify(safe_json(data.get('project', {})))


@app.route('/api/projects', methods=['POST'])
def add_project():
    """Mirrors ManageProjects.add_project() — same fields, same logic"""
    body = request.json
    data = ud.load_data()

    prev_id = int(data['project_id']) if data['project_id'] else 0
    new_id  = str(prev_id + 1)

    # Same fields your add_project() builds
    data['project'][new_id] = {
        'name':           body.get('name', '').strip(),
        'description':    body.get('description', '').strip(),
        'tech_stack':     body.get('tech_stack', []),
        'status':         body.get('status', 'active'),
        'github_url':     body.get('github_url', '').strip(),
        'date_started':   body.get('date_started', ''),
        'last_worked':    body.get('last_worked', ''),
        'completed_date': body.get('completed_date', '')
    }
    data['project_id'] = new_id

    ud.save_data(data)
    return jsonify({'success': True, 'project_id': new_id})


@app.route('/api/projects/<pid>', methods=['PUT'])
def update_project(pid):
    """Mirrors ManageProjects.update_project()"""
    body = request.json
    data = ud.load_data()

    if pid not in data['project']:
        return jsonify({'error': 'Project not found'}), 404

    proj = data['project'][pid]
    # Update only the fields sent (same fields from your class)
    for field in ['name', 'description', 'tech_stack', 'status', 'github_url', 'date_started', 'last_worked', 'completed_date']:
        if field in body:
            proj[field] = body[field]

    ud.save_data(data)
    return jsonify({'success': True})


@app.route('/api/projects/<pid>', methods=['DELETE'])
def delete_project(pid):
    """Mirrors ManageProjects.delete_project()"""
    data = ud.load_data()
    if pid not in data['project']:
        return jsonify({'error': 'Project not found'}), 404
    del data['project'][pid]
    ud.save_data(data)
    return jsonify({'success': True})


# ── GOALS ─────────────────────────────────────────────────────────────────────
@app.route('/api/goals', methods=['GET'])
def get_goals():
    data = ud.load_data()
    # Use GoalsTracker.view_goals() logic to add message field
    goals = data.get('goals', {})
    today_date = datetime.now().date()
    for gid, details in goals.items():
        deadline_obj = datetime.strptime(details['deadline'], '%Y-%m-%d').date()
        diff = (deadline_obj - today_date).days
        if details['status'] == 'completed':
            details['message'] = 'completed'
        elif diff < 0:
            details['message'] = f'overdue by {abs(diff)} days'
        elif diff == 0:
            details['message'] = 'due today'
        else:
            details['message'] = f'{diff} days left'
    return jsonify(safe_json(goals))


@app.route('/api/goals', methods=['POST'])
def add_goal():
    """Mirrors GoalsTracker.add_goals()"""
    body = request.json
    data = ud.load_data()

    prev_id = int(data.get('goal_id', 0))
    new_id  = str(prev_id + 1)

    # Same fields your add_goals() creates
    data['goals'][new_id] = {
        'goal':      body.get('goal', '').strip(),
        'deadline':  body.get('deadline', ''),
        'status':    'pending',
        'created':   datetime.now().date().strftime('%Y-%m-%d'),
        'completed': '',
        'message':   ''
    }
    data['goal_id'] = int(new_id)

    ud.save_data(data)
    return jsonify({'success': True, 'goal_id': new_id})


@app.route('/api/goals/<gid>/complete', methods=['POST'])
def complete_goal(gid):
    """Mirrors GoalsTracker.complete_goals()"""
    data = ud.load_data()
    if gid not in data['goals']:
        return jsonify({'error': 'Goal not found'}), 404
    if data['goals'][gid]['status'] == 'completed':
        return jsonify({'error': 'Already completed'}), 400
    data['goals'][gid]['status'] = 'completed'
    data['goals'][gid]['completed'] = datetime.now().date().strftime('%Y-%m-%d')
    ud.save_data(data)
    return jsonify({'success': True})


@app.route('/api/goals/<gid>', methods=['DELETE'])
def delete_goal(gid):
    """Mirrors GoalsTracker.delete_goals()"""
    data = ud.load_data()
    if gid not in data['goals']:
        return jsonify({'error': 'Goal not found'}), 404
    del data['goals'][gid]
    ud.save_data(data)
    return jsonify({'success': True})


# ── SKILLS ────────────────────────────────────────────────────────────────────
@app.route('/api/skills', methods=['GET'])
def get_skills():
    data = ud.load_data()
    return jsonify(safe_json(data.get('skills', {})))


@app.route('/api/skills', methods=['POST'])
def add_skill():
    """Mirrors SkillProgress.add_skill()"""
    body = request.json
    skill_name = body.get('skill_name', '').strip()
    data = ud.load_data()
    if skill_name in data['skills']:
        return jsonify({'error': 'Skill already registered'}), 400
    data['skills'][skill_name] = []
    ud.save_data(data)
    return jsonify({'success': True})


@app.route('/api/skills/<skill>/topics', methods=['POST'])
def log_topic(skill):
    """Mirrors SkillProgress.log_skill_learning()"""
    body = request.json
    topic = body.get('topic', '').strip()
    data = ud.load_data()
    if skill not in data['skills']:
        return jsonify({'error': 'Skill not found'}), 404
    if topic in data['skills'][skill]:
        return jsonify({'error': 'Topic already logged'}), 400
    data['skills'][skill].append(topic)
    ud.save_data(data)
    return jsonify({'success': True})


@app.route('/api/skills/<skill>', methods=['DELETE'])
def delete_skill(skill):
    """Mirrors SkillProgress.remove_skill() — entire skill"""
    data = ud.load_data()
    if skill not in data['skills']:
        return jsonify({'error': 'Skill not found'}), 404
    del data['skills'][skill]
    ud.save_data(data)
    return jsonify({'success': True})


@app.route('/api/skills/<skill>/topics/<topic>', methods=['DELETE'])
def delete_topic(skill, topic):
    """Mirrors SkillProgress.remove_skill() — subskill only"""
    data = ud.load_data()
    if skill not in data['skills']:
        return jsonify({'error': 'Skill not found'}), 404
    if topic not in data['skills'][skill]:
        return jsonify({'error': 'Topic not found'}), 404
    data['skills'][skill].remove(topic)
    ud.save_data(data)
    return jsonify({'success': True})


# ── GITHUB ────────────────────────────────────────────────────────────────────
@app.route('/api/github', methods=['GET'])
def get_github():
    data = ud.load_data()
    return jsonify(safe_json(data.get('github', {})))


@app.route('/api/github/fetch', methods=['POST'])
def fetch_github():
    """Calls GithubStats.get_github_stats() — your class does the requests"""
    body = request.json
    username = body.get('username', '').strip()
    data = ud.load_data()

    if username:
        data['github']['username'] = username

    # Call YOUR class method directly
    gh.get_github_stats(data)

    ud.save_data(data)
    return jsonify(safe_json(data.get('github', {})))


# ── WEEKLY REPORT ─────────────────────────────────────────────────────────────
@app.route('/api/report', methods=['GET'])
def get_report():
    """Calls WeeklyReport.generate_report() — your class, unchanged"""
    data = ud.load_data()
    report = wr.generate_report(data)

    if not report:
        return jsonify({'no_data': True})

    # Convert DataFrame to list of dicts for JSON
    df = report['this_week_df']
    breakdown = df[['date', 'hours_coded', 'work', 'learning_outcome']].copy()
    breakdown['date'] = breakdown['date'].astype(str)
    report_json = {
        'total_hours':     report['total_hours'],
        'most_productive': str(report['most_productive']),
        'streak':          report['streak'],
        'goals_completed': report['goals_completed'],
        'total_goals':     report['total_goals'],
        'monday':          str(report['monday']),
        'today':           str(report['today']),
        'breakdown':       breakdown.to_dict(orient='records')
    }
    return jsonify(report_json)


@app.route('/api/report/save', methods=['POST'])
def save_report():
    """Mirrors WeeklyReport's save-to-JSON logic"""
    data = ud.load_data()
    report = wr.generate_report(data)
    if not report:
        return jsonify({'error': 'No data this week'}), 400

    import json, os
    report_save = {
        'week':            str(report['monday']),
        'total_hours':     report['total_hours'],
        'streak':          report['streak'],
        'goals_completed': report['goals_completed'],
        'generated_at':    datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    with open('weekly_report.json', 'w') as f:
        json.dump(report_save, f, indent=4)
    return jsonify({'success': True, 'report': report_save})


if __name__ == '__main__':
    app.run(debug=True, port=5000)
