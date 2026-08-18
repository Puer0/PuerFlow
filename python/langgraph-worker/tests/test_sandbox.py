from puerflow_worker.tools import extract_python
from puerflow_worker.sandbox import SandboxClient, CommandResult


def test_extract_python_fence():
    assert extract_python("hello") is None
    code = extract_python("run this\n```python\nprint(1)\n```\n")
    assert code == "print(1)"


async def test_optional_sandbox_skips_without_core():
    client = SandboxClient("127.0.0.1:1", optional=True, timeout=0.2)
    result = await client.execute_command("ls", session_id="s1")
    assert isinstance(result, CommandResult)
    assert result.skipped is True
