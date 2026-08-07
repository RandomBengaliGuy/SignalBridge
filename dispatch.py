import httpx
from bot_client import client, EMAIL_CONNECTION_ID
from database import load_users, save_users

def dispatch_emergency(user_id_str, sender_name, nature, severity, location_text, lat, lon, raw_context):
    users_data = load_users()
    user_info = users_data.get(user_id_str)
    if not user_info:
        return
        
    maps_link = f"https://www.google.com/maps?q={lat},{lon}" if lat != 0.0 else "Not available"
    alert_message = (
        f"🚨 EMERGENCY ALERT 🚨\n"
        f"⚠️ {sender_name} is in distress! ⚠️\n"
        f"Nature: {nature}\n"
        f"Severity: {severity}\n"
        f"Location: {location_text}\n"
        f"Coordinates: {lat}, {lon}\n"
        f"Maps: {maps_link}\n"
        f"Raw message: {raw_context.strip()}"
    )
    
    if user_info.get("family_groups"):
        for group_id in user_info["family_groups"]:
            try:
                client.send_message(group_id, alert_message)
            except Exception as e:
                print(f"Failed to notify family group {group_id}: {e}")
                
    email_subject = f"URGENT: Emergency Alert for {sender_name}!"
    email_body = f"Subject: {email_subject}\n\n{alert_message}"
    if user_info.get("family_emails") and EMAIL_CONNECTION_ID:
        for email in user_info["family_emails"]:
            try:
                client.initiate(EMAIL_CONNECTION_ID, recipient=email, text=email_body)
            except Exception as e:
                print(f"Failed to notify family email {email}: {e}")
                
    try:
        payload = {
            "user_id": user_id_str,
            "nature_of_emergency": nature,
            "severity": severity,
            "latitude": lat,
            "longitude": lon,
            "location_text": location_text,
            "raw_transcript": raw_context.strip()
        }
        httpx.post("http://localhost:8000/api/dispatch", json=payload)
    except Exception as e:
        print(f"Failed to notify dispatch: {e}")

def auto_dispatch_timeout(user_id_str, channel_id, sender_name):
    users_data = load_users()
    user_info = users_data.get(user_id_str)
    if user_info and "pending_emergency" in user_info:
        pending = user_info["pending_emergency"]
        client.send_message(channel_id, "⚠️ 15 seconds elapsed! Auto-dispatching emergency with Unknown Location.")
        
        dispatch_emergency(
            user_id_str, sender_name,
            pending["nature"], pending["severity"], "Unknown", 0.0, 0.0, pending["raw_context"]
        )
        
        del user_info["pending_emergency"]
        save_users(users_data)
