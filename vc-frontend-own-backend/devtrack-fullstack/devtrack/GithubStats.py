import requests
from datetime import datetime

class GithubStats():
    
    def github_dashboard(self,data):
        profile = data['github'].get('profile')
        repos = data['github'].get('repos', [])
        
        if not profile:
            print("No profile data found. Please run get_github_stats first.")
            return

        try:
            joined_date = datetime.strptime(profile['joined date'], "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%D")
        except Exception:
            joined_date = profile['joined date'][:10] 

        print("════════════════════════════════════════")
        print("         🐙 GITHUB STATS")
        print("════════════════════════════════════════")
        print(f"Username    : {profile['username']}")
        print(f"Name        : {profile['fullname'] or 'N/A'}")
        print(f"Followers   : {profile['followers']}")
        print(f"Following   : {profile['following']}")
        print(f"Public Repos: {profile['repo_count']}")
        print(f"Joined      : {joined_date}")
        print("════════════════════════════════════════")

        print("📁 YOUR REPOSITORIES")
        print("————————————————————————————————————————")
        
        if not repos:
            print(" No public repositories found.")
        else:
            for index, repo in enumerate(repos, 1):
               
                name = repo['repo_name']
                stars = f"⭐ {repo['star_count']}"
                lang = repo['language_used'] or "None"
                print(f"{index}. {name:<20} {stars:<6} {lang}")
                
        print("————————————————————————————————————————")
    
    def get_github_stats(self,data):
        
        if 'github' not in data:
            data['github'] = {}
            
        username = data['github'].get('username')
        if not username:
            username = input("enter your github user name : ")
            data['github']['username'] = username
        
        self.profile = requests.get(f"https://api.github.com/users/{username}")
        if self.profile.status_code == 200:
            github_data = self.profile.json()
            data['github']['profile'] = {
                "username": github_data['login'],
                "fullname": github_data['name'],
                "followers": github_data['followers'],
                "following": github_data['following'],
                "repo_count": github_data['public_repos'],
                "joined date": github_data['created_at']
            }
        else:
            print("error in receiving api profile request status ...try again later")
            return
        
        self.repos = requests.get(f"https://api.github.com/users/{username}/repos")
        if self.repos.status_code == 200:
            repo_data = self.repos.json()
            
            repo_data = sorted(repo_data, key=lambda x: x.get("updated_at", ""), reverse=True)
            
            data['github']['repos'] = []
            for repo in repo_data:
                data['github']['repos'].append({
                    "repo_name": repo["name"],
                    "star_count": repo["stargazers_count"],
                    "language_used": repo["language"],
                    "last_updated": repo["updated_at"]
                })
        else:
            print("error in receiving api repo request status ...try again later")
            