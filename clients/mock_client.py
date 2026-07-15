import asyncio
import websockets
import json
import argparse
import time
import random
import sys
import os

# Append parent dir so we can import from coordinator if needed
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def run_client(device_id: str, ws_url: str):
    print(f"[{device_id}] Connecting to {ws_url}...")
    try:
        async with websockets.connect(ws_url) as websocket:
            print(f"[{device_id}] Connected.")
            
            async for message in websocket:
                data = json.loads(message)
                msg_type = data.get("type")
                
                if msg_type == "start_inference" or msg_type == "wake":
                    print(f"\n[{device_id}] Received {msg_type}. Starting inference...")
                    
                    # Update status
                    await websocket.send(json.dumps({
                        "type": "state_update",
                        "payload": {"status": "INFERENCING"}
                    }))
                    scenario = data.get("payload", {}).get("scenario", "Hard Question")
                    
                    # Determine answer and score based on scenario
                    answer = "Paris"
                    if scenario == "Easy Question":
                        score = 0.95
                    elif scenario == "Hard Question":
                        score = 0.40 if device_id == "phone" else 0.95
                    elif scenario == "Disagreement":
                        score = 0.40 if device_id == "phone" else 0.95
                        if device_id == "tablet":
                            answer = "Berlin"
                            
                    # Simulate Token Stream
                    if answer == "Paris":
                        tokens = ["The", " capital", " of", " France", " is", " Paris", "."]
                    else:
                        tokens = ["I", " think", " it", " is", " Berlin", "."]
                    
                    # Phone might be faster but less confident
                    delay = 0.2 if device_id == "phone" else 0.4
                    
                    for token in tokens:
                        await websocket.send(json.dumps({
                            "type": "token_stream",
                            "payload": {"token": token}
                        }))
                        print(token, end="", flush=True)
                        await asyncio.sleep(delay + random.uniform(-0.1, 0.1))
                        
                    print() # newline
                    
                    print(f"[{device_id}] Done. Score: {score:.2f}")
                    
                    await websocket.send(json.dumps({
                        "type": "final_answer",
                        "payload": {
                            "answer": answer,
                            "quorum_score": score
                        }
                    }))
                    
                    await websocket.send(json.dumps({
                        "type": "state_update",
                        "payload": {"status": "DONE"}
                    }))
                    
    except websockets.exceptions.ConnectionClosed:
        print(f"[{device_id}] Connection closed.")
    except Exception as e:
        print(f"[{device_id}] Error: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True, help="Device ID (phone, laptop, tablet)")
    parser.add_argument("--url", default="ws://localhost:8000/ws/device", help="Coordinator WS URL")
    args = parser.parse_args()
    
    url = f"{args.url}/{args.id}"
    asyncio.run(run_client(args.id, url))
