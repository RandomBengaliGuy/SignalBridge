import os
import httpx
import logging
import json
from fastapi import FastAPI
from caspian_sdk import CommClient
from dotenv import load_dotenv

# Silence the httpx polling spam
logging.getLogger("httpx").setLevel(logging.WARNING)

from mock_dispatch import dispatch_router
from ai_extractor import extract_emergency_details, transcribe_audio

load_dotenv()

import threading
import re
import httpx
from contextlib import asynccontextmanager

pending_timers = {}

def extract_lat_lon_from_url(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        with httpx.Client(follow_redirects=True) as client_http:
            resp = client_http.get(url, headers=headers, timeout=10.0)
            final_url = str(resp.url)
            # Match variations like @lat,lon or q=lat,lon or place/lat,lon
            match = re.search(r'(?:@|q=|place/)(-?\d+\.\d+),(-?\d+\.\d+)', final_url)
            if match:
                return float(match.group(1)), float(match.group(2))
    except Exception as e:
        print(f"Failed to resolve Maps URL: {e}")
    return 0.0, 0.0

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the Caspian SDK listener in a background thread 
    # so it doesn't block the FastAPI web server from starting.
    thread = threading.Thread(target=client.listen, daemon=True)
    thread.start()
    yield

# Initialize FastAPI for the mock dispatcher API
app = FastAPI(lifespan=lifespan)
app.include_router(dispatch_router)

# Initialize Caspian SDK Client
# Make sure you run `caspian init` and `caspian connect telegram` in your CLI
client = CommClient()

DUMMY_USER_TELEGRAM_ID = os.getenv("DUMMY_USER_TELEGRAM_ID", "default_telegram_id")

# Helper functions for state management
USERS_FILE = "users.json"

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_users(users_data):
    with open(USERS_FILE, "w") as f:
        json.dump(users_data, f, indent=4)



@client.on_message
def handle_emergency(message):
    """
    Unified entry point for messages coming from Telegram, Discord, SMS, etc.
    """
    # Quick debug to help you find your group ID!
    print(f"----- INCOMING MESSAGE DEBUG -----")
    print(f"RAW MESSAGE DUMP:")
    try:
        print(vars(message))
    except Exception as e:
        print(f"Could not dump message: {e}")
        
    try:
        attachments = getattr(message, 'attachments', [])
        print(f"ATTACHMENTS DUMP:")
        for a in attachments:
            print(vars(a) if hasattr(a, '__dict__') else a)
    except Exception as e:
        print(f"Could not dump attachments: {e}")
        
    # We will safely try to get common ID fields since Caspian SDK schemas vary slightly
    raw_sender = getattr(message, 'sender_id', getattr(message, 'user_id', getattr(message, 'sender', 'Unknown')))
    sender_name = "Unknown User"
    
    # Caspian sometimes wraps sender info in a dictionary, so we extract the raw ID (address) and name
    if isinstance(raw_sender, dict):
        sender_id = raw_sender.get('address', raw_sender)
        sender_name = raw_sender.get('name', sender_name)
    else:
        sender_id = raw_sender
        
    channel_id = getattr(message, 'conversation_id', getattr(message, 'channel_id', getattr(message, 'chat_id', 'Unknown')))
    
    print(f"Detected Sender ID: {sender_id}")
    print(f"Detected Channel/Group ID (conversation_id): {channel_id}")
    print(f"----------------------------------")
    
    users_data = load_users()
    user_id_str = str(sender_id)
    
    if user_id_str not in users_data:
        users_data[user_id_str] = {
            "status": "UNAUTHORIZED",
            "family_groups": []
        }
        save_users(users_data)
        
    user_info = users_data[user_id_str]
    
    # 1. Password check for UNAUTHORIZED users
    if user_info["status"] == "UNAUTHORIZED":
        if message.text and message.text.strip() == "ClaudeCodeIsAllUNeed":
            user_info["status"] = "AUTHORIZED"
            user_info["private_chat_id"] = channel_id
            save_users(users_data)
            client.send_message(channel_id, "✅ Password correct! You are now authorized. Please add this bot to your Family Group(s) and type `/link` in those groups.")
            return
        else:
            client.send_message(channel_id, "🔒 This bot is private. Please enter the password to register.")
            return

    # From here on, user is AUTHORIZED.
    
    # Ignore messages sent inside the Family Group (prevent loops and spam)
    if channel_id in user_info.get("family_groups", []):
        text_lower = message.text.strip().lower() if message.text else ""
        if text_lower == "/link":
            client.send_message(channel_id, "This group is already linked to your account.")
        elif text_lower == "/unlink":
            user_info["family_groups"].remove(channel_id)
            save_users(users_data)
            client.send_message(channel_id, "✅ This chat has been unlinked from your account.")
        return

    # 2. Check for /link command
    if message.text and message.text.strip().lower() == "/link":
        if channel_id == user_info.get("private_chat_id"):
            client.send_message(channel_id, "⚠️ You cannot link your private chat. Please add me to a group and type `/link` inside the group.")
            return
            
        if channel_id not in user_info["family_groups"]:
            user_info["family_groups"].append(channel_id)
            save_users(users_data)
            client.send_message(channel_id, "✅ Group successfully linked to your account for emergency alerts!")
        return

    # Ignore /start command
    if message.text and message.text.strip().lower() == "/start":
        client.send_message(channel_id, "Welcome back! Send a text or voice note to trigger an emergency alert. To link a new group, add me to it and type `/link`.")
        return

    # Check for incoming location pins to resolve pending emergencies
    lat, lon = 0.0, 0.0
    
    if "pending_emergency" in user_info:
        print(f"\n--- DEBUG: PENDING EMERGENCY MESSAGE RECEIVED ---")
        print(f"message.text: {message.text}")
        print(f"message.media: {message.media}")
        print(f"message.raw_payload: {getattr(message, 'raw_payload', 'NOT FOUND')}")
        print(f"vars(message): {vars(message)}")
        print(f"--------------------------------------------------\n")
    if hasattr(message, 'location') and message.location:
        lat = float(message.location.get('latitude', 0.0) if isinstance(message.location, dict) else getattr(message.location, 'latitude', 0.0))
        lon = float(message.location.get('longitude', 0.0) if isinstance(message.location, dict) else getattr(message.location, 'longitude', 0.0))
        
    # Check for Google Maps URL as a fallback for location pin
    if lat == 0.0 and lon == 0.0 and message.text:
        url_match = re.search(r'(https?://[^\s]+)', message.text)
        if url_match:
            lat, lon = extract_lat_lon_from_url(url_match.group(1))

    if lat != 0.0 and lon != 0.0:
        if "pending_emergency" in user_info:
            if user_id_str in pending_timers:
                pending_timers[user_id_str].cancel()
                del pending_timers[user_id_str]
                
            pending = user_info["pending_emergency"]
            client.send_message(channel_id, "✅ Location received! Dispatching emergency now.")
            
            dispatch_emergency(
                user_id_str, sender_name,
                pending["nature"], pending["severity"], "Location Pin Attached", lat, lon, pending["raw_context"]
            )
            
            del user_info["pending_emergency"]
            save_users(users_data)
            return

    # Check if the user is triggering an SOS
    if message.text and message.text.strip().lower() == "/sos":
        client.send_message(channel_id, 
            "🚨 SIGNALBRIDGE EMERGENCY ACTIVATED 🚨\n"
            "Please describe your emergency (via Text or Voice Note).\n\n"
            "Example: 'I am trapped in a fire!'"
        )
        return

    # 1. Extract context from text or voice
    raw_context = ""
    
    # Safely extract attachments or media
    attachments = getattr(message, 'attachments', getattr(message, 'media', getattr(message, 'files', [])))
    if attachments:
        for attachment in attachments:
            # Check if it's an audio file (.ogg from Telegram voice notes)
            # Attachments might be dicts or objects depending on Caspian's internal schema
            filename = ""
            file_type = ""
            if isinstance(attachment, dict):
                filename = attachment.get('filename', attachment.get('name', ''))
                file_type = attachment.get('type', attachment.get('content_type', attachment.get('mime_type', '')))
            else:
                filename = getattr(attachment, 'filename', getattr(attachment, 'name', ''))
                file_type = getattr(attachment, 'type', getattr(attachment, 'content_type', getattr(attachment, 'mime_type', '')))
                
            is_audio = False
            if filename and filename.endswith((".ogg", ".oga", ".mp3", ".m4a", ".wav")):
                is_audio = True
            elif file_type and ('audio' in file_type or 'voice' in file_type):
                is_audio = True
                if not filename:
                    filename = "voice_note.ogg"
                    
            if is_audio:
                # Download the attachment from Caspian's URL
                url = attachment.get('url') if isinstance(attachment, dict) else getattr(attachment, 'url', None)
                if url:
                    # Patch Caspian bug with Telegram URLs
                    if "api.telegram.orgfile" in url:
                        url = url.replace("api.telegram.orgfile", "api.telegram.org/file")
                    try:
                        os.makedirs("scratch", exist_ok=True)
                        audio_path = os.path.join("scratch", filename)
                        
                        # Use httpx to securely download the file
                        resp = httpx.get(url, follow_redirects=True)
                        with open(audio_path, "wb") as f:
                            f.write(resp.content)
                            
                        # Transcribe it
                        transcription = transcribe_audio(audio_path)
                        if transcription:
                            raw_context += f" [Voice Note Transcription: {transcription}]"
                        else:
                            client.send_message(channel_id, "⚠️ We received your audio but our AI failed to transcribe it. Please type your emergency.")
                            return
                        
                    except Exception as e:
                        print(f"Failed to download/transcribe audio: {e}")
                        client.send_message(channel_id, "⚠️ Failed to process audio file. Please type your emergency.")
                        return
    
    if message.text:
        raw_context += f" {message.text}"

    # We need *some* context to extract emergency details
    if not raw_context.strip():
        client.send_message(channel_id, "⚠️ SignalBridge activated, but no text or readable voice note was found. Please describe your emergency.")
        return

    # 2. Use Groq AI to structure the emergency data
    details = extract_emergency_details(raw_context)
    nature = details.get("nature_of_emergency", "Unknown")
    severity = details.get("severity", "Unknown")
    location = details.get("location", "Unknown")

    # Filter out false alarms (like greetings)
    if nature == "FALSE_ALARM":
        client.send_message(channel_id, "I am an emergency bot. If you have an emergency, please describe it clearly.")
        return

    # lat and lon were already resolved at the top of the script.
    
    # If we have a text location and no pin/URL was found, use Geocoding
    if lat == 0.0 and lon == 0.0 and location != "Unknown" and "http" not in location:
        try:
            url = "https://nominatim.openstreetmap.org/search"
            params = {"q": location, "format": "json", "limit": 1}
            headers = {"User-Agent": "SignalBridgeEmergencyBot/1.0"}
            resp = httpx.get(url, params=params, headers=headers, timeout=5.0)
            data = resp.json()
            if data and len(data) > 0:
                lat = float(data[0]["lat"])
                lon = float(data[0]["lon"])
        except Exception as e:
            print(f"Geocoding failed: {e}")

    if not user_info.get("family_groups"):
        client.send_message(channel_id, "⚠️ You have no linked family groups! Please add me to a group and type `/link`.")

    # State Machine Logic: Dispatch or Wait
    if lat == 0.0 and lon == 0.0:
        user_info["pending_emergency"] = {
            "nature": nature,
            "severity": severity,
            "raw_context": raw_context.strip()
        }
        save_users(users_data)
        
        client.send_message(channel_id, "⚠️ Emergency detected! Please paste a Google Maps link to your location so we can dispatch help. (Auto-dispatching in 15 seconds...)")
        
        timer = threading.Timer(15.0, auto_dispatch_timeout, args=(user_id_str, channel_id, sender_name))
        timer.start()
        pending_timers[user_id_str] = timer
        return

    # Acknowledge to the user (sent to their direct chat)
    client.send_message(channel_id, "✅ Your emergency has been reported. Emergency services and your family have been notified.")
    dispatch_emergency(user_id_str, sender_name, nature, severity, location, lat, lon, raw_context)

# In a real environment, you would run the Caspian listener in a background threaduld run the Caspian listener in a background thread 
# or alongside FastAPI using asyncio.
# For simplicity, we can run them concurrently using standard deployment commands.
