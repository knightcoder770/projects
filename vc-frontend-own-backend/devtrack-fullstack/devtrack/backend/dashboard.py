import requests

class dashboard():
    
    def fetch_quote(self)      :
        try:
            request = requests.get('https://programming-quotesapi.vercel.app/api/random  ', timeout=5)
            if request.status_code == 200:
                data_quote = request.json()
                return data_quote
            else:
                return {'author': 'Unknown', 'quote': 'api request failed.'}
        except requests.exceptions.RequestException:
            return {'author': 'Unknown', 'quote': 'could not connect to server.'}
        
    def show_dashboard(self,data_quote):
        print("-"*112)
        print(" "*50+"DEVTRACK V01"+" "*50)
        print("-"*112)
        print("*"*48+"QUOTE OF THE DAY"+"*"*48)
        print(f"Author-{data_quote.get('author')}")
        print(f"{data_quote.get('quote')}")
        print("1 — Log Today's Session")
        print("2 — Manage Projects")
        print("3 — Goal Tracker")
        print("4 — Skill Progress")
        print("5 — GitHub Stats")
        print("6 — Weekly Report")
        print("7 — Exit")
        