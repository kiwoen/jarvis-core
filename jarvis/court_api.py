"""FastAPI REST API server for the Court evolutionary system.

Endpoints:
    GET  /                        — server health
    GET  /court/summary           — court summary
    GET  /court/snapshot          — structured court state
    GET  /court/history           — evolution cycle history
    GET  /court/ministers         — list all ministers
    GET  /court/minister/{name}   — detail for one minister
    POST /court/register          — register a minister
    POST /court/register/batch    — bulk register
    POST /court/evolve            — run N evolution cycles
    POST /court/dispatch          — record a dispatch outcome
    POST /court/feedback          — record external feedback
    POST /court/genomes/save      — persist genomes
    POST /court/genomes/load      — load genomes from file
"""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from jarvis.court.court import Court

_court = Court()

app = FastAPI(title="Emperor Court API", version="0.1.0")


# ── Request models ────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: Optional[str] = None
    domain: str = "general"
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    confidence_baseline: float = Field(default=0.75, ge=0.0, le=1.0)


class BulkRegisterRequest(BaseModel):
    ministers: list[RegisterRequest]


class EvolveRequest(BaseModel):
    cycles: int = Field(default=1, ge=1, le=100)


class DispatchRequest(BaseModel):
    minister: str
    edict_id: str
    intent: str
    success: bool
    confidence: float = Field(ge=0.0, le=1.0)
    execution_time_ms: float = 0.0


class FeedbackRequest(BaseModel):
    minister: str
    edict_id: str
    score: float = Field(ge=0.0, le=1.0)


class GenomeLoadRequest(BaseModel):
    path: str


# ── Endpoints ─────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"service": "emperor-court", "status": "ok"}


@app.get("/court/summary")
def get_summary():
    return {"summary": _court.summary()}


@app.get("/court/snapshot")
def get_snapshot():
    return _court.inspect.snapshot()


@app.get("/court/history")
def get_history():
    records = [_court.history[i] for i in range(len(_court.history))]
    return {"cycles": len(records), "records": records}


@app.get("/court/ministers")
def list_ministers():
    snap = _court.inspect.snapshot()
    active = [m.name for m in snap.ministers if m.status == "active"]
    return {"active": active, "total": snap.total_ministers}


@app.get("/court/minister/{name}")
def get_minister(name: str):
    detail = _court.inspect.minister_detail(name)
    if detail is None:
        raise HTTPException(404, f"Minister '{name}' not found")
    return {"detail": detail}


@app.post("/court/register")
def register_minister(req: RegisterRequest):
    name = _court.register(
        name=req.name, domain=req.domain,
        temperature=req.temperature,
        confidence_baseline=req.confidence_baseline,
    )
    return {"name": name}


@app.post("/court/register/batch")
def register_batch(req: BulkRegisterRequest):
    specs = [
        {"name": m.name, "domain": m.domain,
         "temperature": m.temperature,
         "confidence_baseline": m.confidence_baseline}
        for m in req.ministers
    ]
    names = _court.register_many(specs)
    return {"names": names, "count": len(names)}


@app.post("/court/evolve")
def run_evolution(req: EvolveRequest):
    return _court.evolve(req.cycles)


@app.post("/court/dispatch")
def record_dispatch(req: DispatchRequest):
    _court.record_dispatch(
        req.minister, req.edict_id, req.intent,
        req.success, req.confidence,
        execution_time_ms=req.execution_time_ms,
    )
    return {"message": "Dispatch recorded"}


@app.post("/court/feedback")
def record_feedback(req: FeedbackRequest):
    ok = _court.record_feedback(req.minister, req.edict_id, req.score)
    if not ok:
        raise HTTPException(404, "Dispatch not found")
    return {"message": "Feedback recorded"}


@app.post("/court/genomes/save")
def save_genomes():
    path = _court.save_genomes()
    if path is None:
        raise HTTPException(400, "No genome_path configured")
    return {"path": path}


@app.post("/court/genomes/load")
def load_genomes(req: GenomeLoadRequest):
    genomes, meta = _court.load_genomes(req.path)
    return {
        "loaded": len(genomes),
        "metadata": meta,
        "active": _court.active_ministers,
    }
