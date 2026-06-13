import pandas as pd
class SkillProgress():
    def skill_dashboard(self):
        print('*'*100)
        print(" "*42+'📈 SKILL PROGRESS'+'*'*42)
        print('*'*100)
        print("1 — VIEW ALL SKILLS")
        print("2 — LOG SKILL LEARNING")
        print("3 — ADD NEW SKILL")
        print("4 — REMOVE SKILL")
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
            
    def add_skill(self,data):
        self.skill_name=input("enter new skill name : ").strip()
        if self.skill_name in data['skills']:
            print("skill is already registered")
            return
        else:
            data['skills'][self.skill_name]=[]
            print("skill added sucessfully")
            
    def log_skill_learning(self,data):
        self.view_skill(data)
        self.skill=input("what skill did you learn today : ").strip()
        if self.skill in data['skills']:
            self.topic=input("what sub skill did you learn in it ? : ").strip()
            if self.topic in data['skills'][self.skill]:
                print("you already registered thi sub skill")
                return
            else:
                data['skills'][self.skill].append(self.topic)
                return
        else:
            print("you still haven't added this skill.... add one and come again")
            
    def view_skill(self, data):
        if not data['skills']:
            print("\n[!] No skills added yet.")
            return
        index_data = []
        for skill, subskills in data['skills'].items():
            if not subskills:
                index_data.append((skill, "No progress logged"))
            else:
                for sub in subskills:
                    index_data.append((skill, sub))

        index = pd.MultiIndex.from_tuples(index_data, names=['SKILL', 'LEARNED TOPICS'])
        df = pd.Series(index=index, dtype=float).fillna('') 
        
        print("\n" + "—"*40)
        print(df.to_string())
        print("—"*40)
        
    def remove_skill(self,data):
        while True:    
            try:
                self.ques=int(input("do you want to delete only\n1- entire skill \n2- sub skill ").strip())
                if self.ques in range(1,3):
                    break
                else:
                    print("enter only the option number you want to perform")
                    continue
            except ValueError:
                print("enter only the option number you want to perform")
                continue
            
        if self.ques==1:
            self.del_skill=input("enter the skill name you want to delete : ").strip()
            if self.del_skill in data['skills']:
                self.confirm=input("are you sure you want to delete ? [y/n] : ").strip().lower()
                if self.confirm=='y':
                    del data['skills'][self.del_skill]
                else:
                    return
            else:
                print("skill is not available")
        elif self.ques==2:
            self.skill_name=input("under what skill you want to delete a subskill ? : ").strip()
            if self.skill_name in data['skills']:
                self.del_subskill=input("enter the subskill you want to delete : ").strip()
            else:
                print("no such skill is available")
                return
            if self.del_subskill in data['skills'][self.skill_name]:
                self.confirm=input("are you sure you want to delete ? [y/n] : ").strip().lower()
                if self.confirm=='y':
                    data['skills'][self.skill_name].remove(self.del_subskill)
                else:
                    return
            else:
                print("no such sub skill is available")   
                return
                   