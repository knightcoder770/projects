from update_data import UpdateData
from dashboard import dashboard
from log_streak import login
from ManageProjects import ManageProjects
from GoalsTracker import GoalsTracker
from SkillsProgress import SkillProgress
from GithubStats import GithubStats
from WeeklyReport import WeeklyReport

def main():
    data = UpdateData().load_data()
    db   = dashboard()
    lg   = login()
    mp   = ManageProjects()
    gt   = GoalsTracker()
    sp   = SkillProgress()
    gh   = GithubStats()
    ud   = UpdateData()
    wr   = WeeklyReport()
    while True:
        quote = db.fetch_quote()
        db.show_dashboard(quote)

        while True:
            try:
                option = int(input("choose from above options: "))
                if option in range(1, 8):
                    break
                print("type only number [1-7]")
            except ValueError:
                print("enter only numbers")

        if option == 1:
            lg.log_session(data)
            ud.save_data(data)
            
        elif option == 2:
            while True:
                mp.manage_projects_dashboard()
                opt = mp.get_option()
                if opt == 1: 
                    mp.view_projects(data)
                elif opt == 2: 
                    mp.add_project(data)
                elif opt == 3: 
                    mp.update_project(data)
                elif opt == 4: 
                    mp.delete_project(data)
                else: break
            ud.save_data(data)

        elif option == 3:
            while True:
                gt.goal_dashboard()
                opt = gt.get_option()
                if opt == 1: 
                    gt.view_goals(data)
                elif opt == 2: 
                    gt.add_goals(data)
                elif opt == 3: 
                    gt.complete_goals(data)
                elif opt == 4: 
                    gt.delete_goals(data)
                else: break
            ud.save_data(data)

        elif option == 4:
            while True:
                sp.skill_dashboard()
                opt = sp.get_option()
                if opt == 1: 
                    sp.view_skill(data)
                elif opt == 2: 
                    sp.log_skill_learning(data)
                elif opt == 3: 
                    sp.add_skill(data)
                elif opt == 4: 
                    sp.remove_skill(data)
                else: break
            ud.save_data(data)

        elif option == 5:
            gh.get_github_stats(data)
            gh.github_dashboard(data)
            ud.save_data(data)

        elif option == 6:
            wr.generate_report(data)
            wr.display_report(data)
            ud.save_data(data)
            
        elif option == 7:
            print("goodbye! keep coding ")
            ud.save_data(data)
            break

if __name__=="__main__":
    main()   