import os
import re
import httpx
from bot_client import client
from database import load_users, save_users
from utils import extract_lat_lon_from_url, VisualCountdownTimer, pending_timers
from dispatch import dispatch_emergency, auto_dispatch_timeout
from ai_extractor import extract_emergency_details, transcribe_audio

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
            "family_groups": [],
            "family_emails": []
        }
        save_users(users_data)
        
    user_info = users_data[user_id_str]
    
    # 1. Password check for UNAUTHORIZED users
    if user_info["status"] == "UNAUTHORIZED":
        if message.text and message.text.strip() == "ClaudeCodeIsAllUNeed":
            user_info["status"] = "AUTHORIZED"
            user_info["private_chat_id"] = channel_id
            if "family_emails" not in user_info:
                user_info["family_emails"] = []
            save_users(users_data)
            client.send_message(channel_id, 
                "✅ Password correct! You are now authorized.\n\n"
                "Here are your next steps:\n"
                "• Add this bot to your Family Group(s) and type `/link` in those groups.\n"
                "• Link family emails using `/addemail name@example.com`."
            )
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

    # Check for commands in private chat
    if message.text:
        text_lower = message.text.strip().lower()
        if text_lower == "/start":
            client.send_message(channel_id, 
                "Welcome back!\n\n"
                "• Send a text or voice note to trigger an emergency alert.\n"
                "• To link a new group, add me to it and type `/link`.\n"
                "• Link family emails using `/addemail name@example.com`."
            )
            return
        elif text_lower.startswith("/addemail "):
            email_addr = message.text.strip()[10:].strip()
            if "@" in email_addr and "." in email_addr:
                if "family_emails" not in user_info:
                    user_info["family_emails"] = []
                if email_addr not in user_info["family_emails"]:
                    user_info["family_emails"].append(email_addr)
                    save_users(users_data)
                    client.send_message(channel_id, f"✅ Email {email_addr} successfully linked to your account for emergency alerts!")
                else:
                    client.send_message(channel_id, "That email is already linked.")
            else:
                client.send_message(channel_id, "⚠️ Invalid email format. Please use: /addemail name@example.com")
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
            if user_id_str in pending_timers:
                pending_timers[user_id_str].pause()
                client.send_message(channel_id, "🔍 Processing location link...")
                
            lat, lon = extract_lat_lon_from_url(url_match.group(1))
            
            if lat == 0.0 and lon == 0.0 and user_id_str in pending_timers:
                pending_timers[user_id_str].resume()

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
        
        timer = VisualCountdownTimer(15.0, auto_dispatch_timeout, args=(user_id_str, channel_id, sender_name))
        timer.start()
        pending_timers[user_id_str] = timer
        return

    # Acknowledge to the user (sent to their direct chat)
    client.send_message(channel_id, "✅ Your emergency has been reported. Emergency services and your family have been notified.")
    dispatch_emergency(user_id_str, sender_name, nature, severity, location, lat, lon, raw_context)
