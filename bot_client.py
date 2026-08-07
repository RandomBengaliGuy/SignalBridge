from caspian_sdk import CommClient
import os

client = CommClient()

try:
    email_conn = client.connect_email(username="signalbridge")
    EMAIL_CONNECTION_ID = email_conn["id"]
except Exception as e:
    print(f"Failed to connect email: {e}")
    EMAIL_CONNECTION_ID = None

DUMMY_USER_TELEGRAM_ID = os.getenv("DUMMY_USER_TELEGRAM_ID", "default_telegram_id")
