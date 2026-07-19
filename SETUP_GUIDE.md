# Quorum Hardware Setup Guide

This guide provides step-by-step instructions for running the Quorum distributed reasoning system across a physical laptop and a physical Snapdragon-powered phone.

---

## 1. Architecture Overview

To run Quorum successfully, you need three main components running simultaneously:
1. **The Coordinator & Dashboard (Laptop)**: The central brain that hosts the FastAPI WebSocket server and the React UI.
2. **The Swarm Devices (Laptop)**: Local Python scripts simulating the "Laptop" node for the consensus swarm.
3. **The physical Phone (Snapdragon)**: The initial "Scout" device that evaluates the prompt first using its NPU.

> [!TIP]
> For a 24-hour hackathon, we highly recommend the **ADB Host Approach**. Instead of attempting to install Python and WebSockets directly onto the Android OS, you will run the phone's Python client on your laptop. That script will use a USB cable and ADB to remotely execute the Qualcomm model natively on the phone's NPU and stream the tokens back.

---

## 2. Prerequisites

**On your Laptop:**
- Python 3.10+
- Node.js & npm (for the React Dashboard)
- Android Debug Bridge (ADB) installed and added to your system PATH.
- Qualcomm AI Hub SDK (`qai-hub-models`) installed in your Python environment.

**On your Phone:**
- A Qualcomm Snapdragon device with a Hexagon NPU.
- Developer Options & USB Debugging enabled.

---

## 3. Phone Preparation (AI Hub Export)

Before running Quorum, you must export a quantized model (e.g., Qwen 2.5 1.5B) for your specific Snapdragon chipset using the Qualcomm AI Hub.

1. **Compile the model**: Follow the Qualcomm AI Hub documentation to compile the model to the `.bin` format targeting your exact device.
2. **Connect the phone**: Plug your phone into your laptop via USB. Verify the connection by running:
   ```bash
   adb devices
   ```
3. **Push the model to the phone**:
   Move the compiled model files and the `genie-t2t-run` binary (if required by your execution provider) into a temporary execution folder on the phone.
   ```bash
   adb shell mkdir -p /data/local/tmp/quorum_model
   adb push ./exported_model_dir /data/local/tmp/quorum_model
   ```

---

## 4. Laptop Setup (Coordinator & UI)

Open your terminal and navigate to your `quorum` project directory.

**1. Start the FastAPI Coordinator**
```bash
# Terminal 1
python -m uvicorn coordinator.main:app --host 0.0.0.0 --port 8080
```

**2. Start the React Dashboard**
```bash
# Terminal 2
cd dashboard
npm install
npm run dev
```
Open your browser to `http://localhost:5173` to view the UI.

---

## 5. Starting the Swarm

With the coordinator and dashboard running, it's time to connect the devices.

**1. Start the Laptop Node (Mock)**
These act as your escalation swarm. They don't need real NPU execution for the demo to prove the networking architecture.
```bash
python clients/mock_client.py --id laptop
```

**2. Start the Physical Phone Node (Real NPU)**
Open `clients/genie_client.py` and ensure the `subprocess.Popen` block on line 31 is configured to use ADB to execute the model natively on the phone.

*Modify `genie_client.py` to look like this:*
```python
# Launch the REAL Genie binary on the phone via ADB
process = subprocess.Popen(
    ["adb", "shell", "genie-t2t-run", "--model", "/data/local/tmp/quorum_model", "--prompt", f'"{prompt}"'],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=1 # Line buffered
)
```

Then, run the client from your laptop:
```bash
# Terminal 5
python clients/genie_client.py --id phone
```

> [!IMPORTANT]  
> Watch the React Dashboard! As soon as you run the above commands, you should see the Laptop and Phone transition from `OFFLINE` to `SLEEPING`.

---

## 6. Running the Demo

1. In the React Dashboard, click **⚙ Demo Mode** to reveal the scenario dropdown.
2. Select **Hard Question (Escalation)** to demonstrate the full system.
3. Type a prompt (e.g., *"What is the capital of France?"*) and click **Ask Quorum**.

**What will happen:**
- The Coordinator commands the `phone` client to begin.
- The `phone` client fires the ADB command through the USB cable.
- The Snapdragon NPU processes the prompt and streams tokens back to the laptop via ADB stdout.
- `genie_client.py` intercepts the tokens and streams them over WebSockets to the Coordinator.
- The dashboard animates the token stream live.
- Because it's a "Hard" question, the confidence score is low. The system automatically escalates, waking up the Laptop to achieve consensus.
