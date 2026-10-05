from pydantic import BaseModel, Field
from typing import Optional, Mapping, Literal, Dict
from pathlib import Path

class ExecutionRequest(BaseModel):
    command: str = Field(..., description="Raw command string to execute")
    cwd: Optional[Path] = Field(None, description="Working directory; defaults to session cwd")
    env: Optional[Mapping[str, str]] = Field(None, description="Extra environment variables for the command")
    backend: Literal["local", "docker", "ssh"] = Field("local", description="Backend to run the command on")
    shell: bool = Field(False, description="Run via /bin/sh – enables pipelines, redirects, etc.")
    timeout: Optional[int] = Field(60, description="Maximum seconds before the command is killed")
    background: bool = Field(False, description="If true, run asynchronously and return execution_id immediately")
    interactive: bool = Field(False, description="Require PTY (interactive terminal) support")
    permission_mode: Literal["auto", "ask", "deny"] = Field("ask", description="Permission handling for risky commands")
    verification: Optional[Dict] = Field(None, description="Verification spec – e.g. {\"type\": \"file_exists\", \"path\": \"/tmp/out\"}")

class ExecutionResult(BaseModel):
    execution_id: str = Field(..., description="Unique ID for this execution instance")
    command: str = Field(..., description="Command that was executed")
    backend: str = Field(..., description="Backend used (local, docker, ssh)")
    cwd: Path = Field(..., description="Working directory at execution time")
    status: Literal["success", "failed", "cancelled", "timed_out", "denied"] = Field(..., description="Final status of the execution")
    exit_code: Optional[int] = Field(None, description="Process exit code when applicable")
    stdout: Optional[str] = Field(None, description="Captured standard output (truncated if very large)")
    stderr: Optional[str] = Field(None, description="Captured standard error (truncated if very large)")
    pid: Optional[int] = Field(None, description="PID of the process (if available)")
    duration: float = Field(..., description="Runtime in seconds")
    verified: bool = Field(False, description="Whether post‑execution verification succeeded")
    verification_result: Optional[Dict] = Field(None, description="Result payload from verification engine")
    error: Optional[str] = Field(None, description="Human‑readable error message if status != success")
