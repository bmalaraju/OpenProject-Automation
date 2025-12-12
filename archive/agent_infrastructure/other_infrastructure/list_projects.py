from wpr_agent.clients.openproject_client import OpenProjectClient
import os
from dotenv import load_dotenv

load_dotenv()

def list_projects():
    client = OpenProjectClient()
    try:
        projects = client.list_projects()
        print(f"Found {len(projects)} projects:")
        for p in projects:
            name = p.get("name")
            identifier = p.get("identifier")
            print(f"- {name} (Key: {identifier})")
    except Exception as e:
        print(f"Error listing projects: {e}")

if __name__ == "__main__":
    list_projects()
