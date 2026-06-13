import os
import json
from datetime import date, datetime

FILENAME="devtrack_data.json"
class UpdateData():
    def load_data(self):
        if os.path.exists(FILENAME):
            with open(FILENAME,'r')as file:
                try:
                    return json.load(file)
                except json.JSONDecodeError:
                    return{}
        return{}
    

    def save_data(self, data):
        with open(FILENAME, 'w') as file:
            try:    
                # The 'default' parameter converts date objects to strings on the fly
                json.dump(
                    data, 
                    file, 
                    indent=4, 
                    default=lambda obj: obj.strftime('%Y-%m-%d') if isinstance(obj, (date, datetime)) else str(obj)
                )
                print("Data saved successfully!")
            except Exception as e:
                print(f"file couldn't be saved: {e}")
            
                    
                        
            