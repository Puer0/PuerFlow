from unittest.mock import patch

from puerflow_worker.llm import CompletionClient


class _FakeResponse:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


async def test_completion_client_routes_through_llm_service():
    posted = []

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, headers=None, json=None):
            posted.append((url, json))
            return _FakeResponse(
                {
                    "output_text": "Paris",
                    "model": "routed-small",
                    "provider": "openai",
                    "usage": {"input_tokens": 4, "output_tokens": 2, "total_tokens": 6},
                    "tool_calls": [{"id": "c1", "name": "calculator", "arguments": {"expression": "1+1"}}],
                }
            )

    client = CompletionClient(llm_service_url="http://llm-service:8000", mock=False)
    with patch("puerflow_worker.llm.httpx.AsyncClient", _FakeClient):
        result = await client.generate(
            [{"role": "user", "content": "capital?"}],
            tools=[{"type": "function", "function": {"name": "calculator"}}],
            model_tier="medium",
        )

    assert result.content == "Paris"
    assert result.model == "routed-small"
    assert result.provider == "openai"
    assert result.usage.total_tokens == 6
    assert result.tool_calls[0]["name"] == "calculator"
    assert posted[0][0] == "http://llm-service:8000/completions/"
    assert posted[0][1]["model_tier"] == "medium"
    assert "specific_model" not in posted[0][1]


async def test_llm_service_url_does_not_force_mock_without_openai_key():
    client = CompletionClient(llm_service_url="http://llm-service:8000")
    assert client.mock is False
    assert CompletionClient().mock is True
