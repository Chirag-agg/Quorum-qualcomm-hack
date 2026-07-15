# Quorum

**An Edge-First Orchestration Architecture for Distributed Model Consensus.**

Quorum is an intelligent inference coordinator built to execute small, quantized AI models on edge hardware (like Snapdragon NPUs). Rather than brute-forcing multi-model consensus, Quorum treats the local device as a *Scout*. It routes inference through a single edge device and calculates confidence locally. Only when the device yields low confidence does Quorum dynamically escalate the task to a distributed swarm of devices for consensus. 

This approach minimizes power consumption, reduces latency on trivial queries, and guarantees robust reasoning on complex ones.

## 🚀 Key Features

* **Edge-First Architecture**: Always attempts local inference first.
* **Dynamic Escalation**: Routes low-confidence responses to secondary/tertiary devices across a WebSocket mesh network.
* **On-Device Hardware Accel**: Integrates natively with `genie-t2t-run` to execute models on Hexagon NPUs via Qualcomm AI Hub.
* **Real-time Live Dashboard**: An enterprise-grade React telemetry dashboard built with Vite, showcasing real-time token streams, state transitions, device-level latency tracking, and a unified benchmark ledger.
* **Pluggable Consensus Engine**: Employs configurable majority-vote logic with tie-breaking quorum thresholds.

## 📦 Project Structure

```text
Quorum/
├── coordinator/           # FastAPI Central Node Orchestrator
│   ├── main.py            # Event loop & WebSocket routers
│   ├── state_machine.py   # Flow state logic (SCOUT -> ESCALATE -> CONSENSUS)
│   ├── consensus.py       # Voting algorithm & confidence evaluation
│   └── logger.py          # Benchmark metrics logger
├── clients/               # Edge device interfaces
│   ├── genie_client.py    # Subprocess wrapper for Snapdragon ADB execution
│   └── mock_client.py     # Simulation clients for swarm nodes
├── dashboard/             # React Telemetry UI (Vite)
└── SETUP_GUIDE.md         # Hardware & Network Integration Manual
```

## 🛠 Tech Stack
* **Orchestration**: Python, FastAPI, WebSockets
* **Edge Inference**: Qualcomm AI Hub SDK, Genie (`genie-t2t-run`)
* **Telemetry Dashboard**: React, Vite, Vanilla CSS

## 📚 Getting Started

To deploy Quorum across your physical hardware, please refer to the detailed [Hardware Setup Guide](SETUP_GUIDE.md).
