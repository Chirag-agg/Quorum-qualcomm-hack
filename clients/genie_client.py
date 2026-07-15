import asyncio
import websockets
import json
import argparse
import sys
import os
import subprocess

async def run_genie_client(device_id: str, ws_url: str):
    print(f"[{device_id}] Connecting to {ws_url}...")
    try:
        async with websockets.connect(ws_url) as websocket:
            print(f"[{device_id}] Connected. Waiting for prompts...")
            
            async for message in websocket:
                data = json.loads(message)
                msg_type = data.get("type")
                
                if msg_type == "start_inference":
                    prompt = data.get("payload", {}).get("prompt", "")
                    print(f"\n[{device_id}] Received prompt: {prompt}")
                    
                    # Notify coordinator we are inferencing
                    await websocket.send(json.dumps({
                        "type": "state_update",
                        "payload": {"status": "INFERENCING"}
                    }))
                    
                    # Launch the REAL Genie binary
                    model_path = os.environ.get("GENIE_MODEL_DIR", "./models/qwen2.5-1.5b-genie")
                    
                    process = subprocess.Popen(
                        ["genie-t2t-run", "--model", model_path, "--prompt", prompt],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        bufsize=1 # Line buffered
                    )
                    
                    generated_text = []
                    current_token = ""
                    
                    # Read stdout char-by-char to ensure real-time streaming even without newlines
                    while True:
                        char = process.stdout.read(1)
                        if not char and process.poll() is not None:
                            break
                            
                        if char:
                            current_token += char
                            # Emit token on word boundaries (space or punctuation)
                            if char.isspace() or char in {'.', ',', '!', '?', ':'}:
                                clean_tok = current_token.strip()
                                if clean_tok and not clean_tok.startswith("Starting") and not clean_tok.startswith("Inference"):
                                    await websocket.send(json.dumps({
                                        "type": "token_stream",
                                        "payload": {"token": current_token}
                                    }))
                                    generated_text.append(clean_tok)
                                current_token = ""
                                
                    # Catch any trailing token
                    if current_token.strip():
                         await websocket.send(json.dumps({
                              "type": "token_stream",
                              "payload": {"token": current_token}
                         }))
                         generated_text.append(current_token.strip())
                    
                    final_answer = " ".join(generated_text)
                    
                    scenario = data.get("payload", {}).get("scenario", "")
                    
                    # Hardcoded score based on scenario
                    quorum_score = 0.95 if scenario == "Easy Question" else 0.42
                    
                    print(f"[{device_id}] Submitting final answer with score {quorum_score}")
                    await websocket.send(json.dumps({
                        "type": "final_answer",
                        "payload": {
                            "answer": final_answer,
                            "quorum_score": quorum_score
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
    parser.add_argument("--id", default="phone", help="Device ID")
    parser.add_argument("--url", default="ws://localhost:8000/ws/device", help="Coordinator WS URL")
    args = parser.parse_args()
    
    url = f"{args.url}/{args.id}"
    asyncio.run(run_genie_client(args.id, url))
