from datetime import datetime
import pandas as pd

class GoalsTracker():
    
    def goal_dashboard(self):
        print('*'*100)
        print(" "*42+'🏋️‍♀️ GOAL TRACKER'+'*'*42)
        print('*'*100)
        print("1- VIEW ALL GOALS")
        print("2- ADD NEW GOAL")
        print("3- COMPLETE GOAL")
        print("4- DELETE GOAL")
        print("5-BACK")
        
    def get_option(self):
        while True:
            try:
                self.option=int(input("enter the option number you want to perform : ").strip())
                if self.option in range(1,6):
                    return self.option
                    
                else:
                    print("enter only the option number [1-4]you want to perform")
                    continue
            except ValueError:
                print("enter only number in range [1-4] based on what you want to perform")
                continue
            
    def add_goals(self,data):
        self.prev_id=data['goal_id']
        self.id=self.prev_id+1
        self.goal_id=str(self.id)
        self.goal=input("what is your goal ? : ").strip()
        self.deadline_input = input("enter the deadline date in [YYYY-MM-DD] format : ").strip()
        try:
            self.check_deadline = datetime.strptime(self.deadline_input, '%Y-%m-%d')
            self.deadline = self.check_deadline.strftime('%Y-%m-%d') 
        except ValueError:
            print("Invalid date format! Please use YYYY-MM-DD.")
        self.status="pending"
        self.created=datetime.now().date()
        self.completed="'"
        data['goals'][self.goal_id] = {
            "goal":self.goal,
            "deadline":self.deadline,
            "status":self.status,
            "created":self.created,
            "completed":self.completed
        }
        print(f"goal added sucessfully and goal ID is : {self.goal_id}")
        data['goal_id']=self.id
        
    def view_goals(self,data):
        if not  data['goals']:
            print("there is no goals..... create one....")
            return
        
        else:
            for goal_id,details in data['goals'].items():
                deadline_obj = datetime.strptime(details['deadline'], '%Y-%m-%d').date()
                self.today = datetime.now().date()
                diff = (deadline_obj - self.today).days
                
                if details['status'] == "completed":
                    self.message='✅completed'
                    
                elif diff<0:
                    self.message=f"overdue by {abs(diff)} days"
                    
                elif diff == 0:
                    self.message = "⚠️ due today"
                    
                else:
                    self.message=f"🕛 {diff} day left"
                
                details['message']=self.message
                
                df = pd.DataFrame.from_dict( data['goals'],orient='index')
                print(df)
                    
    def complete_goals(self, data):
        if not data['goals']:
            print("There are no goals to complete.")
            return

        goal_id = input("Enter the goal ID of the goal you want to mark complete: ").strip()
        
        if goal_id in data['goals']:
            if data['goals'][goal_id]['status'] == "pending":
                data['goals'][goal_id]['status'] = "completed"
                data['goals'][goal_id]['completed'] = datetime.now().date().strftime('%Y-%m-%d')
                print(f"🎉 Goal {goal_id} marked as completed successfully!")
            else:
                print("This goal is already completed!")
        else:
            print("Goal ID not found... try again.")

    def delete_goals(self, data):
        if not data['goals']:
            print("There are no goals to delete.")
            return
        goal_id = input("Enter the goal ID of the goal you want to delete: ").strip()
        
        if goal_id in data['goals']:
            confirmation = input(f"Are you sure you want to delete goal {goal_id}? [y/n] : ").strip().lower()
            if confirmation == 'y':
                del data['goals'][goal_id]              
                print("Goal deleted successfully.")
            else:
                print("Deletion cancelled.")
        else:
            print("Goal ID not found.")
   