Quorum
An edge-first inference system that routes AI queries to the cheapest device that can answer them confidently, and only escalates to bigger hardware when it has to.

The Problem
Most companies building AI tools today are stuck picking between two bad options.

Send every query to a cloud API, and you get strong accuracy but you pay for it on every single request, you take on latency, and you send your data outside your own walls. For a law firm reviewing contracts, a clinic handling patient notes, or a financial advisor looking at client records, that last part isn't just inconvenient. It's often not allowed.

Run everything locally on one big model instead, and you avoid the data problem, but now you need serious hardware to handle even simple questions, most of which didn't need a large model in the first place.

Neither option matches how queries actually show up in practice. The vast majority of what a company's AI assistant gets asked is simple: routine lookups, summaries, straightforward drafting. A small fraction is genuinely hard. Today's systems don't tell the difference. They either always pay full price, or they never can afford to.

The Solution
Quorum treats a small local device as a first responder, not a full solution.

A phone-tier model answers first. It also scores its own confidence using self-consistency: it samples the same question multiple times and checks how often it agrees with itself. If it's confident, the answer goes out immediately, fast and nearly free. If it's not, the question escalates automatically to a swarm of larger local devices, which reason independently and vote on a final answer.

Nothing leaves the building at any point. The company owns every device in the chain.

This means most queries get answered in milliseconds by hardware that costs very little, and only the genuinely hard ones pay the cost of a bigger model, on the same local network, under the same compliance boundary.

Who This Is For
Quorum is built for companies that need AI assistance but can't send their data to a cloud API: law firms, clinics, financial advisors, and other regulated businesses that are currently choosing between no AI and risky AI.

It isn't a device. It's the routing layer a company installs on hardware it already owns, small edge devices for the common case, a modest local server for the hard case, with the coordinator deciding which one handles each query in real time.

How It Works
A prompt comes in and goes to the Scout, a small model running on an edge device.
The Scout samples its own answer multiple times and checks agreement across samples.
High agreement means high confidence. The answer is returned immediately.
Low agreement triggers escalation. The prompt is sent to a swarm of larger local devices.
The swarm answers independently, and a consensus engine resolves the group's answer through majority vote with confidence-based tie-breaking.
Every step is logged and shown live on a dashboard: which device answered, how confident it was, whether it escalated, and how long it took.
What's Real Right Now
The full pipeline runs end to end on physical hardware: a Snapdragon phone running the Scout model over ADB, a laptop running the swarm tier, and a coordinator that manages state, escalation, and consensus between them. The dashboard shows live token streams, per-device latency, and a running history of every query the system has handled.

What This Is Not
This is not a claim that small models are secretly as good as large ones. It's a claim that most queries don't need a large model at all, and the ones that do can be identified and routed there automatically, instead of paying the large-model cost on everything by default.

