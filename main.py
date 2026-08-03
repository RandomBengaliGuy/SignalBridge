import os
import httpx
import logging
from fastapi import FastAPI
from caspian_sdk import CommClient
from dotenv import load_dotenv

# Silence the httpx polling spam
logging.getLogger("httpx").setLevel(logging.WARNING)

from mock_dispatch import dispatch_router
from ai_extractor import extract_emergency_details, transcribe_audio

load_dotenv()

import threading
from contextlib import asynccontextmanager

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
FAMILY_GROUP_ID = os.getenv("FAMILY_GROUP_ID", "default_family_group_id")



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
    
    # Ignore messages sent inside the Family Group (prevent loops and spam)
    if channel_id == FAMILY_GROUP_ID:
        return
        
    # If the user has configured specific Telegram IDs, restrict access to only them.
    # Supports a comma-separated list in the .env file (e.g. 1234,5678,9012)
    if DUMMY_USER_TELEGRAM_ID != "default_telegram_id":
        allowed_ids = [i.strip() for i in str(DUMMY_USER_TELEGRAM_ID).split(",")]
        if str(sender_id) not in allowed_ids:
            client.send_message(channel_id, "You are not authorized to use this emergency relay.")
            return

    # Ignore /start command
    if message.text and message.text.strip().lower() == "/start":
        client.send_message(channel_id, "Welcome to SignalBridge. Send a text or voice note to trigger an emergency alert.")
        return

    # Check if the user is triggering an SOS
    if message.text and message.text.strip().lower() == "/sos":
        client.send_message(channel_id, 
            "🚨 SIGNALBRIDGE EMERGENCY ACTIVATED 🚨\n"
            "Please describe your emergency (via Text or Voice Note).\n"
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

    # Filter out false alarms (like greetings)
    if nature == "FALSE_ALARM":
        client.send_message(channel_id, "I am an emergency bot. If you have an emergency, please describe it clearly.")
        return

    # 3. Outbound 1: Notify Family via Caspian to the configured WhatsApp/Discord Group
    alert_message = (
        f"🚨 EMERGENCY ALERT 🚨\n"
        f"⚠️ {sender_name} is in distress! ⚠️\n"
        f"Nature: {nature}\n"
        f"Severity: {severity}\n"
        f"Raw message: {raw_context.strip()}"
    )
    
    # Send via Caspian to the Telegram Family Group
    try:
        client.send_message(
            conversation_id=FAMILY_GROUP_ID,
            text=alert_message
        )
        print(f"Alert sent to Telegram Family Group: {FAMILY_GROUP_ID}")
    except Exception as e:
        print(f"Failed to notify family group: {e}")

    # 4. Outbound 2: Send to Mock Dispatcher API
    try:
        payload = {
            "user_id": str(sender_id),
            "nature_of_emergency": nature,
            "severity": severity,
            "latitude": 0.0,
            "longitude": 0.0,
            "raw_transcript": raw_context.strip()
        }
        # In this MVP, the FastAPI dispatcher runs locally on port 8000
        httpx.post("http://localhost:8000/api/dispatch", json=payload)
    except Exception as e:
        print(f"Failed to notify dispatch: {e}")
        
    # Acknowledge to the user (sent to their direct chat)
    client.send_message(channel_id, "✅ Your emergency has been reported.\n Emergency services and your family have been notified.")

# In a real environment, you would run the Caspian listener in a background thread 
# or alongside FastAPI using asyncio.
# For simplicity, we can run them concurrently using standard deployment commands.
