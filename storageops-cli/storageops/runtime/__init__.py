"""StorageOps agent runtime integration.

Pi Coding Agent is the default and only supported Agent Runtime. StorageOps
keeps deterministic diagnostics, redaction, validation, and non-agent commands.
"""
from storageops.runtime.base import AgentRunOptions, AgentRunResult
from storageops.runtime.pi_rpc import PiRpcRuntime

__all__ = ["AgentRunOptions", "AgentRunResult", "PiRpcRuntime"]
