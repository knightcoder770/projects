import pandas as pd

class ManageProjects():

    def manage_projects_dashboard(self):
        print('*'*100)
        print(" "*42+'📁MANAGE PROJECTS'+'*'*42)
        print('*'*100)
        print("1 — View all projects")
        print("2 — Add new project")
        print("3 — Update project status")
        print("4 — Delete project")
        print("5 — Back")
        
    def get_option(self):
        while True:
            try:
                self.option=int(input("enter the option number you want to perform : ").strip())
                if self.option in range(1,6):
                    return self.option
                    
                else:
                    print("enter only the option number [1-5]you want to perform")
                    continue
            except ValueError:
                print("enter only number in range [1-5] based on what you want to perform")
                continue
            
    def add_project(self,data,proid):
        self.prev_id=data['project_id']
        self.id=self.prev_id+1
        id=str(self.id)
        data['project'][id]={}
        self.name=input("enter the name of the project : ").strip()
        data['project'][id]['name']=self.name
        self.description=input("give a description on the project").strip()
        data['project'][id]['description']=self.description
        data['project'][id]['tech_stack']=[]
        while True:   
            try:
                self.no_of_techstack=abs(int(input("how many tech stack you used?\n(type only total no of tech stack you used) : ")))
                if self.no_of_techstack >0:
                    for i in range (0,self.no_of_techstack):
                        self.tech_stack=input("what tech stack you used? : ").strip()
                        data['project'][id]['tech_stack'].append(self.tech_stack)
                    break
                else:
                    print("type only the no of tech stack you used in this project")
                    continue
            except ValueError:
                print("enter only the no of tech stack you used")
                continue
        data['project'][id]['status']=""
        self.github_url=input("paste your github url of this project....if you haven't created one leave it blank : ").strip()
        data['project'][id]['github_url']=self.github_url
        self.date_started=input("enter the date of your project start date in (YYYY-MM-DD)format : ").strip()
        self.last_worked=input("enter the date when yo last worked in this project in (YYYY-MM-DD)format : ").strip()
        self.completed_date=input("enter the date of your project end date in (YYYY-MM-DD)format/ leave blank if still you are working : ").strip()
        data['project'][id]['date_started']=self.date_started
        data['project'][id]['last_worked']=self.last_worked
        data['project'][id]['completed_date']=self.completed_date
        print("project added sucessfully 👍")
        print(f"this project id is {id}")
        data['project_id']=id
    
    def view_projects(self,data):
        for pid, proj in data['project'].items():
            print(f"{pid} — {proj['name']} — {proj['status']}")
        self.project_id=(input("enter the project id to view the project : ").strip())
        if self.project_id in data['project']:
            project=data['project'][self.project_id]
            print(f"ID             ={self.project_id}")
            print(f"Name           ={project['name']}")
            print(f"Status         ={project['status']}")
            print(f"Stack          ={project['tech_stack']}")
            print(f"GitHub         ={project['github_url']}")
            print(f"Started        ={project['date_started']}")
            print(f"Last worked    ={project['last_worked']}")
            print(f"Completed Date ={project['completed_date']}")
            
        else:
            print("no such project id is available")
            
    def project_table(self,data):
        data_f = pd.DataFrame(data['project'].values())
        print(data_f)
        
    def update_status(self,data):
                self.project_id=input("enter the project id of the project to update the status : ").strip()
                print(F"current status of the project is : {data['project'][self.project_id]['status']}")
                print("1-ACTIVE")
                print("2-PAUSED")
                print("3-COMPLETED")
                while True:
                    try:
                        self.status_option=int(input("enter the option number based on how to change your status").strip())
                        if self.status_option in range (1,4):
                            break
                        else:
                            print("enter only the option number based on how to change your project status [1-3]")
                            continue
                    except ValueError:
                        print("enter only the option number from above based on how to change your project status [1-3]")
                        continue
                if self.status_option == 1:
                    data['project'][self.project_id]['status']='active'
                elif self.status_option ==2:
                    data['project'][self.project_id]['status']='paused'
                elif self.status_option ==3:
                    data['project'][self.project_id]['status']='completed'
                else:
                    print("status update failed.....try again")
           
    def update_project(self,data):
        self.project_id=input("enter the project id").strip()
        if self.project_id in data['project']:
            print("1-update/make changes in whole project")
            print("2-update only status")
            while True:
                try:
                    self.option=int(input("enter the option number you want to perform").strip())
                    if self.option in range (1,3):
                        break
                    else:
                        print("type only the option number you want to perform [1 or 2]")
                        continue
                except ValueError:
                    print("type only the option number you want to do [1 or 2]")
                    continue
            
            if self.option==1:
                    self.name=input("do you want to update name for the project [type 'y' or leave blank to keep same] : ").strip().lower()
                    self.status=input("do you want to updae status for the project [type 'y' or leave blank to keep same] : ").strip().lower()
                    self.stack=input("do you want to update tech stack for the project [type 'y' or leave blank to keep same] : ").strip().lower()
                    self.github=input("do you want to update github url for the project [type 'y' or leave blank to keep same] : ").strip().lower()
                    self.started=input("do you want to update start date for the project [type 'y'  or leave blank to keep same] : ").strip().lower()
                    self.last_worked=input("do you want to update last worked date for the project [type 'y' or leave blank to keep same] : ").strip().lower()
                    self.completed=input("do you want to update completed date for the project[type 'y' or leave blank to keep same] : ").strip().lower()
                    if self.name == 'y':
                        self.new_name=input("enter new name for the project : ").strip()
                        data['project'][self.project_id]['name']=self.new_name
                    if self.status == 'y':
                        self.update_status(data)
                    if self.stack == 'y':
                         while True:   
                            try:
                                self.no_of_techstack=abs(int(input("how many tech stack you used?\n(type only total no of tech stack you used) : ")))
                                if self.no_of_techstack >0:
                                    data['project'][self.project_id]['tech_stack']=[]
                                    for i in range (0,self.no_of_techstack):
                                        self.tech_stack=input("what tech stack you used? : ").strip()
                                        data['project'][self.project_id]['tech_stack'].append(self.tech_stack)
                                    break
                                else:
                                    print("type only the no of tech stack you used in this project")
                                    continue
                            except ValueError:
                                print("enter only the no of tech stack you used")
                                continue
                    if self.github == 'y':
                        self.new_github_url=input("enter new github url for the project : ").strip()
                        data['project'][self.project_id]['github_url']=self.new_github_url
                    if self.started == 'y':
                        self.date_started=input("enter the date of your project start date in (YYYY-MM-DD)format : ").strip()
                        data['project'][self.project_id]['date_started']=self.date_started
                    if self.last_worked == 'y':
                        self.last_worked=input("enter the date when you last worked in this project in (YYYY-MM-DD)format : ").strip()
                        data['project'][self.project_id]['last_worked']=self.last_worked
                    if self.completed == 'y':
                        self.completed_date=input("enter the date of your project end date in (YYYY-MM-DD)format/ leave blank if still you are working : ").strip()
                        data['project'][self.project_id]['completed_date']=self.completed_date 
            elif self.option ==2:
                self.update_status(data)    
            else:
                print("encountered some issues.....try again")
    
    def delete_project(self,data):
        self.project_id=input("enter the project id of the project you want to delete").strip()
        if self.project_id in data['project']:
            self.confirmation=input("are you sure you want to delete ? [y/n] : ").strip().lower()
            if self.confirmation == 'y':
                del data['project'][self.project_id]               
                print("project deleted sucessfully")
        else:
            print("project id not found")