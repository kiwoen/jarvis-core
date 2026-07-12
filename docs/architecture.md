# JARVIS Architecture

## The Vision

JARVIS (Just A Rather Very Intelligent System) is not a chatbot, not a coding assistant,
not a research tool. It is an operating system for your entire digital existence.

Every AI product today is a point solution:
- ChatGPT for chat
- Copilot for code
- Midjourney for images
- Siri for reminders

JARVIS is the unification layer. One intelligence, everywhere.

## Design Principles

### 1. Universal Domain Model

A domain is a self-contained area of human activity. Each domain has:
- **Capabilities**: What it can do
- **Memory**: Its own knowledge base
- **Tools**: The instruments it uses
- **Evolution**: How it gets better over time

Domains are NOT plugins. They are limbs of a single intelligence.

### 2. Intent-Driven Execution

User says: "Remind me to buy milk when I leave the house"

JARVIS:
1. Intent Parser: Personal domain, action=reminder, entities={milk, leave house}
2. Domain Router: → Personal domain
3. Personal domain handles: creates geofence reminder
4. Memory: stores the context
5. Evolution: learns that this user sets location-based reminders

### 3. Self-Evolution

Every interaction feeds back into the system:
- Prompts are optimized for success rate
- Models are selected for speed vs. quality trade-offs
- New capabilities are proposed when gaps are detected

This is the key differentiator: JARVIS gets smarter with use.

### 4. Secure by Design

- All generated code runs in isolated sandboxes
- Memory is encrypted at rest
- Network access is denied by default for code execution
- Audit logging for compliance
- Authentication required for sensitive operations

## Data Flow

```
User Input (text/voice/image)
    │
    ▼
Intent Parser ──→ Domain Router ──→ Domain Module
    │                                    │
    │◄── Memory Engine (context)─────    │
    │                                    │
    ▼                                    ▼
Orchestrator ◄──────────────────── Task Result
    │
    ├──→ Evolution Engine (learn)
    ├──→ Memory Engine (store)
    └──→ User Output (text/voice/card)
```

## Key Innovations

### 1. Intent Fusion
Rather than rigid "intent classification," JARVIS uses a cascade:
1. Fast keyword matching for 90% of cases
2. Semantic embedding for ambiguous intents
3. Conversation history disambiguation

This means it can handle "帮我查一下" (ambiguous) and "分析Q3财报趋势"
(specific) with equal reliability.

### 2. Progressive Loading
Domains are loaded progressively: core first, then domains on-demand.
A cold start initializes < 200ms. Full domain loading with ChromaDB takes
< 3 seconds. This matters for resource-constrained edge deployments.

### 3. Memory Compression
Episodic memory (conversation history) is automatically compressed when
it exceeds thresholds. JARVIS summarizes old conversations into semantic
facts, preserving knowledge while reducing context window cost.

This enables effectively infinite conversation memory at near-constant token cost.

### 4. Domain Healing
When a domain module fails, JARVIS:
1. Isolates the failure (doesn't crash other domains)
2. Logs the error for debugging
3. Attempts automatic recovery (restart module, reload tools)
4. Learns from the failure pattern

## Future Directions

### Phase 1: Foundation (Current)
- 8-domain architecture with basic handlers
- Memory engine with compression
- Evolution engine with prompt optimization
- REST + WebSocket API
- Docker sandbox for code execution

### Phase 2: Intelligence
- Cross-domain inference (e.g., "prepare a financial report for the health project")
- Multi-modal input (image, voice, document)
- Active learning (asking clarifying questions to improve)
- Personality adaptation (learning user communication style)

### Phase 3: Autonomy
- Scheduled proactive tasks (daily briefings, health check-ins)
- Goal decomposition (user says "save $10k" → JARVIS breaks into weekly budget actions)
- Inter-agent collaboration (multiple JARVIS instances coordinating)
- Self-hosting (JARVIS manages its own infrastructure)

### Phase 4: Pervasive
- Edge deployment (Raspberry Pi, smart glasses)
- IoT orchestration (full home/office automation)
- AR/VR integration (spatial computing companion)
- Biometric integration (health monitoring from wearables)

## Technical Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Orchestration | Python 3.11+ asyncio | Speed, ecosystem, readability |
| Memory | ChromaDB + SQLite | Fast vector search, local-first |
| API | FastAPI + WebSocket | Performance, async-native |
| Sandbox | Docker / Podman | Battle-tested isolation |
| LLM Router | LiteLLM | Multi-provider, cost optimization |
| Evolution | TextGrad | Gradient-free prompt optimization |
| Testing | pytest + mypy | Type safety, reliability |
| Packaging | setuptools + pyproject.toml | Modern Python standards |
