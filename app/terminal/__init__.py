"""MOON Terminal — AI-agent execution subsystem.

Public API:
    from app.terminal import (
        terminal_interface,
        execution_engine,
        session_manager,
        process_manager,
        pty_manager,
        environment_manager,
        history_manager,
        get_bus,
        ExecutionRequest,
        ExecutionResult,
        ExecutionState,
        StateMachine,
        TerminalInterface,
    )
"""

from .models import ExecutionRequest, ExecutionResult
from .state_machine import ExecutionState, StateMachine
from .execution_engine import execution_engine, ExecutionEngine
from .session_manager import session_manager, SessionManager, Session
from .process_manager import process_manager, ProcessManager, ProcessInfo
from .pty_manager import pty_manager, PTYManager
from .environment_manager import environment_manager, EnvironmentManager
from .history_manager import history_manager, HistoryManager, HistoryEntry
from .event_bus import get_bus, Event
from .terminal_interface import terminal_interface, TerminalInterface
from .backend_manager import BackendManager
from .risk_engine import RiskEngine
from .permission_engine import PermissionEngine
from .verification_engine import VerificationEngine
from .recovery_engine import recovery_engine, RecoveryEngine
from .output_engine import OutputEngine

__all__ = [
    # Singletons
    "terminal_interface",
    "execution_engine",
    "session_manager",
    "process_manager",
    "pty_manager",
    "environment_manager",
    "history_manager",
    "recovery_engine",
    "get_bus",
    # Classes
    "TerminalInterface",
    "ExecutionEngine",
    "SessionManager",
    "Session",
    "ProcessManager",
    "ProcessInfo",
    "PTYManager",
    "EnvironmentManager",
    "HistoryManager",
    "HistoryEntry",
    "BackendManager",
    "RiskEngine",
    "PermissionEngine",
    "VerificationEngine",
    "RecoveryEngine",
    "OutputEngine",
    "Event",
    # Models
    "ExecutionRequest",
    "ExecutionResult",
    "ExecutionState",
    "StateMachine",
]
