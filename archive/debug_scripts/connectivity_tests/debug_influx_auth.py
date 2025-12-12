
import requests
import os
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("INFLUX_URL")
token = os.getenv("INFLUX_TOKEN")
bucket = "wpr-state"

print(f"Testing URL: {url}")
print(f"Token: {token[:5]}...")

base_ip = "http://212.2.245.85"
ports = [8181, 8182, 8086]

for port in ports:
    print(f"\n=== Testing Port {port} ===")
    url = f"{base_ip}:{port}"
    
    # Test Bearer (most likely for v3)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    try:
        api_url = f"{url}/api/v2/buckets?org=infinite"
        print(f"GET {api_url}")
        r = requests.get(api_url, headers=headers, timeout=3)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            print("SUCCESS!")
            print(r.text[:200])
            break
    except Exception as e:
        print(f"Error: {e}")
