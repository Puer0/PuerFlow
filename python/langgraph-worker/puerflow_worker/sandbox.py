from __future__ import annotations

from dataclasses import dataclass
import logging
import sys
from pathlib import Path
from typing import Any

_GRPC_GEN = Path(__file__).resolve().parent / "grpc_gen"
if str(_GRPC_GEN) not in sys.path:
    sys.path.insert(0, str(_GRPC_GEN))

logger = logging.getLogger(__name__)

try:
    import grpc
    from agent import agent_pb2, agent_pb2_grpc
    from sandbox import sandbox_pb2, sandbox_pb2_grpc
    from google.protobuf import struct_pb2

    _PROTO_AVAILABLE = True
except Exception:  # noqa: BLE001
    grpc = None  # type: ignore[misc, assignment]
    _PROTO_AVAILABLE = False


@dataclass
class CommandResult:
    success: bool
    stdout: str = ""
    stderr: str = ""
    error: str = ""
    skipped: bool = False
    exit_code: int = 0


@dataclass
class FileResult:
    success: bool
    content: str = ""
    error: str = ""
    skipped: bool = False
    bytes_written: int = 0


class SandboxClient:
    """gRPC client for Shannon Rust Agent Core: WASI exec + workspace files."""

    def __init__(self, address: str = "agent-core:50051", *, optional: bool = True, timeout: float = 8.0):
        self.address = address
        self.optional = optional
        self.timeout = timeout
        self._channel: Any = None
        self._sandbox = None
        self._agent = None

    async def _ensure_connected(self) -> bool:
        if not _PROTO_AVAILABLE or grpc is None:
            return False
        if self._channel is None:
            self._channel = grpc.aio.insecure_channel(self.address)
            self._sandbox = sandbox_pb2_grpc.SandboxServiceStub(self._channel)
            self._agent = agent_pb2_grpc.AgentServiceStub(self._channel)
        return True

    async def close(self) -> None:
        if self._channel is not None:
            await self._channel.close()
            self._channel = None

    async def execute_python(self, code: str, session_id: str = "", user_id: str = "") -> CommandResult:
        if not await self._ensure_connected():
            return CommandResult(success=False, skipped=True, error="sandbox proto unavailable")
        ctx = struct_pb2.Struct()
        ctx.update(
            {
                "tool_parameters": {
                    "tool": "code_executor",
                    "stdin": code,
                    "argv": ["python", "-c", "import sys; exec(sys.stdin.read())"],
                }
            }
        )
        request = agent_pb2.ExecuteTaskRequest(
            query=f"Execute Python code (session: {session_id or 'none'})",
            context=ctx,
            available_tools=["code_executor"],
        )
        if session_id:
            request.session_context.session_id = session_id
        if user_id:
            request.session_context.user_id = user_id
        try:
            resp = await self._agent.ExecuteTask(request, timeout=self.timeout)
            return CommandResult(
                success=bool(resp.result) or getattr(resp, "status", 0) == 1,
                stdout=resp.result or "",
                error=resp.error_message or "",
            )
        except Exception as exc:  # noqa: BLE001
            return self._optional_fail(f"execute_python: {exc}")

    async def execute_command(self, command: str, session_id: str = "", user_id: str = "", timeout_seconds: int = 30) -> CommandResult:
        if not await self._ensure_connected():
            return CommandResult(success=False, skipped=True, error="sandbox proto unavailable")
        try:
            resp = await self._sandbox.ExecuteCommand(
                sandbox_pb2.CommandRequest(
                    session_id=session_id,
                    user_id=user_id,
                    command=command,
                    timeout_seconds=timeout_seconds,
                ),
                timeout=min(self.timeout, timeout_seconds + 5),
            )
            return CommandResult(
                success=resp.success,
                stdout=resp.stdout or "",
                stderr=resp.stderr or "",
                error=resp.error or "",
                exit_code=resp.exit_code,
            )
        except Exception as exc:  # noqa: BLE001
            return self._optional_fail(f"execute_command: {exc}")

    async def file_write(self, path: str, content: str, session_id: str = "", user_id: str = "") -> FileResult:
        if not await self._ensure_connected():
            return FileResult(success=False, skipped=True, error="sandbox proto unavailable")
        try:
            resp = await self._sandbox.FileWrite(
                sandbox_pb2.FileWriteRequest(
                    session_id=session_id,
                    user_id=user_id,
                    path=path,
                    content=content,
                    create_dirs=True,
                ),
                timeout=self.timeout,
            )
            return FileResult(success=resp.success, error=resp.error or "", bytes_written=int(resp.bytes_written or 0))
        except Exception as exc:  # noqa: BLE001
            return FileResult(success=False, skipped=self.optional, error=str(exc))

    async def file_read(self, path: str, session_id: str = "", user_id: str = "") -> FileResult:
        if not await self._ensure_connected():
            return FileResult(success=False, skipped=True, error="sandbox proto unavailable")
        try:
            resp = await self._sandbox.FileRead(
                sandbox_pb2.FileReadRequest(session_id=session_id, user_id=user_id, path=path),
                timeout=self.timeout,
            )
            return FileResult(success=resp.success, content=resp.content or "", error=resp.error or "")
        except Exception as exc:  # noqa: BLE001
            return FileResult(success=False, skipped=self.optional, error=str(exc))

    def _optional_fail(self, error: str) -> CommandResult:
        logger.info("sandbox call skipped/failed: %s", error)
        return CommandResult(success=False, skipped=self.optional, error=error)
