"""Backward-compat shim → storageops.core.session.

Re-exports Session and SessionEntry for legacy imports.
"""
from storageops.core.session import Session, SessionEntry  # noqa: F401

# Backward compat: keep DiagnosticSession alias
DiagnosticSession = Session
