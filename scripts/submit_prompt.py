import asyncio
import websockets
import json

async def trigger():
    uri = "ws://localhost:8000/ws/dashboard"
    async with websockets.connect(uri) as websocket:
        # Dashboard connects, receives init
        init_msg = await websocket.recv()
        print("Received init:", init_msg)
        
        # Send start command
        await websocket.send(json.dumps({
            "type": "start_inference",
            "payload": {"prompt": "What is the capital of France?"}
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
