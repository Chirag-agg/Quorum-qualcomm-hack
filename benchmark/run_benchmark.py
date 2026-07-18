import json
import asyncio
import websockets
import time
import requests
import csv
import os

async def run_quorum(prompt: str):
    uri = "ws://localhost:8000/ws/dashboard"
    try:
        async with websockets.connect(uri) as websocket:
            # Dashboard receives init from coordinator upon connection
            # We must await the first message before sending
            try:
                await asyncio.wait_for(websocket.recv(), timeout=2.0)
            except asyncio.TimeoutError:
                pass
            
            # Send start command
            await websocket.send(json.dumps({
                "type": "start_inference",
                "payload": {"prompt": prompt, "scenario": "Benchmark"}
            }))
            
            # Wait for consensus result
            while True:
                msg = await websocket.recv()
                data = json.loads(msg)
                
                if data.get("type") == "consensus_result":
                    break
                    
        # Fetch run details from session history
        resp = requests.get("http://localhost:8000/session")
        resp.raise_for_status()
        history = resp.json().get("history", [])
        if history:
            last_run = history[-1]
            return {
                "answer": last_run.get("result", ""),
                "latency_ms": last_run.get("latency_ms", 0),
                "escalated": last_run.get("escalated", False),
                "devices_used": last_run.get("devices", 0)
            }
    except Exception as e:
        print(f"Error running quorum for prompt '{prompt}': {e}")
        
    return {"answer": "ERROR", "latency_ms": 0, "escalated": False, "devices_used": 0}

def run_baseline(prompt: str):
    start = time.time()
    try:
        resp = requests.post(
            "http://127.0.0.1:18181/v1/chat/completions",
            json={
                "model": "qwen3-8b",
                "messages": [{"role": "user", "content": prompt}],
                "stream": False
            },
            timeout=120
        )
        resp.raise_for_status()
        answer = resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"Error running baseline for prompt '{prompt}': {e}")
        answer = "ERROR"
        
    latency_ms = int((time.time() - start) * 1000)
    return {"answer": answer, "latency_ms": latency_ms}

async def main():
    questions_file = "benchmark/questions.json"
    if not os.path.exists(questions_file):
        print(f"Error: {questions_file} not found.")
        return
        
    with open(questions_file, "r", encoding="utf-8") as f:
        questions = json.load(f)
        
    results_file = "benchmark/results.csv"
    
    total_quorum_latency = 0
    total_baseline_latency = 0
    total_escalations = 0
    
    with open(results_file, "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = [
            "question", "quorum_latency_ms", "baseline_latency_ms", 
            "devices_used", "escalated", "quorum_answer", "baseline_answer", "correct"
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for i, q in enumerate(questions):
            print(f"Running question {i+1}/{len(questions)}: {q}")
            
            quorum_res = await run_quorum(q)
            baseline_res = run_baseline(q)
            
            total_quorum_latency += quorum_res["latency_ms"]
            total_baseline_latency += baseline_res["latency_ms"]
            if quorum_res["escalated"]:
                total_escalations += 1
                
            writer.writerow({
                "question": q,
                "quorum_latency_ms": quorum_res["latency_ms"],
                "baseline_latency_ms": baseline_res["latency_ms"],
                "devices_used": quorum_res["devices_used"],
                "escalated": "yes" if quorum_res["escalated"] else "no",
                "quorum_answer": quorum_res["answer"].replace('\n', ' '),
                "baseline_answer": baseline_res["answer"].replace('\n', ' '),
                "correct": "" # manual grading
            })
            csvfile.flush()
            print(f"  -> Quorum: {quorum_res['latency_ms']}ms, Baseline: {baseline_res['latency_ms']}ms, Escalated: {quorum_res['escalated']}")
            
    print("\n--- Benchmark Summary ---")
    print(f"Average Quorum Latency: {total_quorum_latency / len(questions):.0f} ms")
    print(f"Average Baseline Latency: {total_baseline_latency / len(questions):.0f} ms")
    print(f"Escalation Rate: {(total_escalations / len(questions)) * 100:.1f}%")

if __name__ == "__main__":
    asyncio.run(main())
