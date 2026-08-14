import os
import re
import httpx
import json
from bot_client import client
from database import SessionLocal
from utils import extract_lat_lon_from_url, VisualCountdownTimer, pending_timers
from dispatch import dispatch_emergency, auto_dispatch_timeout
from ai_extractor import extract_emergency_details, transcribe_audio
from models import User, Emergency, EmergencyStatus, RelaySession

@client.on_message
def handle_emergency(message):
    raw_sender = getattr(message, 'sender_id', getattr(message, 'user_id', getattr(message, 'sender', 'Unknown')))
    sender_name = "Unknown User"
    
    if isinstance(raw_sender, dict):
        sender_id = raw_sender.get('address', raw_sender)
        sender_name = raw_sender.get('name', sender_name)
    else:
        sender_id = raw_sender
        
    channel_id = getattr(message, 'conversation_id', getattr(message, 'channel_id', getattr(message, 'chat_id', 'Unknown')))
    user_id_str = str(sender_id)
    text = message.text or ""
    
    print(f"[DEBUG] Received message from {sender_name} ({user_id_str}) in channel {channel_id}: {text}")
    
    db = SessionLocal()
    try:
        if text.startswith("dispatch_em:"):
            em_id = text.split(":")[1]
            
            em = db.query(Emergency).filter(Emergency.id == int(em_id)).first()
            if em and em.user and em.user.private_chat_id:
                client.send_message(em.user.private_chat_id, f"[INFO] **Help is on the way!** 911 Dispatch has received your SOS and emergency units have been dispatched to your location.")
                
            client.send_message(channel_id, f"[SUCCESS] Acknowledged. Units dispatched for Emergency #{em_id}. The victim has been notified.")
            return
            
        if text.startswith("accept_relay:"):
            em_id = text.split(":")[1]
            relay = RelaySession(
                emergency_id=int(em_id),
                discord_user_id=user_id_str,
                discord_channel_id=channel_id
            )
            db.add(relay)
            db.commit()
            client.send_message(channel_id, f"[SUCCESS] You are now bridged to Emergency #{em_id}. Any message you send here will be forwarded to the user.")
            return

        discord_channel = os.getenv("DISCORD_VOLUNTEER_CHANNEL")
        if discord_channel and channel_id == discord_channel:
            relay = db.query(RelaySession).filter(
                RelaySession.discord_user_id == user_id_str,
                RelaySession.is_active == True
            ).first()
            if relay:
                em = db.query(Emergency).filter(Emergency.id == relay.emergency_id).first()
                if em and em.user and em.user.private_chat_id:
                    client.send_message(em.user.private_chat_id, f"**Volunteer:** {text}")
            else:
                client.send_message(channel_id, "[WARNING] You are not currently bridged to any active emergency. Type `accept_relay:<id>` to join one.")
            return
        user = db.query(User).filter(User.id == user_id_str).first()
        if not user:
            user = User(id=user_id_str)
            db.add(user)
            db.commit()

        if user.status == "UNAUTHORIZED":
            if text.strip() == "ClaudeCodeIsAllUNeed":
                user.status = "AUTHORIZED"
                user.private_chat_id = channel_id
                db.commit()
                client.send_message(channel_id, "[SUCCESS] Password correct! You are now authorized.\n\nHere are your next steps:\n• Add this bot to your Family Group(s) and type `/link` in those groups.\n• Link family emails using `/addemail name@example.com`.")
                return
            else:
                client.send_message(channel_id, "[LOCKED] This bot is private. Please enter the password to register.")
                return

        family_groups = json.loads(user.family_groups)
        if channel_id in family_groups:
            if text.strip().lower() == "/link":
                client.send_message(channel_id, "This group is already linked to your account.")
            elif text.strip().lower() == "/unlink":
                family_groups.remove(channel_id)
                user.family_groups = json.dumps(family_groups)
                db.commit()
                client.send_message(channel_id, "[SUCCESS] This chat has been unlinked from your account.")
            return

        if text.strip().lower() == "/link":
            if channel_id == user.private_chat_id:
                client.send_message(channel_id, "[WARNING] You cannot link your private chat. Please add me to a group and type `/link` inside the group.")
                return
            if channel_id not in family_groups:
                family_groups.append(channel_id)
                user.family_groups = json.dumps(family_groups)
                db.commit()
                client.send_message(channel_id, "[SUCCESS] Group successfully linked to your account for emergency alerts!")
            return

        if text.strip().lower() == "/start":
            client.send_message(channel_id, "Welcome back!\n\n• Send a text or voice note to trigger an emergency alert.\n• To link a new group, add me to it and type `/link`.\n• Link family emails using `/addemail name@example.com`.\n• Link family phones using `/addphone +1234567890`.")
            return
            
        if text.strip().lower().startswith("/addemail "):
            email_addr = text.strip()[10:].strip()
            if "@" in email_addr and "." in email_addr:
                family_emails = json.loads(user.family_emails)
                if email_addr not in family_emails:
                    family_emails.append(email_addr)
                    user.family_emails = json.dumps(family_emails)
                    db.commit()
                    client.send_message(channel_id, f"[SUCCESS] Email {email_addr} successfully linked to your account for emergency alerts!")
                else:
                    client.send_message(channel_id, "That email is already linked.")
            else:
                client.send_message(channel_id, "[WARNING] Invalid email format. Please use: /addemail name@example.com")
            return

        if text.strip().lower().startswith("/addphone "):
            phone_num = text.strip()[10:].strip()
            if phone_num.startswith("+") and len(phone_num) >= 10:
                family_phones = json.loads(user.family_phones)
                if phone_num not in family_phones:
                    family_phones.append(phone_num)
                    user.family_phones = json.dumps(family_phones)
                    db.commit()
                    client.send_message(channel_id, f"[SUCCESS] Phone number {phone_num} successfully linked! Offline SMS alerts enabled.")
                else:
                    client.send_message(channel_id, "That phone number is already linked.")
            else:
                client.send_message(channel_id, "[WARNING] Invalid phone format. Please use: /addphone +1234567890")
            return

        lat, lon = 0.0, 0.0
        active_em = db.query(Emergency).filter(
            Emergency.user_id == user_id_str,
            Emergency.status == EmergencyStatus.PENDING_LOCATION
        ).first()

        if hasattr(message, 'location') and message.location:
            lat = float(message.location.get('latitude', 0.0) if isinstance(message.location, dict) else getattr(message.location, 'latitude', 0.0))
            lon = float(message.location.get('longitude', 0.0) if isinstance(message.location, dict) else getattr(message.location, 'longitude', 0.0))
            
        if lat == 0.0 and lon == 0.0 and text:
            url_match = re.search(r'(https?://[^\s]+)', text)
            if url_match:
                if user_id_str in pending_timers:
                    pending_timers[user_id_str].pause()
                    client.send_message(channel_id, "[INFO] Processing location link...")
                lat, lon = extract_lat_lon_from_url(url_match.group(1))
                if lat == 0.0 and lon == 0.0 and user_id_str in pending_timers:
                    pending_timers[user_id_str].resume()

        if lat != 0.0 and lon != 0.0:
            if active_em:
                if user_id_str in pending_timers:
                    pending_timers[user_id_str].cancel()
                    del pending_timers[user_id_str]
                    
                active_em.status = EmergencyStatus.DISPATCHED
                active_em.lat = lat
                active_em.lon = lon
                active_em.location = "Location Pin Attached"
                db.commit()
                
                client.send_message(channel_id, "[SUCCESS] Location received! Dispatching emergency now.")
                dispatch_emergency(
                    user_id_str, sender_name,
                    active_em.nature, active_em.severity, active_em.location, lat, lon, active_em.raw_context, emergency_id=active_em.id
                )
                return

        if text.strip().lower() == "/sos":
            client.send_message(channel_id, "!!! SIGNALBRIDGE EMERGENCY ACTIVATED !!!\nPlease describe your emergency (via Text or Voice Note).")
            return

        raw_context = ""
        attachments = getattr(message, 'attachments', getattr(message, 'media', getattr(message, 'files', [])))
        if attachments:
            for attachment in attachments:
                url = attachment.get('url') if isinstance(attachment, dict) else getattr(attachment, 'url', None)
                filename = attachment.get('filename', attachment.get('name', '')) if isinstance(attachment, dict) else getattr(attachment, 'filename', getattr(attachment, 'name', ''))
                file_type = attachment.get('type', attachment.get('content_type', attachment.get('mime_type', ''))) if isinstance(attachment, dict) else getattr(attachment, 'type', getattr(attachment, 'content_type', getattr(attachment, 'mime_type', '')))
                
                is_audio = False
                if filename and filename.lower().endswith((".ogg", ".oga", ".mp3", ".m4a", ".wav", ".flac", ".webm")):
                    is_audio = True
                elif file_type and ('audio' in file_type.lower() or 'voice' in file_type.lower()):
                    is_audio = True
                elif url and (".ogg" in url.lower() or ".oga" in url.lower() or "voice" in url.lower()):
                    is_audio = True
                    
                if is_audio:
                    if not filename:
                        filename = "voice_note.ogg"
                        
                    if not url and 'file_id' in attachment:
                        telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
                        if telegram_token:
                            file_info_url = f"https://api.telegram.org/bot{telegram_token}/getFile?file_id={attachment['file_id']}"
                            try:
                                resp = httpx.get(file_info_url, timeout=30.0)
                                file_path = resp.json().get('result', {}).get('file_path')
                                if file_path:
                                    url = f"https://api.telegram.org/file/bot{telegram_token}/{file_path}"
                            except Exception as e:
                                print(f"Failed to fetch Telegram file URL: {e}")
                                
                    if url:
                        if "api.telegram.orgfile" in url:
                            url = url.replace("api.telegram.orgfile", "api.telegram.org/file")
                        try:
                            os.makedirs("scratch", exist_ok=True)
                            audio_path = os.path.join("scratch", filename)
                            resp = httpx.get(url, follow_redirects=True, timeout=30.0)
                            with open(audio_path, "wb") as f:
                                f.write(resp.content)
                            transcription = transcribe_audio(audio_path)
                            if transcription:
                                raw_context += f" [Voice Note Transcription: {transcription}]"
                            else:
                                client.send_message(channel_id, "[WARNING] We received your audio but our AI failed to transcribe it. Please type your emergency.")
                                return
                        except Exception as e:
                            print(f"Failed to download/transcribe audio: {e}")
                            client.send_message(channel_id, "[WARNING] Failed to process audio file. Please type your emergency.")
                            return
        
        if text:
            raw_context += f" {text}"

        if not raw_context.strip():
            debug_info = str(message.__dict__) if hasattr(message, "__dict__") else str(message)
            client.send_message(channel_id, f"[WARNING] SignalBridge activated, but no text or readable voice note was found. Please describe your emergency.\n\n[DEBUG PAYLOAD]: {debug_info[:800]}")
            return

        if active_em and active_em.relay and active_em.relay.is_active:
            client.send_message(active_em.relay.discord_channel_id, f"**Victim:** {raw_context.strip()}")

        details = extract_emergency_details(raw_context)
        nature = details.get("nature_of_emergency", "Unknown")
        severity = details.get("severity", "Unknown")
        location = details.get("location", "Unknown")

        if nature == "FALSE_ALARM":
            client.send_message(channel_id, "I am an emergency bot. If you have an emergency, please describe it clearly.")
            return

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

        if not family_groups:
            client.send_message(channel_id, "[WARNING] You have no linked family groups! Please add me to a group and type `/link`.")

        new_em = Emergency(
            user_id=user_id_str,
            nature=nature,
            severity=severity,
            location=location,
            lat=lat,
            lon=lon,
            raw_context=raw_context.strip(),
            status=EmergencyStatus.PENDING_LOCATION if lat == 0.0 and lon == 0.0 else EmergencyStatus.DISPATCHED
        )
        db.add(new_em)
        db.commit()

        if lat == 0.0 and lon == 0.0:
            client.send_message(channel_id, "[WARNING] Emergency detected! Please paste a Google Maps link to your location so we can dispatch help. (Auto-dispatching in 15 seconds...)")
            timer = VisualCountdownTimer(15.0, auto_dispatch_timeout, args=(user_id_str, channel_id, sender_name))
            timer.start()
            pending_timers[user_id_str] = timer
            return

        client.send_message(channel_id, "[SUCCESS] Your emergency has been reported. Emergency services and your family have been notified.")
        dispatch_emergency(user_id_str, sender_name, nature, severity, location, lat, lon, raw_context, emergency_id=new_em.id)

    finally:
        db.close()
