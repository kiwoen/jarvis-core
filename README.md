"""
JARVIS — Just A Rather Very Intelligent System
===============================================

A multi-domain autonomous AI orchestrator. Think Iron Man's J.A.R.V.I.S.,
but real — it operates across every domain of human life, not as a tool,
but as a digital extension of its user.

Philosophy
----------

    "J.A.R.V.I.S. is more than a butler. It's a partner."

This is NOT a chatbot, NOT a Copilot wrapper, NOT a single-purpose agent.
JARVIS is an operating system for your digital life — it manages your
schedule, writes your code, researches problems, creates content, monitors
your security, tracks your health, advises your finances, and controls
your home.

And most importantly — it learns. Every interaction makes it better.

Architecture
------------

    ┌─────────────────────────────────────────────────────┐
    │                   CONTROL PLANE                      │
    │  ┌─────────────┐  ┌──────────┐  ┌──────────────┐   │
    │  │  Orchestrator│  │ Config   │  │ API Server   │   │
    │  └──────┬───────┘  └──────────┘  └──────────────┘   │
    ├─────────┼───────────────────────────────────────────┤
    │         │         EXECUTION ENGINE                   │
    │  ┌──────▼───────┐ ┌───────┐ ┌───────┐ ┌───────┐    │
    │  │Intent Parser │ │Memory │ │Sandbox│ │Domain │    │
    │  │+Router       │ │Engine │ │Manager│ │Modules│    │
    │  └──────────────┘ └───────┘ └───────┘ └───────┘    │
    ├─────────────────────────────────────────────────────┤
    │                 EVOLUTION ENGINE                     │
    │  ┌──────────────┐ ┌──────────┐ ┌──────────────┐    │
    │  │Prompt        │ │Model     │ │Capability    │    │
    │  │Optimization  │ │Selection │ │Proposer      │    │
    │  └──────────────┘ └──────────┘ └──────────────┘    │
    ├─────────────────────────────────────────────────────┤
    │                 CAPABILITY LAYER                     │
    │  Personal │ Research │ Engineering │ Creator │ ...   │
    │  Security │ Health   │ Finance     │ Home    │       │
    └─────────────────────────────────────────────────────┘

Eight Domains
-------------

1. **Personal** — Scheduling, reminders, email, contacts, notes
2. **Research** — Web search, paper review, data analysis, intelligence
3. **Engineering** — Code gen, debugging, CI/CD, infrastructure
4. **Creator** — Writing, design, video, music, content strategy
5. **Security** — Monitoring, threat detection, vulnerability scanning
6. **Health** — Fitness tracking, sleep analysis, nutrition monitoring
7. **Finance** — Budgeting, investment analysis, portfolio tracking
8. **Home** — IoT control, environment monitoring, smart automation

Each domain is a self-contained module, hot-pluggable at runtime.

Self-Evolution
--------------

JARVIS doesn't just execute — it improves. The Evolution Engine runs
three concurrent optimization loops:

- **L1: Prompt Optimization** — TextGrad-style gradient descent on prompts
- **L2: Model Selection** — A/B testing LLMs per task type for speed/cost/quality
- **L3: Capability Growth** — Proposes new tools/domains from unmet needs

Quick Start
-----------

```bash
# Install
pip install -e ".[dev]"

# Run CLI
python -m jarvis.main

# Run API server
uvicorn jarvis.api.server:app --reload

# Run tests
pytest tests/ -v
```

Project Structure
-----------------

```
jarvis-core/
├── jarvis/
│   ├── __init__.py          # Package identity
│   ├── main.py              # Entry point
│   ├── core/
│   │   ├── orchestrator.py  # Master controller
│   │   └── config.py        # Configuration system
│   ├── memory/
│   │   └── engine.py        # Hybrid memory (episodic/semantic)
│   ├── evolution/
│   │   └── controller.py    # Self-evolution engine
│   ├── sandbox/
│   │   └── __init__.py      # Secure code execution
│   ├── api/
│   │   └── server.py        # FastAPI REST + WebSocket
│   └── domains/
│       ├── personal/        # Personal assistant
│       ├── research/        # Research & analytics
│       ├── engineering/     # Software engineering
│       ├── creator/         # Content creation
│       ├── security/        # Security monitoring
│       ├── health/          # Health & wellness
│       ├── finance/         # Finance & investment
│       └── home/            # Home automation
├── tests/
│   └── test_core.py         # Core tests
├── docs/
│   └── architecture.md      # Full architecture docs
├── pyproject.toml           # Project config
└── README.md                # This file
```

License
-------

MIT — Build something great.
