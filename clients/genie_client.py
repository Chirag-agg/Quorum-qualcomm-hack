import asyncio
import websockets
import json
import argparse
import sys
import os
import subprocess
import re
import tempfile
from collections import Counter

def normalize_answer(answer: str) -> str:
    """Simple normalization: strip whitespace and lowercase."""
    return re.sub(r'\s+', ' ', answer.strip().lower())

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
                    
                    try:
                        N = int(os.environ.get("GENIE_SAMPLES", "3"))
                        answers = []
                        
                        model_dir = os.environ.get("GENIE_MODEL_DIR", "/data/local/tmp/qwen2.5-1.5b-genie")
                        config_file = os.environ.get("GENIE_CONFIG_FILE", "genie_config.json")
                        
                        # Manually wrap with chat template
                        wrapped_prompt = f"<|im_start|>user\n{prompt} /no_think<|im_end|>\n<|im_start|>assistant\n"
                        
                        # Write wrapped prompt to a local temp file (no BOM)
                        # UTF-8 in Python does not write a BOM, so we use ascii or utf-8
                        with tempfile.NamedTemporaryFile(mode='w', encoding='ascii', delete=False) as f:
                            f.write(wrapped_prompt)
                            local_path = f.name
                        
                        device_prompt_path = "/data/local/tmp/prompt_temp.txt"
                        
                        # Push the prompt file via adb push
                        subprocess.run(["adb", "push", local_path, device_prompt_path], check=True)
                        os.remove(local_path)
                        
                        model_basename = os.path.basename(model_dir.rstrip('/'))
                        adsp_path = f"/data/local/tmp/{model_basename}/"
                        
                        cmd_str = (
                            f"export LD_LIBRARY_PATH=/data/local/tmp/qairt/aarch64-android && "
                            f"export ADSP_LIBRARY_PATH={adsp_path} && "
                            f"cd {model_dir} && "
                            f"/data/local/tmp/genie-t2t-run -c {config_file} --prompt_file {device_prompt_path}"
                        )
                        
                        for i in range(N):
                            # We rely on temp=0.7/top-p=0.95 alone for sample diversity since seed variation
                            # isn't straightforward without rewriting the config file per run.
                            result = subprocess.run(["adb", "shell", cmd_str], capture_output=True, text=True)
                            output = result.stdout
                            
                            # Parse stdout per rules
                            if "[BEGIN]:" in output:
                                output = output.split("[BEGIN]:", 1)[1]
                            
                            if "[END]" in output:
                                output = output.split("[END]", 1)[0]
                            
                            # Strip any <think>...</think> blocks (even empty ones — they can appear doubled)
                            output = re.sub(r"<think>.*?</think>", "", output, flags=re.DOTALL)
                            
                            final_answer = output.strip()
                            print(f"[{device_id}] Raw answer {i+1}:\n{final_answer}\n")
                            answers.append(final_answer)
                        
                        # Normalize each answer exactly like coordinator/consensus.py
                        normalized_answers = [normalize_answer(a) for a in answers]
                        counts = Counter(normalized_answers)
                        majority_norm, majority_count = counts.most_common(1)[0]
                        quorum_score = majority_count / N
                        
                        # Find original majority answer
                        majority_ans = next(a for a, norm in zip(answers, normalized_answers) if norm == majority_norm)
                        
                        # Since genie-t2t-run doesn't stream token-by-token over ADB in a way we can easily tap mid-generation,
                        # keep sending token_stream WebSocket events by chunking the final parsed answer into word-sized pieces 
                        # with a small artificial delay, so the dashboard still animates - this is a known limitation, not real token streaming.
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
    parser.add_argument("--id", default="phone", help="Device ID")
    parser.add_argument("--url", default="ws://localhost:8000/ws/device", help="Coordinator WS URL")
    args = parser.parse_args()
    
    url = f"{args.url}/{args.id}"
    asyncio.run(run_genie_client(args.id, url))
