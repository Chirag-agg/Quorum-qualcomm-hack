import asyncio
import json
import time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, List, Any
from .models import Message, EventType, DeviceStatus
from .state_machine import state_machine, QuorumState
from .logger import event_logger
from .consensus import consensus_engine

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class CoordinatorRouter:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.dashboard_sockets: List[WebSocket] = []
        self.candidates: List[Dict[str, Any]] = []
        self.expected_devices: int = 1
        self.QUORUM_THRESHOLD = 0.85
        
        # Metrics and tracking
        self.metrics = {
            "escalations": 0,
            "tokens": 0,
            "latency_ms": 0,
            "start_time": 0
        }
        self.current_question = ""
        self.scout_score = 0.0
        self.escalated = False
        
        # History for the benchmark table
        self.history = []
        
        # Track device specific state
        self.devices_state = {
            "phone": {"status": "SLEEPING", "tokens": 0, "latency_ms": 0, "decision": ""},
            "laptop": {"status": "SLEEPING", "tokens": 0, "latency_ms": 0, "decision": ""}
        }

    async def connect_device(self, websocket: WebSocket, device_id: str):
        await websocket.accept()
        self.active_connections[device_id] = websocket
        self.devices_state[device_id]["status"] = "JOINED"
        event_logger.log("Device Connected", {"device_id": device_id})
        await self.broadcast_to_dashboard({"type": "device_connected", "device_id": device_id})

    async def connect_dashboard(self, websocket: WebSocket):
        await websocket.accept()
        self.dashboard_sockets.append(websocket)
        # Dashboard uses GET /session for initial load, so we don't need to send huge initial state here.

    def disconnect_device(self, device_id: str):
        if device_id in self.active_connections:
            del self.active_connections[device_id]
            self.devices_state[device_id]["status"] = "OFFLINE"
            event_logger.log("Device Disconnected", {"device_id": device_id})
            
            # HACKATHON FALLBACK
            if state_machine.state == QuorumState.SCOUT and device_id == "phone":
                print("\n*** CODE WORD: PHOENIX_PROTOCOL -> PHONE DISCONNECTED -> AUTO ESCALATING TO LAPTOP ***\n")
                asyncio.create_task(self._trigger_fallback_escalation())

    async def _trigger_fallback_escalation(self):
        if state_machine.state == QuorumState.SCOUT:
            self.escalated = True
            self.metrics["escalations"] += 1
            state_machine.transition_to(QuorumState.ESCALATE, "Phone disconnected - PHOENIX")
            self.expected_devices = 1  # Only laptop remaining
            wake_payload = {"prompt": getattr(self, "current_question", ""), "scenario": getattr(self, "current_scenario", "Hard Question")}
            await self.send_to_device("laptop", {"type": "wake", "payload": wake_payload})

    def disconnect_dashboard(self, websocket: WebSocket):
        if websocket in self.dashboard_sockets:
            self.dashboard_sockets.remove(websocket)

    async def broadcast_to_dashboard(self, message: dict):
        for ws in self.dashboard_sockets:
            try:
                await ws.send_json(message)
            except:
                pass

    async def send_to_device(self, device_id: str, message: dict):
        if device_id in self.active_connections:
            await self.active_connections[device_id].send_json(message)

    def _record_history(self, answer: str):
        self.metrics["latency_ms"] = int((time.time() - self.metrics["start_time"]) * 1000)
        run_data = {
            "id": len(self.history) + 1,
            "devices": len(self.candidates),
            "escalated": self.escalated,
            "latency_ms": self.metrics["latency_ms"],
            "result": answer,
            "scout_score": self.scout_score
        }
        self.history.append(run_data)
        
        event_logger.log_inference_summary(
            self.current_question, self.scout_score, self.escalated, 
            len(self.candidates), self.escalated, answer, self.metrics["latency_ms"]
        )

    async def handle_message(self, device_id: str, msg: dict):
        # Broadcast all raw messages to dashboard for live updating
        await self.broadcast_to_dashboard({"source_device": device_id, "data": msg})
        
        msg_type = msg.get("type")
        payload = msg.get("payload", {})
        
        if msg_type == "state_update":
            status = payload.get("status")
            if status:
                self.devices_state[device_id]["status"] = status
                
        elif msg_type == EventType.TOKEN_STREAM:
            self.metrics["tokens"] += 1
            self.devices_state[device_id]["tokens"] += 1
            
        elif msg_type == EventType.FINAL_ANSWER:
            ans = payload.get("answer")
            if not ans or not ans.strip():
                ans = "Empty response"
            
            score = payload.get("quorum_score", 0.0)
            
            self.devices_state[device_id]["latency_ms"] = int((time.time() - self.metrics["start_time"]) * 1000)
            self.devices_state[device_id]["decision"] = "LOCAL" if score >= self.QUORUM_THRESHOLD else "ESCALATE"
            
            self.candidates.append({
                "device": device_id,
                "answer": ans,
                "quorum_score": score
            })
            
            if state_machine.state == QuorumState.SCOUT:
                self.scout_score = score
                if score >= self.QUORUM_THRESHOLD:
                    # Scout was confident enough, done
                    state_machine.transition_to(QuorumState.DONE, "Scout confident")
                    self._record_history(ans)
                    await self.broadcast_to_dashboard({"type": "consensus_result", "result": {"answer": ans, "winner": device_id}})
                else:
                    # Low confidence, escalate
                    self.escalated = True
                    self.metrics["escalations"] += 1
                    state_machine.transition_to(QuorumState.ESCALATE, f"Score {score} < {self.QUORUM_THRESHOLD}")
                    
                    # Wake up laptop
                    self.expected_devices = 2
                    
                    # Pass the scenario down
                    wake_payload = {"prompt": self.current_question, "scenario": self.current_scenario}
                    await self.send_to_device("laptop", {"type": EventType.WAKE, "payload": wake_payload})
                    
            elif state_machine.state == QuorumState.ESCALATE:
                if len(self.candidates) == self.expected_devices:
                    state_machine.transition_to(QuorumState.CONSENSUS, "All answers received")
                    result = consensus_engine.resolve(self.candidates)
                    state_machine.transition_to(QuorumState.DONE, "Consensus resolved")
                    
                    self._record_history(result["answer"])
                    
                    await self.broadcast_to_dashboard({"type": "consensus_result", "result": result})

router = CoordinatorRouter()

@app.get("/session")
def get_session():
    elapsed = time.time() - router.metrics["start_time"] if state_machine.state != QuorumState.IDLE and state_machine.state != QuorumState.DONE else (router.metrics["latency_ms"]/1000.0)
    if elapsed == 0: elapsed = 1 # prevent div/0
    tps = round(router.metrics["tokens"] / elapsed, 1)
    
    return {
        "prompt": router.current_question,
        "state": state_machine.state,
        "devices": router.devices_state,
        "timeline": event_logger.get_all_events(),
        "metrics": {
            "latency_ms": router.metrics["latency_ms"],
            "tokens_per_sec": tps,
            "devices_used": len(router.candidates) if router.candidates else (1 if state_machine.state == QuorumState.SCOUT else 0),
            "escalations": router.metrics["escalations"]
        },
        "history": router.history
    }

@app.get("/metrics")
def get_metrics():
    # Legacy endpoint just in case
    return get_session()["metrics"]

@app.websocket("/ws/device/{device_id}")
async def websocket_device(websocket: WebSocket, device_id: str):
    await router.connect_device(websocket, device_id)
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            await router.handle_message(device_id, msg)
    except WebSocketDisconnect:
        router.disconnect_device(device_id)

@app.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket):
    await router.connect_dashboard(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "start_inference":
                payload = msg.get("payload", {})
                prompt = payload.get("prompt", "What is 2+2?")
                scenario = payload.get("scenario", "Hard Question") # Default hard to demo escalation
                
                router.current_question = prompt
                router.current_scenario = scenario
                router.metrics["start_time"] = time.time()
                router.escalated = False
                router.metrics["tokens"] = 0
                router.metrics["latency_ms"] = 0
                
                # reset devices
                for dev in router.devices_state:
                    router.devices_state[dev]["tokens"] = 0
                    router.devices_state[dev]["latency_ms"] = 0
                    router.devices_state[dev]["decision"] = ""
                
                state_machine.reset()
                router.candidates = []
                router.expected_devices = 1
                
                state_machine.transition_to(QuorumState.SCOUT, f"Starting inference ({scenario})")
                
                await router.send_to_device("phone", {
                    "type": EventType.START_INFERENCE, 
                    "payload": {"prompt": prompt, "scenario": scenario}
                })
    except WebSocketDisconnect:
        router.disconnect_dashboard(websocket)
