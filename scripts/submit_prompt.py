import asyncio
import websockets
import json

async def trigger():
    uri = "ws://127.0.0.1:8080/ws/dashboard"
    async with websockets.connect(uri) as websocket:
        # Dashboard connects
        print("Connected to dashboard")
        
        # Send start command
        await websocket.send(json.dumps({
            "type": "start_inference",
            "payload": {"prompt": "A bat and a ball cost $1.10 in total. The bat costs $1.00 more than the ball. How much does the ball cost?"}
        }))
        print("Triggered inference!")
        
        # Keep listening for a bit to see the output
        try:
            while True:
                msg = await websocket.recv()
                data = json.loads(msg)
                
                if data.get("type") == "consensus_result":
                    print("\n\n>>> CONSENSUS REACHED:", data["result"])
                    break
                elif data.get("source_device"):
                    print(f"[{data['source_device']}] {data['data']}")
                else:
                    print("[Coordinator]", data)
        except Exception as e:
            pass

asyncio.run(trigger())
