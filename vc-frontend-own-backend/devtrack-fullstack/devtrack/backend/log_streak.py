from datetime import datetime

class login():
    
    def log_session(self,data):
        self.project_today=input("what project did you work on today? : ").strip()
        while True:
            try:
                self.code_time=int(input("how many hours you coded today? : ").strip())
                round(self.code_time)
                if self.code_time in range(1,25):
                    break
                else:
                    print("type the no of hours you spent in coding today as a integer")
                    continue
            except ValueError:
                print("you must type no of hours in integer format")
                continue
        self.work=input("what did you build or work on? : ").strip()
        self.outcome=input("what did you learn today").strip()
        self.date=datetime.now()
        data['daily_data']['date'].append(self.date.strftime("%Y-%m-%d"))
        data['daily_data']['time'].append(self.date.strftime("%H:%M:%S"))
        data['daily_data']['hours_coded'].append(self.code_time)
        data['daily_data']['work'].append(self.work)
        data['daily_data']['learning_outcome'].append(self.outcome)
        return data
    
    def streak(self,data):
        self.date=datetime.now().date()
        if not data['default_data']['streak']['last_logged']:
            data['default_data']['streak']['last_logged']=self.date.strftime("%Y-%m-%d")
            data['default_data']['streak']['current'] = 1
            data['default_data']['streak']['longest'] = 1
        self.previous_date=datetime.strptime(data['default_data']['streak']['last_logged'],"%Y-%m-%d").date()
        self.check=abs((self.date-self.previous_date).days)
        
        if self.check == 0:
            print("already logged today 🔥 streak continues")
            return data 
    
        if self.check ==1:
            data['default_data']['streak']['current']+=1
            
        elif self.check >1:
            data['default_data']['streak']['current']=0
            
        if data['default_data']['streak']['current']>data['default_data']['streak']['longest']:
            data['default_data']['streak']['longest']=data['default_data']['streak']['current']
            
        
        
       
            
        
        
        