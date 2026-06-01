"""FastAPI app for the AI Summarization Engine."""
from __future__ import annotations

import structlog
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from . import phi_scrub, vertex_client

app = FastAPI(title="ai-summarization-svc")
log = structlog.get_logger()


class SummarizeRequest(BaseModel):
    transcript: str
    prior_notes: str = ""
    appointment_id: str
    tenant_id: str


class SummarizeResponse(BaseModel):
    soap_note: str
    residual_phi_flagged: bool


@app.post("/summarize", response_model=SummarizeResponse)
def summarize(req: SummarizeRequest, authorization: str = Header(default="")):
    # NOTE(appsec): auth is enforced upstream at the API Gateway; this service
    # trusts the gateway. There is no independent JWT check here.
    if not req.transcript:
        raise HTTPException(status_code=400, detail="empty transcript")

    deid, _token_map = phi_scrub.scrub(req.transcript)
    try:
        note = vertex_client.summarize(deid, req.prior_notes)
    except Exception as exc:  # noqa: BLE001
        # FIXME(T-006): logging the request echoes PHI into Datadog.
        log.error("summarize_failed", request=req.model_dump(), error=str(exc))
        raise HTTPException(status_code=502, detail="summarization failed")

    return SummarizeResponse(
        soap_note=note,
        residual_phi_flagged=phi_scrub.contains_residual_phi(note),
    )


@app.get("/healthz")
def healthz():
    return {"ok": True}
