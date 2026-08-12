import os
import json
import httpx
from bot_client import client, EMAIL_CONNECTION_ID
from database import SessionLocal
from models import User, Emergency, EmergencyStatus
from caspian_sdk import blocks as b

SLACK_DISPATCH_CHANNEL = os.getenv("SLACK_DISPATCH_CHANNEL", "slack_dispatch_channel")
DISCORD_VOLUNTEER_CHANNEL = os.getenv("DISCORD_VOLUNTEER_CHANNEL", "discord_volunteer_channel")

def dispatch_emergency(user_id_str, sender_name, nature, severity, location_text, lat, lon, raw_context, emergency_id=None):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id_str).first()
        if not user:
            return
            
        maps_link = f"https://www.google.com/maps?q={lat},{lon}" if lat != 0.0 else "Not available"
        alert_message = (
            f"!!! EMERGENCY ALERT !!!\n"
            f"!!! {sender_name} is in distress! !!!\n"
            f"Nature: {nature}\n"
            f"Severity: {severity}\n"
            f"Location: {location_text}\n"
            f"Coordinates: {lat}, {lon}\n"
            f"Maps: {maps_link}\n"
            f"Raw message: {raw_context.strip()}"
        )
        
        family_groups = json.loads(user.family_groups)
        if family_groups:
            for group_id in family_groups:
                try:
                    client.send_message(group_id, alert_message)
                except Exception as e:
                    print(f"Failed to notify family group {group_id}: {e}")
                    
        email_subject = f"URGENT: Emergency Alert for {sender_name}!"
        email_body = f"Subject: {email_subject}\n\n{alert_message}"
        family_emails = json.loads(user.family_emails)
        if family_emails and EMAIL_CONNECTION_ID:
            for email in family_emails:
                try:
                    client.initiate(connection_id=EMAIL_CONNECTION_ID, recipient=email, text=email_body)
                except Exception as e:
                    print(f"Failed to notify family email {email}: {e}")
                    
        family_phones = json.loads(user.family_phones)
        try:
            from bot_client import PHONE_CONNECTION_ID
        except ImportError:
            PHONE_CONNECTION_ID = None
            
        if family_phones and PHONE_CONNECTION_ID:
            for phone in family_phones:
                sms_text = f"!!! SIGNALBRIDGE EMERGENCY ALERT !!!\n\nVictim: {sender_name}\nNature: {nature} (Severity: {severity})\nLocation: {maps_link}"
                try:
                    if PHONE_CONNECTION_ID == "mock_sms_gateway_123":
                        print(f"\n[DUMMY SMS GATEWAY] Successfully routed SMS to {phone}:")
                        print(f"   > {sms_text.replace(chr(10), chr(10) + '   > ')}\n")
                    else:
                        client.initiate(
                            connection_id=PHONE_CONNECTION_ID,
                            recipient=phone,
                            text=sms_text
                        )
                except Exception as e:
                    print(f"Failed to send SMS to {phone}: {e}")
                    
        slack_blocks = [
            {
                "type": "card",
                "title": f"!!! EMERGENCY: {severity} !!!",
                "subtitle": f"Nature: {nature} | User: {sender_name}",
                "text": f"Location: {location_text}\nCoordinates: {lat}, {lon}\nRaw Context: {raw_context.strip()}\n\n> *Type `dispatch_em:{emergency_id}` to mark as dispatched and notify the victim.*"
            }
        ]
        
        if SLACK_DISPATCH_CHANNEL:
            try:
                client.send_message(SLACK_DISPATCH_CHANNEL, text="New Emergency", blocks=slack_blocks)
            except Exception as e:
                print(f"Failed to send to Slack via SDK: {e}")

        discord_text = (
            f"**!!! VOLUNTEER INTERPRETER NEEDED !!!**\n\n"
            f"**Victim:** {sender_name}\n"
            f"**Location:** {location_text}\n"
            f"**Context:** {raw_context.strip()}\n\n"
            f"Can you assist in translating or calming the victim?\n"
            f"> *Type `accept_relay:{emergency_id}` to open a live bridge to the victim.*"
        )
        
        if DISCORD_VOLUNTEER_CHANNEL:
            try:
                client.send_message(DISCORD_VOLUNTEER_CHANNEL, text=discord_text)
            except Exception as e:
                print(f"Failed to send to Discord via SDK: {e}")

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
            print(f"Failed to notify mock dispatch: {e}")
    finally:
        db.close()

def auto_dispatch_timeout(user_id_str, channel_id, sender_name):
    db = SessionLocal()
    try:
        em = db.query(Emergency).filter(
            Emergency.user_id == user_id_str,
            Emergency.status == EmergencyStatus.PENDING_LOCATION
        ).first()
        
        if em:
            client.send_message(channel_id, "[WARNING] 15 seconds elapsed! Auto-dispatching emergency with Unknown Location.")
            em.status = EmergencyStatus.DISPATCHED
            em.location = "Unknown"
            db.commit()
            
            dispatch_emergency(
                user_id_str, sender_name,
                em.nature, em.severity, em.location, 0.0, 0.0, em.raw_context, emergency_id=em.id
            )
    finally:
        db.close()
