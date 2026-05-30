"""
StorageOps HTTP API server — exposes diagnostic tools over a REST API.

Usage:
    python -m storageops.api_server
    storageops serve [--host 0.0.0.0] [--port 8000]

Endpoints:
    POST /triage          — classify evidence text into a diagnostic domain
    POST /analyze         — run domain-specific rule-based analysis
    POST /agent           — run LLM-powered diagnostic agent
    GET  /memory          — list recent 20 diagnosed cases
    GET  /memory/search   — search memory by keyword (?q=...)
    GET  /health          — liveness check

Requires: pip install 'storageops[api]'  (fastapi uvicorn)
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure storageops-core is importable
_CLI_DIR = Path(__file__).parent.parent
_CORE_DIR = _CLI_DIR.parent / "storageops-core"
for _sub in ("utils", "parsers", "analyzers"):
    _p = str(_CORE_DIR / _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

_VERSION = "0.2.0"

# ── Optional FastAPI / Pydantic imports ───────────────────────────────

try:
    from fastapi import FastAPI, Query
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel, ConfigDict
    import uvicorn
    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False
    FastAPI = None  # type: ignore[assignment,misc]
    BaseModel = object  # type: ignore[assignment,misc]


# ── Request / Response models ─────────────────────────────────────────

if _FASTAPI_AVAILABLE:
    class TriageRequest(BaseModel):
        model_config = ConfigDict(extra="forbid")

        text: str | None = None
        file_content: str | None = None

    class AnalyzeRequest(BaseModel):
        model_config = ConfigDict(extra="forbid")

        domain: str
        text: str

    class AgentRequest(BaseModel):
        model_config = ConfigDict(extra="forbid")

        text: str
        provider: str = "anthropic"
        api_key: str | None = None
        model: str | None = None
        base_url: str | None = None
        max_turns: int = 8


# ── App factory ───────────────────────────────────────────────────────

def _make_app() -> "FastAPI":
    app = FastAPI(
        title="StorageOps API",
        version=_VERSION,
        description="StorageOps diagnostic tools over HTTP.",
    )

    # ── /health ───────────────────────────────────────────────────────

    @app.get("/health")
    async def health():
        return {"ok": True, "version": _VERSION}

    # ── /triage ───────────────────────────────────────────────────────

    @app.post("/triage")
    async def triage(req: TriageRequest):
        text = req.text or req.file_content
        if not text:
            return JSONResponse(
                status_code=422,
                content={"ok": False, "error": "Provide 'text' or 'file_content'"},
            )
        try:
            from secret_scanner import scan as _scan
            scan_result = _scan(text)
            safe_text = scan_result["redacted_text"]

            from storageops.agent import classify_evidence, assess_evidence
            classification = classify_evidence(safe_text)
            domain = classification["primary_domain"]
            evidence = assess_evidence(safe_text, domain)

            return {
                "ok": True,
                "primary_domain": domain,
                "all_domains": classification["all_domains"],
                "scores": classification["scores"],
                "evidence_quality": evidence.get("quality", "unknown"),
                "missing_required": evidence.get("missing_required", []),
                "missing_helpful": evidence.get("missing_helpful", []),
                "secrets_redacted": scan_result["count"],
            }
        except Exception as exc:
            return JSONResponse(
                status_code=500,
                content={"ok": False, "error": str(exc)},
            )

    # ── /analyze ──────────────────────────────────────────────────────

    @app.post("/analyze")
    async def analyze(req: AnalyzeRequest):
        try:
            from storageops.agent import run_analysis, generate_report, assess_evidence

            result = run_analysis(req.domain, req.text)
            evidence = assess_evidence(req.text, req.domain)
            report = generate_report(req.domain, dict(result), evidence.get("quality", "partial"))

            return {
                "ok": True,
                "domain": req.domain,
                "analysis": result,
                "report": report,
            }
        except Exception as exc:
            return JSONResponse(
                status_code=500,
                content={"ok": False, "error": str(exc)},
            )

    # ── /agent ────────────────────────────────────────────────────────

    @app.post("/agent")
    async def agent(req: AgentRequest):
        try:
            from storageops.llm_agent import run_llm_agent
        except ImportError as exc:
            return JSONResponse(
                status_code=501,
                content={
                    "ok": False,
                    "error": (
                        f"LLM agent unavailable: {exc}. "
                        "Install with: pip install 'storageops[llm]'"
                    ),
                },
            )

        try:
            # Pre-classify domain for the agent
            from storageops.agent import classify_evidence
            classification = classify_evidence(req.text)
            domain = classification["primary_domain"]

            result = run_llm_agent(
                evidence_text=req.text,
                domain=domain,
                provider_name=req.provider,
                api_key=req.api_key,
                model=req.model,
                base_url=req.base_url,
                max_turns=req.max_turns,
                verbose=False,
            )
            return result
        except Exception as exc:
            return JSONResponse(
                status_code=500,
                content={"ok": False, "error": str(exc)},
            )

    # ── /memory ───────────────────────────────────────────────────────

    @app.get("/memory")
    async def memory(domain: str | None = Query(default=None)):
        try:
            from storageops.memory_store import list_cases
            cases = list_cases(domain=domain, limit=20)
            return {"ok": True, "count": len(cases), "cases": cases}
        except Exception as exc:
            return JSONResponse(
                status_code=500,
                content={"ok": False, "error": str(exc)},
            )

    @app.get("/memory/search")
    async def memory_search(
        q: str = Query(..., description="Search keywords"),
        domain: str | None = Query(default=None),
        top_k: int = Query(default=3, ge=1, le=10),
    ):
        try:
            from storageops.memory_store import search_cases
            results = search_cases(q, domain=domain, top_k=top_k)
            return {"ok": True, "count": len(results), "query": q, "results": results}
        except Exception as exc:
            return JSONResponse(
                status_code=500,
                content={"ok": False, "error": str(exc)},
            )

    return app


# ── Module-level app instance (for uvicorn import string) ─────────────

if _FASTAPI_AVAILABLE:
    app = _make_app()
else:
    app = None  # type: ignore[assignment]


# ── Entry point ───────────────────────────────────────────────────────

def run(host: str = "127.0.0.1", port: int = 8000, reload: bool = False) -> None:
    """Start the API server with uvicorn."""
    if not _FASTAPI_AVAILABLE:
        print(
            "API server requires fastapi and uvicorn.\n"
            "Install with: pip install 'storageops[api]'\n"
            "  or: pip install fastapi uvicorn",
            file=sys.stderr,
        )
        sys.exit(1)

    uvicorn.run(
        "storageops.api_server:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    run()
