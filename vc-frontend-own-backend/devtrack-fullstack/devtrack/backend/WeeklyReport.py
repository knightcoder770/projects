import pandas as pd
import json
import os
from datetime import datetime, timedelta

class WeeklyReport():

    def generate_report(self, data):
        today = datetime.now().date()
        monday = today - timedelta(days=today.weekday())

        if not data['daily_data']['date']:
            return None

        df = pd.DataFrame(data['daily_data'])
        df['date'] = pd.to_datetime(df['date']).dt.date

        this_week = df[df['date'] >= monday]

        if this_week.empty:
            return None

        total_hours = this_week['hours_coded'].sum()
        most_productive = this_week.loc[
            this_week['hours_coded'].idxmax(), 'date'
        ]

        completed_goals = [
            g for g in data['goals'].values()
            if g['status'] == 'completed' and
            g['completed'] and
            datetime.strptime(g['completed'], "%Y-%m-%d").date() >= monday
        ]
        total_goals = len(data['goals'])

        return {
            "total_hours"      : int(total_hours),
            "most_productive"  : str(most_productive),
            "streak"           : data['default_data']['streak']['current'],
            "goals_completed"  : len(completed_goals),
            "total_goals"      : total_goals,
            "this_week_df"     : this_week,
            "monday"           : monday,
            "today"            : today
        }

    def display_report(self, data):
        report = self.generate_report(data)

        if not report:
            print("\n📭 No sessions logged this week yet.")
            return

        print("\n" + "═"*45)
        print("         📊 WEEKLY REPORT")
        print(f"   Week of {report['monday']} to {report['today']}")
        print("═"*45)
        print(f"⏱️  Total hours coded    : {report['total_hours']}")
        print(f"📅 Most productive day  : {report['most_productive']}")
        print(f"🔥 Current streak       : {report['streak']} days")
        print(f"✅ Goals completed      : {report['goals_completed']}/{report['total_goals']}")
        print("═"*45)

        print("\n📈 DAILY BREAKDOWN")
        print("—"*45)
        df_display = report['this_week_df'][['date','hours_coded','work']].copy()
        df_display.columns = ['Date', 'Hours', 'Work']
        print(df_display.to_string(index=False))
        print("—"*45)

        if data['skills']:
            print("\n🧠 SKILLS BEING TRACKED")
            print("—"*45)
            for skill, topics in data['skills'].items():
                topic_count = len(topics)
                print(f"{skill:<20} → {topic_count} topics logged")
            print("—"*45)

        save = input("\nsave this report? [Y/N]: ").upper().strip()
        if save == 'Y':
            report_save = {
                "week"           : str(report['monday']),
                "total_hours"    : report['total_hours'],
                "streak"         : report['streak'],
                "goals_completed": report['goals_completed'],
                "generated_at"   : datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            with open("weekly_report.json", "w") as f:
                json.dump(report_save, f, indent=4)
            print("✅ Report saved to weekly_report.json")