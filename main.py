import logging
from fastapi import FastAPI
from contextlib import asynccontextmanager
import threading
from dotenv import load_dotenv

# Silence the httpx polling spam
logging.getLogger("httpx").setLevel(logging.WARNING)
load_dotenv()

from bot_client import client
import handlers  # Import handlers to register the @client.on_message decorator
from mock_dispatch import dispatch_router
from database import load_users, save_users
from dispatch import dispatch_emergency

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Crash Recovery: Check for any orphaned pending emergencies
    try:
        users_data = load_users()
        recovered = False
        for user_id_str, user_info in users_data.items():
            if "pending_emergency" in user_info:
                pending = user_info["pending_emergency"]
                channel_id = user_info.get("private_chat_id", "Unknown")
                
                print(f"CRASH RECOVERY: Found orphaned emergency for {user_id_str}. Dispatching immediately.")
                
                dispatch_emergency(
                    user_id_str, "User (Recovered)",
                    pending["nature"], pending["severity"], "Unknown (Server Crash Recovery)", 0.0, 0.0, pending["raw_context"]
                )
                
                if channel_id != "Unknown":
                    try:
                        client.send_message(channel_id, "⚠️ The server restarted during your emergency. Your alert has been safely auto-dispatched to your family as a precaution.")
                    except Exception:
                        pass
                
                del user_info["pending_emergency"]
                recovered = True
                
        if recovered:
            save_users(users_data)
    except Exception as e:
        print(f"Failed to run crash recovery: {e}")

    # Start the Caspian SDK listener in a background thread 
    # so it doesn't block the FastAPI web server from starting.
    thread = threading.Thread(target=client.listen, daemon=True)
    thread.start()
    yield

# Initialize FastAPI for the mock dispatcher API
app = FastAPI(lifespan=lifespan)
app.include_router(dispatch_router)
