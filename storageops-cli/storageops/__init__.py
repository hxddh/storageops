"""StorageOps — object storage diagnostic toolkit."""
import sys
from pathlib import Path

# storageops-core parsers, analyzers, and utils use flat module names
# (e.g. `from secret_scanner import scan`) rather than package-qualified
# names, so their parent directories must be on sys.path.
# This block runs once when any storageops.* module is first imported.
_CORE = Path(__file__).resolve().parents[2] / "storageops-core"
for _sub in ("utils", "parsers", "analyzers"):
    _p = str(_CORE / _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)
