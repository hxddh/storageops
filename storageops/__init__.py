"""StorageOps — S3-compatible object storage diagnostic toolkit."""
__version__ = "0.3.0"

# Public API
from storageops.session import Session, create as create_session, load as load_session, list_all as list_sessions
from storageops.agent import converse, converse_one_shot, PiRunResult
from storageops.display import Display
from storageops.context import build_prompt, load_identity
from storageops.diagnostics import classify_evidence, assess_evidence, run_analysis, generate_report, EVIDENCE_CHECKLIST
