from __future__ import annotations

import ast
import operator
from typing import Any

from puerflow_worker.sandbox import SandboxClient
from puerflow_worker.tools.base import Tool, ToolMetadata, ToolResult

_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}


class CalculatorTool(Tool):
    metadata = ToolMetadata(
        name="calculator",
        description="Evaluate a basic arithmetic expression.",
        category="utility",
        parameters={
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
        },
    )

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        expression = str(parameters.get("expression") or "").strip()
        if not expression:
            return ToolResult(success=False, error="expression is required")
        try:
            result = _eval_node(ast.parse(expression, mode="eval").body)
            return ToolResult(success=True, output=result, text=str(result))
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=str(exc))


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_eval_node(node.operand))
    raise ValueError("unsupported expression")


class PythonExecutorTool(Tool):
    def __init__(self, sandbox: SandboxClient, *, dangerous: bool = True) -> None:
        self.sandbox = sandbox
        self.metadata = ToolMetadata(
            name="python_executor",
            description=(
                "Execute Python in an isolated WASI sandbox. Stdlib only. "
                "Write session files under /workspace."
            ),
            category="code",
            source="native",
            timeout_seconds=40.0,
            dangerous=dangerous,
            parameters={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to execute."},
                    "session_id": {"type": "string", "description": "Session workspace id."},
                },
                "required": ["code"],
            },
        )

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        code = str(parameters.get("code") or "").strip()
        if not code:
            return ToolResult(success=False, error="code is required")
        session_id = str(parameters.get("session_id") or "")
        user_id = str(parameters.get("user_id") or "")
        workflow_id = str(parameters.get("workflow_id") or session_id or "session")
        staging_path = f"staging/{workflow_id}.py"
        write = await self.sandbox.file_write(staging_path, code, session_id=session_id, user_id=user_id)
        if write.skipped and not write.success:
            return ToolResult(
                success=False,
                error=write.error or "sandbox unavailable",
                metadata={"skipped": True, "stage": "staging"},
            )
        result = await self.sandbox.execute_python(code, session_id=session_id, user_id=user_id)
        output = (result.stdout or result.error or "").strip()
        if result.skipped:
            return ToolResult(
                success=False,
                error=result.error or "sandbox skipped",
                metadata={"skipped": True},
            )
        if not result.success:
            return ToolResult(success=False, error=output or "WASI execution failed", text=output)
        if output:
            await self.sandbox.file_write(
                f"workspace/{workflow_id}.out",
                output,
                session_id=session_id,
                user_id=user_id,
            )
        return ToolResult(
            success=True,
            output=output,
            text=output,
            metadata={"stage": "commit", "workspace": f"workspace/{workflow_id}.out"},
        )
