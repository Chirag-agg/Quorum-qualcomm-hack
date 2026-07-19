import asyncio
import websockets
import json
import argparse
import sys
import os
import re
import requests
from collections import Counter

def normalize_answer(answer: str) -> str:
    return re.sub(r'\s+', ' ', answer.strip().lower())

def fetch_sample(geniex_url: str, prompt: str) -> str:
    headers = {"Content-Type": "application/json"}
    payload = {
        "model": "qualcomm/Qwen3-4B-Instruct-2507",
        "messages": [{"role": "user", "content": prompt}]
    }
    
    if not geniex_url.endswith("/v1/chat/completions"):
        geniex_url = geniex_url.rstrip("/") + "/v1/chat/completions"
        
    resp = requests.post(geniex_url, json=payload, headers=headers, timeout=300)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]

async def run_swarm_genie_client(device_id: str, ws_url: str, geniex_url: str):
    print(f"[{device_id}] Connecting to {ws_url}...")
    try:
        async with websockets.connect(ws_url) as websocket:
            print(f"[{device_id}] Connected. Waiting for wake events...")
            
            async for message in websocket:
                data = json.loads(message)
                msg_type = data.get("type")
                
                # Only activate on the "wake" message type
                if msg_type == "wake":
                    payload_data = data.get("payload", {})
                    prompt = payload_data.get("prompt", "")
                    print(f"\n[{device_id}] Received wake prompt: {prompt}")
                    
                    # Notify coordinator we are inferencing
                    await websocket.send(json.dumps({
                        "type": "state_update",
                        "payload": {"status": "INFERENCING"}
                    }))
                    
                    try:
                        N = int(os.environ.get("GENIE_SAMPLES", "3"))
                        answers = []
                        normalized_answers = []
                        
                        jitters = ["", "\nThink carefully.", "\nDouble check your logic.", "\nBe accurate.", "\n"]
                        engineered_prompt = prompt + "\nGive a short, direct answer. Do not explain."
                        
                        for i in range(N):
                            jitter_text = jitters[i % len(jitters)]
                            jittered_prompt = f"{engineered_prompt}{jitter_text}"
                            
                            # POST standard OpenAI chat format to GenieX local server in a thread to avoid blocking the event loop
                            final_answer = await asyncio.to_thread(fetch_sample, geniex_url, jittered_prompt)
                            print(f"[{device_id}] Raw answer {i+1}:\n{final_answer}\n")
                            answers.append(final_answer)
                            normalized_answers.append(normalize_answer(final_answer))
                        
                        # Self-consistency scoring logic
                        counts = Counter(normalized_answers)
                        majority_norm, majority_count = counts.most_common(1)[0]
                        # The laptop is the authoritative fallback, so it always returns High Confidence
                        quorum_score = 1.0
                        
                        # dict-keyed-by-normalized-answer approach (reuse winner-selection logic)
                        norm_to_orig = {}
                        for orig, norm in zip(answers, normalized_answers):
                            if norm not in norm_to_orig:
                                norm_to_orig[norm] = orig
                                
                        majority_ans = norm_to_orig[majority_norm]
                        
                        # Path used: chunked-fake-streaming pattern
                        # Real SSE streaming cannot be cleanly done while waiting for N samples to finish for majority voting.
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
                                "answer": f"ERROR: inference failed - {str(e)}",
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
    parser.add_argument("--url", default="ws://localhost:8080/ws/device", help="Coordinator WS URL")
    parser.add_argument("--geniex-url", default="http://127.0.0.1:18181/v1/chat/completions", help="GenieX OpenAI-compatible endpoint URL")
    args = parser.parse_args()
    
    url = f"{args.url}/{args.id}"
    asyncio.run(run_swarm_genie_client(args.id, url, args.geniex_url))
