import asyncio
import websockets
import json
import argparse
import sys
import os
import requests
import re
from collections import Counter

def normalize_answer(answer: str) -> str:
    return re.sub(r'\s+', ' ', answer.strip().lower())

async def run_swarm_genie_client(device_id: str, ws_url: str, geniex_url: str):
    print(f"[{device_id}] Connecting to {ws_url}...")
    try:
        async with websockets.connect(ws_url) as websocket:
            print(f"[{device_id}] Connected. Waiting for wake events...")
            
            async for message in websocket:
                data = json.loads(message)
                msg_type = data.get("type")
                
                # Only activate on the "wake" message type from the coordinator
                if msg_type == "wake":
                    prompt = data.get("payload", {}).get("prompt", "")
                    print(f"\n[{device_id}] Received wake prompt: {prompt}")
                    
                    # Notify coordinator we are inferencing
                    await websocket.send(json.dumps({
                        "type": "state_update",
                        "payload": {"status": "INFERENCING"}
                    }))
                    
                    try:
                        N = int(os.environ.get("GENIE_SAMPLES", "3"))
                        answers = []
                        
                        for i in range(N):
                            # POST standard OpenAI chat format to GenieX local server
                            response = requests.post(
                                geniex_url,
                                json={
                                    "model": "qwen3-4b",
                                    "messages": [{"role": "user", "content": prompt}]
                                },
                                timeout=120
                            )
                            response.raise_for_status()
                            response_json = response.json()
                            final_answer = response_json["choices"][0]["message"]["content"]
                            print(f"[{device_id}] Raw answer {i+1}:\n{final_answer}\n")
                            answers.append(final_answer)
                        
                        # Self-consistency scoring logic
                        normalized_answers = [normalize_answer(a) for a in answers]
                        counts = Counter(normalized_answers)
                        majority_norm, majority_count = counts.most_common(1)[0]
                        quorum_score = majority_count / N
                        
                        # dict-keyed-by-normalized-answer approach
                        norm_to_orig = {}
                        for orig, norm in zip(answers, normalized_answers):
                            if norm not in norm_to_orig:
                                norm_to_orig[norm] = orig
                                
                        majority_ans = norm_to_orig[majority_norm]
                        
                        # Using chunked-fake-streaming pattern since real SSE streaming support 
                        # for this GenieX endpoint wasn't confirmed.
                        chunks = re.findall(r'\S+|\s+', majority_ans)
                        for chunk in chunks:
                            if not chunk:
                                continue
                            await websocket.send(json.dumps({
                                "type": "token_stream",
                                "payload": {"token": chunk}
                            }))
                            await asyncio.sleep(0.02)
                        
                        print(f"[{device_id}] Submitting final answer with score {quorum_score}")
                        await websocket.send(json.dumps({
                            "type": "final_answer",
                            "payload": {
                                "answer": majority_ans,
                                "quorum_score": quorum_score
                            }
                        }))
                        
                        await websocket.send(json.dumps({
                            "type": "state_update",
                            "payload": {"status": "DONE"}
                        }))
                        
                    except Exception as e:
                        print(f"[{device_id}] Error during inference: {e}")
                        await websocket.send(json.dumps({
                            "type": "final_answer",
                            "payload": {
                                "answer": "ERROR: inference failed",
                                "quorum_score": 0.0
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
    parser.add_argument("--id", default="laptop", help="Device ID")
    parser.add_argument("--url", default="ws://localhost:8000/ws/device", help="Coordinator WS URL")
    parser.add_argument("--geniex-url", default="http://127.0.0.1:18181/v1/chat/completions", help="GenieX OpenAI-compatible endpoint URL")
    args = parser.parse_args()
    
    url = f"{args.url}/{args.id}"
    asyncio.run(run_swarm_genie_client(args.id, url, args.geniex_url))
