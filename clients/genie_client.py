import asyncio
import websockets
import json
import argparse
import sys
import os
import subprocess
import re
import tempfile
import random
import time
import functools
import copy
from collections import Counter

# Flush all print statements immediately for reliable real-time logging
print = functools.partial(print, flush=True)

ADB_PATH = os.environ.get("ADB_EXECUTABLE", r"C:\Users\qcwor\platform-tools-latest-windows\platform-tools\adb.exe")

def normalize_answer(answer: str) -> str:
    """Simple normalization: strip whitespace and lowercase."""
    return re.sub(r'\s+', ' ', answer.strip().lower())

def is_degenerate_repetition(text: str) -> bool:
    """
    Detects if a phrase of 5+ words is repeated consecutively 4+ times.
    Uses regex as requested by Step 2(c), and a list-based check for robustness.
    """
    if not text:
        return False
    
    # Lowercase and replace punctuation with spaces
    text_lower = text.lower()
    text_no_punc = re.sub(r'[^\w\s]', ' ', text_lower)
    text_normalized = re.sub(r'\s+', ' ', text_no_punc).strip()
    
    # 1. Regex check on normalized text
    # Regex: captures a group of 5+ words, followed by 3+ consecutive repetitions of that same group
    # (\w+(?:\s+\w+){4,}) matches 1 word + at least 4 space-separated words = 5+ words
    # (?:\s+\1){3,} matches at least 3 subsequent copies of that group
    pattern = re.compile(r'\b(\w+(?:\s+\w+){4,})(?:\s+\1){3,}', re.IGNORECASE)
    if bool(pattern.search(text_normalized)):
        return True
        
    # 2. Substring/list check on words
    words = text_normalized.split()
    n = len(words)
    if n >= 20:
        for L in range(5, n // 4 + 1):
            for i in range(n - 4 * L + 1):
                phrase = words[i : i+L]
                if (words[i+L : i+2*L] == phrase and
                    words[i+2*L : i+3*L] == phrase and
                    words[i+3*L : i+4*L] == phrase):
                    return True
                    
    return False

async def run_genie_client(device_id: str, ws_url: str):
    print(f"[{device_id}] Connecting to {ws_url}...")
    try:
        async with websockets.connect(ws_url, ping_interval=None, ping_timeout=None) as websocket:
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
                        N = int(os.environ.get("GENIE_SAMPLES", "4"))
                        answers = []
                        jitters = ["", "\nThink carefully.", "\nDouble check your logic.", "\nBe accurate.", "\n"]
                        
                        model_dir = os.environ.get("GENIE_MODEL_DIR", "/data/local/tmp/qwen3_1_7b-geniex_qairt-w4a16-qualcomm_snapdragon_8_elite_gen5")
                        config_file = os.environ.get("GENIE_CONFIG_FILE", "genie_config.json")
                        device_prompt_path = "/data/local/tmp/prompt_temp.txt"
                        
                        model_basename = os.path.basename(model_dir.rstrip('/'))
                        adsp_path = f"/data/local/tmp/{model_basename}/"
                        
                        cmd_str = (
                            f"export LD_LIBRARY_PATH=/data/local/tmp/qairt/aarch64-android && "
                            f"export ADSP_LIBRARY_PATH={adsp_path} && "
                            f"cd {model_dir} && "
                            f"/data/local/tmp/genie-t2t-run -c {config_file} --prompt_file {device_prompt_path}"
                        )
                        
                        device_config_path = f"{model_dir}/{config_file}"
                        config_data = {}
                        
                        # Try to read the config locally if it exists
                        if os.path.exists(config_file):
                            try:
                                with open(config_file, "r", encoding="utf-8") as f:
                                    config_data = json.load(f)
                            except Exception as e:
                                print(f"[{device_id}] Error reading local config file {config_file}: {e}")
                        
                        # If not found or failed, try pulling from the device once before the loop
                        if not config_data:
                            try:
                                # Pull to a temporary file to keep the workspace clean
                                with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp_f:
                                    tmp_pull_path = tmp_f.name
                                await asyncio.to_thread(
                                    subprocess.run,
                                    [ADB_PATH, "pull", device_config_path, tmp_pull_path],
                                    capture_output=True,
                                    check=True
                                )
                                with open(tmp_pull_path, "r", encoding="utf-8") as f:
                                    config_data = json.load(f)
                                os.remove(tmp_pull_path)
                            except Exception as e:
                                print(f"[{device_id}] Error pulling config from device {device_config_path}: {e}")
                        
                        # Ensure config_data is a dictionary
                        if not isinstance(config_data, dict):
                            config_data = {}
                            
                        if not config_data:
                            # Fallback basic structure if we couldn't load config at all
                            config_data = {
                                "dialog": {
                                    "version": 1,
                                    "type": "basic",
                                    "context": {
                                        "version": 1,
                                        "size": 4096,
                                        "n-vocab": 151936,
                                        "bos-token": 151643,
                                        "eos-token": 151645
                                    },
                                    "sampler": {
                                        "version": 1,
                                        "seed": 12345,
                                        "temp": 0.7,
                                        "top-k": 40,
                                        "top-p": 0.95
                                    },
                                    "tokenizer": {
                                        "version": 1,
                                        "path": "tokenizer.json"
                                    }
                                }
                            }
                            
                        # Clean up sampler block from unsupported repeat-penalty key if present to prevent crash
                        if "sampler" in config_data and isinstance(config_data["sampler"], dict):
                            config_data["sampler"].pop("repeat-penalty", None)
                        if "dialog" in config_data and isinstance(config_data["dialog"], dict):
                            if "sampler" in config_data["dialog"] and isinstance(config_data["dialog"]["sampler"], dict):
                                config_data["dialog"]["sampler"].pop("repeat-penalty", None)
                                
                        # Supplementary mitigations for repetition collapse (confirmed supported keys)
                        if "dialog" in config_data and isinstance(config_data["dialog"], dict):
                            config_data["dialog"]["max-num-tokens"] = 512
                            config_data["dialog"]["stop-sequence"] = ["<|im_end|>", "<|im_start|>"]
                            
                            # Artificially boost temperature to simulate logprob entropy via jittering
                            if "sampler" in config_data["dialog"] and isinstance(config_data["dialog"]["sampler"], dict):
                                config_data["dialog"]["sampler"]["temp"] = 0.95
                        elif "sampler" in config_data and isinstance(config_data["sampler"], dict):
                            config_data["sampler"]["temp"] = 0.95
                        
                        for i in range(N):
                            sample_start_time = time.perf_counter()
                            
                            # 1. Jitter Prompt and Push
                            jitter_text = jitters[i % len(jitters)]
                            jittered_prompt = f"{prompt}{jitter_text}"
                            wrapped_prompt = f"<|im_start|>user\n{jittered_prompt} /no_think<|im_end|>\n<|im_start|>assistant\n"
                            
                            with tempfile.NamedTemporaryFile(mode='w', encoding='ascii', delete=False) as f:
                                f.write(wrapped_prompt)
                                local_path = f.name
                                
                            try:
                                await asyncio.to_thread(subprocess.run, [ADB_PATH, "push", local_path, device_prompt_path], check=True, capture_output=True)
                            except Exception as e:
                                print(f"[{device_id}] Error pushing prompt: {e}")
                            finally:
                                os.remove(local_path)
                            
                            # 2. Generate a unique seed for this sample
                            new_seed = random.randint(0, 2**31 - 1)
                            
                            # Deep copy config_data so we don't accumulate changes across loop iterations
                            sample_config = copy.deepcopy(config_data)
                            
                            # Overwrite seed where it exists to support different schema variants without adding unused nested blocks
                            seed_updated = False
                            if "seed" in sample_config:
                                sample_config["seed"] = new_seed
                                seed_updated = True
                            
                            if "sampler" in sample_config and isinstance(sample_config["sampler"], dict):
                                if "seed" in sample_config["sampler"]:
                                    sample_config["sampler"]["seed"] = new_seed
                                    seed_updated = True
                            
                            if "dialog" in sample_config and isinstance(sample_config["dialog"], dict):
                                if "sampler" in sample_config["dialog"] and isinstance(sample_config["dialog"]["sampler"], dict):
                                    if "seed" in sample_config["dialog"]["sampler"]:
                                        sample_config["dialog"]["sampler"]["seed"] = new_seed
                                        seed_updated = True
                                        
                            if not seed_updated:
                                sample_config["seed"] = new_seed
                                
                            # Write config to a local temp file to keep workspace clean
                            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.json', delete=False) as tmp_f:
                                json.dump(sample_config, tmp_f, indent=4)
                                tmp_config_path = tmp_f.name
                                
                            # Push config to phone
                            try:
                                await asyncio.to_thread(subprocess.run, [ADB_PATH, "push", tmp_config_path, device_config_path], check=True, capture_output=True)
                            except Exception as e:
                                print(f"[{device_id}] Error pushing config to device: {e}")
                            
                            # Clean up the local temp config file immediately
                            try:
                                os.remove(tmp_config_path)
                            except Exception as e:
                                pass
                            
                            # Run the inference subprocess
                            result = await asyncio.to_thread(subprocess.run, [ADB_PATH, "shell", cmd_str], capture_output=True, text=True)
                            exit_code = result.returncode
                            stdout_val = result.stdout if result.stdout else ""
                            stderr_val = result.stderr if result.stderr else ""
                            
                            elapsed_time = time.perf_counter() - sample_start_time
                            
                            # Parse stdout per rules
                            output = stdout_val
                            if "[BEGIN]:" in output:
                                output = output.split("[BEGIN]:", 1)[1]
                            
                            if "[END]" in output:
                                output = output.split("[END]", 1)[0]
                            
                            # Strip any <think>...</think> blocks (even empty ones — they can appear doubled)
                            stripped_output = re.sub(r"<think>.*?</think>", "", output, flags=re.DOTALL)
                            if not stripped_output.strip():
                                # If stripping think blocks leaves nothing, the answer was entirely inside them.
                                # Remove just the tags instead.
                                output = re.sub(r"</?think>", "", output)
                            else:
                                output = re.sub(r"</?think>", "", stripped_output)
                            
                            final_answer = output.strip()
                            
                            # Validation
                            crashed = (exit_code != 0)
                            is_empty = (not final_answer)
                            is_degenerate = False
                            if not crashed and not is_empty:
                                is_degenerate = is_degenerate_repetition(final_answer)
                            
                            # STEP 3: Verification instrumentation logging per sample
                            print(f"[{device_id}] Sample {i+1}/{N}:")
                            print(f"[{device_id}]   - Raw Seed: {new_seed}")
                            print(f"[{device_id}]   - Elapsed Time: {elapsed_time:.3f} seconds")
                            print(f"[{device_id}]   - Subprocess Exit Code: {exit_code}")
                            print(f"[{device_id}]   - Stdout Empty: {is_empty}")
                            print(f"[{device_id}]   - Degenerate Repetition: {is_degenerate}")
                            if crashed:
                                print(f"[{device_id}]   - Subprocess Stderr:\n{stderr_val}\n")
                            else:
                                print(f"[{device_id}]   - Raw Answer Text:\n{final_answer}\n")
                            
                            if crashed or is_empty or is_degenerate:
                                reason_parts = []
                                if crashed: reason_parts.append("crashed (non-zero exit)")
                                if is_empty: reason_parts.append("empty output")
                                if is_degenerate: reason_parts.append("degenerate repetition")
                                print(f"[{device_id}]   - EXCLUDING Sample {i+1} from majority vote. Reason: {', '.join(reason_parts)}")
                            else:
                                answers.append(final_answer)
                        
                        # Excluded count and logging
                        excluded_count = N - len(answers)
                        if excluded_count > 0:
                            print(f"[{device_id}] Excluded {excluded_count}/{N} samples from the consensus pool.")
                        
                        if len(answers) > 0:
                            # Normalize each answer exactly like coordinator/consensus.py
                            normalized_answers = [normalize_answer(a) for a in answers]
                            counts = Counter(normalized_answers)
                            majority_norm, majority_count = counts.most_common(1)[0]
                            quorum_score = majority_count / len(answers)
                            
                            # Find original majority answer
                            majority_ans = next(a for a, norm in zip(answers, normalized_answers) if norm == majority_norm)
                            
                            if len(answers) == N:
                                print(f"[{device_id}] Final confidence score: {quorum_score:.3f} (computed from full count of {len(answers)}/{N} valid samples)")
                            else:
                                print(f"[{device_id}] Final confidence score: {quorum_score:.3f} (computed from partial count of {len(answers)}/{N} valid samples)")
                        else:
                            # Forced-failure signal
                            majority_ans = "ERROR: all inference samples failed or were degenerate"
                            quorum_score = 0.0
                            print(f"[{device_id}] Forced-failure signal triggered (0/{N} valid samples). Final confidence score: 0.0")
                        
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
                                "quorum_score": quorum_score,
                                "status": "failed" if len(answers) == 0 else "success"
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
                                "quorum_score": 0.0,
                                "status": "failed"
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
    parser.add_argument("--url", default="ws://127.0.0.1:8000/ws/device", help="Coordinator WS URL")
    args = parser.parse_args()
    
    url = f"{args.url}/{args.id}"
    asyncio.run(run_genie_client(args.id, url))
