from caspian_sdk import CommClient
import os

client = CommClient()

try:
    email_conn = client.connect_email(username="signalbridge-team-alpha")
    EMAIL_CONNECTION_ID = email_conn["id"]
except Exception as e:
    print(f"Failed to connect email: {e}")
    EMAIL_CONNECTION_ID = None

try:
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if telegram_token:
        client.connect_telegram(bot_token=telegram_token)
        print("[SUCCESS] Successfully connected to custom Telegram bot!")
except Exception as e:
    print(f"Failed to connect custom Telegram bot: {e}")

try:
    slack_info = client.install_slack(display_name="SignalBridge Dispatch")
    if "authorize_url" in slack_info:
        print(f"[LINK] CLICK HERE TO INSTALL SLACK: {slack_info['authorize_url']}")
    else:
        print("[SUCCESS] Slack is already active on this Caspian account!")
except Exception as e:
    print(f"Failed to connect Slack via SDK: {e}")

try:
    discord_info = client.install_discord(display_name="SignalBridge Relay")
    if "authorize_url" in discord_info:
        print(f"[LINK] CLICK HERE TO INSTALL DISCORD: {discord_info['authorize_url']}")
    else:
        print("[SUCCESS] Discord is already active on this Caspian account!")
except Exception as e:
    print(f"Failed to connect Discord via SDK: {e}")

try:
    twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
    twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
    twilio_number = os.getenv("TWILIO_PHONE_NUMBER")
    
    if twilio_sid and twilio_token and twilio_number:
        phone_conn = client.connect_phone(provider="twilio", account_sid=twilio_sid, auth_token=twilio_token, from_number=twilio_number)
        PHONE_CONNECTION_ID = phone_conn["id"]
        print("[SUCCESS] Twilio SMS Gateway Initialized for live texting.")
    else:
        PHONE_CONNECTION_ID = "mock_sms_gateway_123"
        print("[INFO] No Twilio credentials found. Using Dummy SMS Gateway for local testing.")
except Exception as e:
    print(f"Failed to connect phone for SMS: {e}")
    PHONE_CONNECTION_ID = "mock_sms_gateway_123"
    print("[INFO] Falling back to Dummy SMS Gateway.")

DUMMY_USER_TELEGRAM_ID = os.getenv("DUMMY_USER_TELEGRAM_ID", "default_telegram_id")
