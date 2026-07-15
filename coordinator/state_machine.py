from enum import Enum
from .logger import event_logger

class QuorumState(str, Enum):
    IDLE = "IDLE"
    SCOUT = "SCOUT"
    ESCALATE = "ESCALATE"
    CONSENSUS = "CONSENSUS"
    DONE = "DONE"

class StateMachine:
    def __init__(self):
        self.state = QuorumState.IDLE
        event_logger.log("System Initialized", {"state": self.state})

    def transition_to(self, new_state: QuorumState, reason: str = ""):
        if self.state == new_state:
            return
            
        old_state = self.state
        self.state = new_state
        event_logger.log("State Transition", {
            "from": old_state,
            "to": new_state,
            "reason": reason
        })
        
    def reset(self):
        self.transition_to(QuorumState.IDLE, "Resetting system")

state_machine = StateMachine()
