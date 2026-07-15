from enum import Enum
from pydantic import BaseModel
from typing import Optional, Any, Dict

class DeviceType(str, Enum):
    PHONE = "phone"
    LAPTOP = "laptop"
    TABLET = "tablet"
    DASHBOARD = "dashboard"

class DeviceStatus(str, Enum):
    SLEEPING = "SLEEPING"
    JOINED = "JOINED"
    SCOUT = "SCOUT"
    INFERENCING = "INFERENCING"
    DONE = "DONE"

class EventType(str, Enum):
    REGISTER = "register"
    STATE_UPDATE = "state_update"
    TOKEN_STREAM = "token_stream"
    FINAL_ANSWER = "final_answer"
    WAKE = "wake"
    START_INFERENCE = "start_inference"
    TIMELINE_EVENT = "timeline_event"

class Message(BaseModel):
    type: EventType
    device_id: Optional[str] = None
    payload: Dict[str, Any]

class TokenPayload(BaseModel):
    token: str

class FinalAnswerPayload(BaseModel):
    answer: str
    quorum_score: float

class StateUpdatePayload(BaseModel):
    status: DeviceStatus
    tokens_generated: int = 0
    current_quorum_score: float = 0.0
