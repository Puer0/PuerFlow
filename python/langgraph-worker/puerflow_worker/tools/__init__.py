from puerflow_worker.sandbox import SandboxClient
from puerflow_worker.settings import WorkerSettings
from puerflow_worker.tools.builtin import CalculatorTool, PythonExecutorTool
from puerflow_worker.tools.fence import extract_python, maybe_run_sandbox
from puerflow_worker.tools.loop import complete_turn, run_llm_with_tools
from puerflow_worker.tools.registry import ToolRegistry, load_mcp_tools_from_json

__all__ = [
    "ToolRegistry",
    "build_default_registry",
    "complete_turn",
    "extract_python",
    "maybe_run_sandbox",
    "run_llm_with_tools",
]


def build_default_registry(
    sandbox: SandboxClient | None,
    settings: WorkerSettings,
) -> ToolRegistry:
    registry = ToolRegistry(approval_timeout_seconds=settings.approval_timeout_seconds)
    registry.register(CalculatorTool())
    if sandbox is not None:
        registry.register(PythonExecutorTool(sandbox, dangerous=settings.python_executor_dangerous))
    load_mcp_tools_from_json(registry, settings.mcp_tools_json)
    return registry
