"""StorageOps — object storage diagnostic toolkit."""
import sys
from pathlib import Path


def _setup_core_path() -> None:
    """Add storageops-core sub-modules to sys.path for flat-name imports."""
    # Path 1: wheel/pip install — core bundled as storageops._parsers etc.
    try:
        import storageops._parsers as _p
        import storageops._analyzers as _a
        import storageops._utils as _u
        for _m in (_p, _a, _u):
            _d = str(Path(_m.__file__).parent)
            if _d not in sys.path:
                sys.path.insert(0, _d)
        return
    except (ImportError, AttributeError):
        pass
    # Path 2: editable/repo install — storageops-core sits two levels up
    _core = Path(__file__).resolve().parents[2] / "storageops-core"
    if _core.exists():
        for _sub in ("utils", "parsers", "analyzers"):
            _d = str(_core / _sub)
            if _d not in sys.path:
                sys.path.insert(0, _d)


_setup_core_path()
