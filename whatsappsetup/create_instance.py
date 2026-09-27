import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv('API_URL')
API_KEY = os.getenv("API_KEY")
INSTANCE = os.getenv('INSTANCE')
INSTANCE_TOKEN = os.getenv('INSTANCE_TOKEN')

def create_instance():
    print(f"Creating instance: {INSTANCE}")
    headers = {
        "apikey": API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "instanceName": INSTANCE,
        "qrcode": True,
        "integration": "WHATSAPP-BAILEYS"
    }
    # Optional instance auth token; Evolution generates one if not set
    if INSTANCE_TOKEN:
        payload["token"] = INSTANCE_TOKEN
    try:
        res = requests.post(f"{API_URL}/instance/create", json=payload, headers=headers)
        if res.status_code in [200, 201]:
            print("Instance created!")
        else:
            print(f"Error creating instance: {res.text}")
    except Exception as e:
        print(f"Failed to create: {e}")

if __name__ == "__main__":
    create_instance()
