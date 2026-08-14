import logging
from fastapi import FastAPI
from contextlib import asynccontextmanager
import threading
from dotenv import load_dotenv

logging.getLogger("httpx").setLevel(logging.WARNING)
load_dotenv()

from bot_client import client
import handlers
from mock_dispatch import dispatch_router
from database import init_db, SessionLocal
from dispatch import dispatch_emergency
from models import Emergency, EmergencyStatus

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        orphaned = db.query(Emergency).filter(Emergency.status == EmergencyStatus.PENDING_LOCATION).all()
        for em in orphaned:
            print(f"CRASH RECOVERY: Found orphaned emergency #{em.id}. Dispatching immediately.")
            em.status = EmergencyStatus.DISPATCHED
            em.location = "Unknown (Server Crash Recovery)"
            db.commit()
            
            sender_name = "User (Recovered)"
            dispatch_emergency(
                em.user_id, sender_name,
                em.nature, em.severity, em.location, 0.0, 0.0, em.raw_context, emergency_id=em.id
            )
            
            if em.user and em.user.private_chat_id:
                try:
                    client.send_message(em.user.private_chat_id, "[WARNING] The server restarted during your emergency. Your alert has been safely auto-dispatched to your family and emergency services as a precaution.")
                except Exception:
                    pass
    except Exception as e:
        print(f"Failed to run crash recovery: {e}")
    finally:
        db.close()

    thread = threading.Thread(target=client.listen, daemon=True)
    thread.start()
    yield

app = FastAPI(lifespan=lifespan)
app.include_router(dispatch_router)

@app.get("/")
def health_check():
    return {"status": "ok", "message": "SignalBridge is awake!"}
