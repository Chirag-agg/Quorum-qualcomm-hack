import time
from datetime import datetime
from typing import List, Dict, Any

class EventLogger:
    def __init__(self):
        self.events: List[Dict[str, Any]] = []
        self.start_time = time.time()

    def log(self, event_name: str, details: Dict[str, Any] = None):
        elapsed = time.time() - self.start_time
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        event = {
            "timestamp": timestamp,
            "elapsed_sec": round(elapsed, 2),
            "event": event_name,
            "details": details or {}
        }
        self.events.append(event)
        
        # Also print to terminal for debugging
        print(f"[{timestamp}] {event_name} | {details if details else ''}")
        return event

    def get_all_events(self) -> List[Dict[str, Any]]:
        return self.events

    def log_inference_summary(self, question: str, scout_score: float, escalated: bool, devices_used: int, consensus_reached: bool, final_answer: str, latency_ms: int):
        summary = {
            "Question": question,
            "Scout Score": round(scout_score, 3),
            "Escalated?": escalated,
            "Devices used": devices_used,
            "Consensus": consensus_reached,
            "Final answer": final_answer,
            "Latency": f"{latency_ms}ms"
        }
        self.log("Inference Complete Benchmark", summary)
        print("\n--- INFERENCE BENCHMARK ---")
        for k, v in summary.items():
            print(f"{k}: {v}")
        print("---------------------------\n")

    def clear(self):
        self.events = []
        self.start_time = time.time()

event_logger = EventLogger()

