from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum, Boolean
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
import enum

Base = declarative_base()

class EmergencyStatus(enum.Enum):
    PENDING_LOCATION = "PENDING_LOCATION"
    DISPATCHED = "DISPATCHED"
    RESOLVED = "RESOLVED"

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)
    status = Column(String, default="UNAUTHORIZED")
    private_chat_id = Column(String, nullable=True)
    family_groups = Column(String, default="[]") 
    family_emails = Column(String, default="[]")
    family_phones = Column(String, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)
    
    emergencies = relationship("Emergency", back_populates="user")

class Emergency(Base):
    __tablename__ = "emergencies"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"))
    nature = Column(String)
    severity = Column(String)
    location = Column(String, nullable=True)
    lat = Column(Float, nullable=True, default=0.0)
    lon = Column(Float, nullable=True, default=0.0)
    status = Column(Enum(EmergencyStatus), default=EmergencyStatus.PENDING_LOCATION)
    raw_context = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="emergencies")
    relay = relationship("RelaySession", back_populates="emergency", uselist=False)

class RelaySession(Base):
    __tablename__ = "relay_sessions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    emergency_id = Column(Integer, ForeignKey("emergencies.id"))
    discord_user_id = Column(String, nullable=True)
    discord_channel_id = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    
    emergency = relationship("Emergency", back_populates="relay")
