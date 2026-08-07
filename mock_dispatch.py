from fastapi import APIRouter
from pydantic import BaseModel
import logging

# Configure basic logging for the mock dispatcher
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DispatchCenter")

dispatch_router = APIRouter()

class EmergencyPayload(BaseModel):
    user_id: str
    nature_of_emergency: str
    severity: str
    latitude: float
    longitude: float
    location_text: str | None = "Unknown"
    raw_transcript: str | None = None

@dispatch_router.post("/api/dispatch")
async def receive_emergency(payload: EmergencyPayload):
    """
    Mock endpoint simulating a 911 / Emergency Services API.
    In a real-world scenario, this would trigger an ambulance/police dispatch system.
    """
    logger.info("🚨 🚨 🚨 EMERGENCY DISPATCH ALERT RECEIVED 🚨 🚨 🚨")
    logger.info(f"User ID: {payload.user_id}")
    logger.info(f"Nature of Emergency: {payload.nature_of_emergency}")
    logger.info(f"Severity: {payload.severity}")
    logger.info(f"Coordinates: Latitude {payload.latitude}, Longitude {payload.longitude}")
    logger.info(f"Location Text: {payload.location_text}")
    if payload.raw_transcript:
         logger.info(f"Raw context: {payload.raw_transcript}")
    logger.info("🚨 🚨 🚨 DISPATCHING EMERGENCY SERVICES IMMEDIATELY 🚨 🚨 🚨")
    
    return {"status": "success", "message": "Emergency services dispatched"}
