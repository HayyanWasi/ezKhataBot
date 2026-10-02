"""
Helper script to connect WhatsApp with Evolution API.
Opens the Evolution API Manager in your browser and monitors the connection state.
"""

from socket import timeout
import os
import time
import webbrowser
from dotenv import load_dotenv
import requests
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

def main():
    print("=" * 60)
    print("  EzKhata - Connect WhatsApp")
    print("=" * 60)
    print(f"\nInstance Name: {INSTANCE}")

    state = check_status()
    print(f"Current Connection State: {state}")

    if state == "open":
        print("\n🎉 WhatsApp is ALREADY CONNECTED!")
        return

    manager_url = f"{API_URL}/manager"
    print(f"\nOpening Evolution API Manager in your browser:")
    print(f"  --> {manager_url}")
    print("\nHow to scan the QR code:")
    print("  1. In the Manager webpage, log in with:")
    print("     - the Global API Key (API_KEY in .env)")
    print("  2. Click on the 'ezkhata' instance.")
    print("  3. Click 'Connect' / QR code button to display the QR code.")
    print("  4. Open WhatsApp on your phone -> Settings -> Linked Devices -> Link a Device.")
    print("  5. Scan the QR code.\n")

    webbrowser.open(manager_url)

    print("Monitoring connection state (press Ctrl+C to stop)...")
    for _ in range(60):
        time.sleep(3)
        current = check_status()
        if current == "open":
            print("\n🎉 SUCCESS! WhatsApp connected successfully!")
            break
        elif current != state:
            print(f"  State changed to: {current}")
            state = current

if __name__ == "__main__":
    main()
