"""
StorageOps HTTP API server — exposes diagnostic tools over a REST API.

Usage:
    python -m storageops.api_server
    storageops serve [--host 0.0.0.0] [--port 8000]

Endpoints:
    GET  /                 — Web UI (single-page diagnostic interface)
    POST /triage          — classify evidence text into a diagnostic domain
    POST /analyze         — run domain-specific rule-based analysis
    POST /agent           — deprecated; use storageops agent CLI (requires Pi)
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

_VERSION = "0.3.0"
_STATIC_DIR = Path(__file__).parent / "static"

# ── Optional FastAPI / Pydantic imports ───────────────────────────────

try:
    from fastapi import FastAPI, Query
    from fastapi.responses import JSONResponse, FileResponse
    from fastapi.staticfiles import StaticFiles
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


# ── App factory ───────────────────────────────────────────────────────

def _make_app() -> "FastAPI":
    app = FastAPI(
        title="StorageOps API",
        version=_VERSION,
        description="StorageOps diagnostic tools over HTTP.",
    )

    # ── Static files / Web UI ─────────────────────────────────────────

    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    async def ui():
        index = _STATIC_DIR / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return {"message": "StorageOps API", "version": _VERSION, "docs": "/docs"}

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
    async def agent():
        return JSONResponse(
            status_code=501,
            content={
                "ok": False,
                "error": (
                    "The /agent HTTP endpoint has been removed. "
                    "StorageOps Agent Runtime is now Pi Coding Agent. "
                    "Use the CLI: storageops agent <file>"
                ),
            },
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
