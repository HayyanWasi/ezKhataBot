import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv('API_URL')
API_KEY = os.getenv("API_KEY")
INSTANCE = os.getenv('INSTANCE')

def check_status():
    try:
        response = requests.get(
            f"{API_URL}/instance/connectionState/{INSTANCE}",
            headers={"apikey": API_KEY}, timeout=5)
        data = response.json()
        return data.get("instance", {}).get("state", "unknown")
    except Exception as e:
        return f"error {e}"

def generate_pairing_code():
    print("=" * 60)
    print("  exKhataBot - Generate Pairing Code")
    print("=" * 60)
    print(f"\nInstance Name: {INSTANCE}")

    state = check_status()
    print(f"Current Connection State: {state}")

    if state == "open":
        print("\n🎉 WhatsApp is ALREADY CONNECTED!")
        return

    # To generate a pairing code for the instance
    # Evolution API uses GET /instance/connect/{instance} with a body or query param
    # Alternatively, you can use the manager to get a pairing code.
    
    number = input("Enter your WhatsApp number with country code (e.g., 923172783460): ").strip()
    
    try:
        url = f"{API_URL}/instance/connect/{INSTANCE}"
        payload = {
            "number": number
        }
        headers = {
            "apikey": API_KEY,
            "Content-Type": "application/json"
        }
        print("\nGenerating pairing code...")
        response = requests.get(url, params=payload, headers=headers, timeout=10)
        
        # In Evolution API v2, pairing code is returned in the response
        if response.status_code == 200:
            data = response.json()
            code = data.get("pairingCode", "NOT FOUND")
            if code and code != "NOT FOUND":
                print("\n==========================================")
                print(f"🚀 PAIRING CODE: {code}")
                print("==========================================")
                print("Open WhatsApp -> Linked Devices -> Link with Phone Number Instead")
                print("Enter this code to connect.")
            else:
                print(f"\nNo pairing code returned. Response: {data}")
        else:
            print(f"Failed! Status Code: {response.status_code}, Response: {response.text}")
            
    except Exception as e:
        print(f"Error occurred: {e}")

if __name__ == "__main__":
    generate_pairing_code()
