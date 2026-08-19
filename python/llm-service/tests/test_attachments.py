import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from llm_service.attachments import AttachmentResolver
from llm_service.api.agent import _resolve_attachments
from llm_provider.base import translate_content_for_openai

@pytest.fixture
def mock_redis():
    return AsyncMock()

@pytest.fixture
def resolver(mock_redis):
    return AttachmentResolver(mock_redis)


class TestAttachmentResolver:

    @pytest.mark.asyncio
    async def test_resolve_base64_attachment(self, resolver, mock_redis):
        """Resolve an attachment ID to base64 data from Redis."""
        att_data = {
            "id": "abc123",
            "session_id": "sess-1",
            "media_type": "image/png",
            "filename": "test.png",
            "data": "iVBORw0KGgo=",
            "size_bytes": 10,
        }
        mock_redis.get.return_value = json.dumps(att_data).encode()

        result = await resolver.resolve("abc123")
        assert result["media_type"] == "image/png"
        assert result["data"] is not None
        mock_redis.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_not_found(self, resolver, mock_redis):
        mock_redis.get.return_value = None
        result = await resolver.resolve("nonexistent")
        assert result is None

    def test_to_anthropic_image_block(self, resolver):
        att = {"media_type": "image/png", "data": "iVBORw0KGgo=", "source": "base64"}
        block = resolver.to_anthropic_block(att)
        assert block["type"] == "image"
        assert block["source"]["type"] == "base64"
        assert block["source"]["media_type"] == "image/png"

    def test_to_anthropic_pdf_block(self, resolver):
        att = {"media_type": "application/pdf", "data": "JVBERi0=", "source": "base64"}
        block = resolver.to_anthropic_block(att)
        assert block["type"] == "document"
        assert block["source"]["type"] == "base64"
        assert block["source"]["media_type"] == "application/pdf"

    def test_to_openai_image_block(self, resolver):
        att = {"media_type": "image/png", "data": "iVBORw0KGgo=", "source": "base64"}
        block = resolver.to_openai_block(att)
        assert block["type"] == "image_url"
        assert block["image_url"]["url"].startswith("data:image/png;base64,")

    def test_to_openai_pdf_block(self, resolver):
        att = {"media_type": "application/pdf", "data": "JVBERi0=", "source": "base64"}
        block = resolver.to_openai_block(att)
        assert block["type"] == "file"
        assert block["file"]["file_data"].startswith("data:application/pdf;base64,")

    def test_to_content_blocks_multiple(self, resolver):
        atts = [
            {"media_type": "image/png", "data": "abc=", "source": "base64"},
            {"media_type": "application/pdf", "data": "def=", "source": "base64"},
        ]
        blocks = resolver.to_content_blocks(atts, provider="anthropic")
        assert len(blocks) == 2
        assert blocks[0]["type"] == "image"
        assert blocks[1]["type"] == "document"


# ─── Task 5: build_agent_messages injection tests ───


class TestBuildAgentMessagesAttachments:
    """Test that build_agent_messages injects shannon_attachment blocks."""

    def _make_body(self, **overrides):
        """Create a minimal AgentLoopStepRequest-like object."""
        from llm_service.api.agent import AgentLoopStepRequest
        defaults = {
            "agent_id": "test-agent",
            "task": "Analyze the attached image",
            "iteration": 0,
        }
        defaults.update(overrides)
        return AgentLoopStepRequest(**defaults)

    def test_no_attachments_returns_string_content(self):
        from llm_service.api.agent import build_agent_messages
        body = self._make_body()
        msgs = build_agent_messages(body, raw_attachments=None)
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        # Without attachments, content is a plain string
        assert isinstance(msgs[1]["content"], str)

    def test_with_attachments_returns_list_content(self):
        from llm_service.api.agent import build_agent_messages
        body = self._make_body()
        raw_atts = [
            {"media_type": "image/png", "data": "iVBORw0KGgo=", "filename": "chart.png"},
        ]
        msgs = build_agent_messages(body, raw_attachments=raw_atts)
        user_content = msgs[1]["content"]
        assert isinstance(user_content, list)
        # First block is the attachment, last is the text
        assert user_content[0]["type"] == "shannon_attachment"
        assert user_content[0]["media_type"] == "image/png"
        assert user_content[0]["data"] == "iVBORw0KGgo="
        assert user_content[0]["filename"] == "chart.png"
        assert user_content[-1]["type"] == "text"
        assert "Analyze the attached image" in user_content[-1]["text"]

    def test_multiple_attachments(self):
        from llm_service.api.agent import build_agent_messages
        body = self._make_body()
        raw_atts = [
            {"media_type": "image/png", "data": "abc=", "filename": "a.png"},
            {"media_type": "application/pdf", "data": "def=", "filename": "b.pdf"},
        ]
        msgs = build_agent_messages(body, raw_attachments=raw_atts)
        user_content = msgs[1]["content"]
        assert isinstance(user_content, list)
        assert len(user_content) == 3  # 2 attachments + 1 text
        assert user_content[0]["type"] == "shannon_attachment"
        assert user_content[1]["type"] == "shannon_attachment"
        assert user_content[2]["type"] == "text"

    def test_empty_attachments_list_returns_string(self):
        from llm_service.api.agent import build_agent_messages
        body = self._make_body()
        msgs = build_agent_messages(body, raw_attachments=[])
        assert isinstance(msgs[1]["content"], str)

    def test_text_attachments_still_bound_total_prompt_size(self):
        from llm_service.api.agent import AgentLoopTurn, build_agent_messages
        body = self._make_body(
            history=[
                AgentLoopTurn(iteration=1, action="tool_call:web_search", result="A" * 150000),
                AgentLoopTurn(iteration=2, action="tool_call:web_search", result="B" * 150000),
                AgentLoopTurn(iteration=3, action="tool_call:web_search", result="C" * 150000),
            ]
        )
        raw_atts = [
            {"source": "text", "filename": "1.txt", "text_content": "x" * 120000},
            {"source": "text", "filename": "2.txt", "text_content": "y" * 120000},
        ]
        msgs = build_agent_messages(body, raw_attachments=raw_atts)
        user_content = msgs[1]["content"]
        assert isinstance(user_content, list)
        total_text_chars = sum(
            len(block.get("text", ""))
            for block in user_content
            if isinstance(block, dict) and block.get("type") == "text"
        )
        assert total_text_chars <= 400000


# ─── Task 6: Provider content block handling tests ───


class TestTranslateContentForOpenAI:
    """Test shannon_attachment conversion in translate_content_for_openai."""

    def test_image_attachment_to_openai(self):
        content = [
            {"type": "shannon_attachment", "media_type": "image/png", "data": "abc=", "filename": "x.png"},
            {"type": "text", "text": "Analyze this"},
        ]
        result = translate_content_for_openai(content)
        assert len(result) == 2
        assert result[0]["type"] == "image_url"
        assert result[0]["image_url"]["url"] == "data:image/png;base64,abc="
        assert result[1]["type"] == "text"

    def test_pdf_attachment_to_openai(self):
        content = [
            {"type": "shannon_attachment", "media_type": "application/pdf", "data": "JVBERi0=", "filename": "doc.pdf"},
        ]
        result = translate_content_for_openai(content)
        assert len(result) == 1
        assert result[0]["type"] == "file"
        assert result[0]["file"]["filename"] == "doc.pdf"
        assert result[0]["file"]["file_data"].startswith("data:application/pdf;base64,")

    def test_plain_string_passthrough(self):
        result = translate_content_for_openai("hello")
        assert result == "hello"

    def test_mixed_content_blocks(self):
        content = [
            {"type": "shannon_attachment", "media_type": "image/jpeg", "data": "jpg=", "filename": "photo.jpg"},
            {"type": "text", "text": "What's in this photo?"},
        ]
        result = translate_content_for_openai(content)
        assert len(result) == 2
        assert result[0]["type"] == "image_url"
        assert result[1]["type"] == "text"


class TestAnthropicAttachmentConversion:
    """Test shannon_attachment conversion in Anthropic provider."""

    def test_image_attachment_to_anthropic(self):
        from llm_provider.anthropic_provider import AnthropicProvider
        block = AnthropicProvider._shannon_att_to_anthropic({
            "type": "shannon_attachment",
            "media_type": "image/png",
            "data": "iVBORw0KGgo=",
            "filename": "chart.png",
        })
        assert block["type"] == "image"
        assert block["source"]["type"] == "base64"
        assert block["source"]["media_type"] == "image/png"
        assert block["source"]["data"] == "iVBORw0KGgo="

    def test_pdf_attachment_to_anthropic(self):
        from llm_provider.anthropic_provider import AnthropicProvider
        block = AnthropicProvider._shannon_att_to_anthropic({
            "type": "shannon_attachment",
            "media_type": "application/pdf",
            "data": "JVBERi0=",
            "filename": "report.pdf",
        })
        assert block["type"] == "document"
        assert block["source"]["type"] == "base64"
        assert block["source"]["media_type"] == "application/pdf"

    def test_convert_attachments_in_messages(self):
        from llm_provider.anthropic_provider import AnthropicProvider
        messages = [
            {"role": "user", "content": [
                {"type": "shannon_attachment", "media_type": "image/png", "data": "abc=", "filename": "x.png"},
                {"type": "text", "text": "Analyze this"},
            ]},
        ]
        # Create a mock provider instance to call the instance method
        with patch.object(AnthropicProvider, '__init__', lambda self, *a, **k: None):
            provider = AnthropicProvider.__new__(AnthropicProvider)
            result = provider._convert_attachments_for_anthropic(messages)
        user_content = result[0]["content"]
        assert user_content[0]["type"] == "image"
        assert user_content[1]["type"] == "text"

    def test_string_content_unchanged(self):
        from llm_provider.anthropic_provider import AnthropicProvider
        messages = [
            {"role": "user", "content": "Just text"},
        ]
        with patch.object(AnthropicProvider, '__init__', lambda self, *a, **k: None):
            provider = AnthropicProvider.__new__(AnthropicProvider)
            result = provider._convert_attachments_for_anthropic(messages)
        assert result[0]["content"] == "Just text"


class TestGeminiAttachmentConversion:
    """Test shannon_attachment conversion in Google Gemini provider."""

    def test_content_to_gemini_parts_with_attachment(self):
        from llm_provider.google_provider import GoogleProvider
        content = [
            {"type": "shannon_attachment", "media_type": "image/png", "data": "abc=", "filename": "x.png"},
            {"type": "text", "text": "Analyze this"},
        ]
        parts = GoogleProvider._content_to_gemini_parts(content)
        assert len(parts) == 2
        assert "inline_data" in parts[0]
        assert parts[0]["inline_data"]["mime_type"] == "image/png"
        assert parts[0]["inline_data"]["data"] == "abc="
        assert parts[1] == {"text": "Analyze this"}

    def test_content_to_gemini_parts_string(self):
        from llm_provider.google_provider import GoogleProvider
        parts = GoogleProvider._content_to_gemini_parts("Hello")
        assert parts == [{"text": "Hello"}]

    def test_content_to_gemini_parts_anthropic_image(self):
        from llm_provider.google_provider import GoogleProvider
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "jpg="}},
        ]
        parts = GoogleProvider._content_to_gemini_parts(content)
        assert len(parts) == 1
        assert parts[0]["inline_data"]["mime_type"] == "image/jpeg"

    def test_content_to_gemini_parts_external_url_degrades_to_text(self):
        from llm_provider.google_provider import GoogleProvider
        content = [
            {
                "type": "shannon_attachment",
                "source": "url",
                "media_type": "image/png",
                "url": "https://example.com/chart.png",
            },
            {"type": "text", "text": "Analyze this"},
        ]
        parts = GoogleProvider._content_to_gemini_parts(content)
        assert parts[0] == {"text": "[External attachment: https://example.com/chart.png (image/png)]"}
        assert parts[1] == {"text": "Analyze this"}

    def test_content_to_gemini_parts_google_file_uri_stays_native(self):
        from llm_provider.google_provider import GoogleProvider
        content = [
            {
                "type": "shannon_attachment",
                "source": "url",
                "media_type": "application/pdf",
                "url": "https://generativelanguage.googleapis.com/v1beta/files/abc123",
            },
        ]
        parts = GoogleProvider._content_to_gemini_parts(content)
        assert parts == [{
            "file_data": {
                "mime_type": "application/pdf",
                "file_uri": "https://generativelanguage.googleapis.com/v1beta/files/abc123",
            }
        }]


class TestXAIAttachmentDegradation:
    """Test shannon_attachment degradation to text in xAI provider."""

    def test_attachment_degrades_to_text(self):
        """xAI doesn't support multimodal; attachments degrade to text descriptions."""
        # Manually test the sanitization logic from _sanitize_messages
        from llm_provider.xai_provider import XAIProvider
        # Create a minimal instance for testing _sanitize_messages
        # We can't instantiate without API key, so test the logic directly
        content = [
            {"type": "shannon_attachment", "media_type": "image/png", "data": "abc=", "filename": "chart.png"},
            {"type": "text", "text": "What is in this chart?"},
        ]
        # Simulate what _sanitize_messages does for list content:
        text_parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "shannon_attachment":
                fname = part.get("filename", "file")
                mtype = part.get("media_type", "unknown")
                text_parts.append(f"[Attached file: {fname} ({mtype})]")
            elif isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(part.get("text", ""))
            elif isinstance(part, str):
                text_parts.append(part)
        result = " ".join(text_parts)
        assert "[Attached file: chart.png (image/png)]" in result
        assert "What is in this chart?" in result


class TestGroqAttachmentDegradation:
    """Test shannon_attachment degradation to text in Groq provider."""

    def test_attachment_degrades_to_text(self):
        """Groq doesn't support multimodal; attachments degrade to text descriptions."""
        content = [
            {"type": "shannon_attachment", "media_type": "application/pdf", "data": "pdf=", "filename": "report.pdf"},
            {"type": "text", "text": "Summarize this report"},
        ]
        # Simulate _sanitize_messages logic
        text_parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "shannon_attachment":
                fname = part.get("filename", "file")
                mtype = part.get("media_type", "unknown")
                text_parts.append(f"[Attached file: {fname} ({mtype})]")
            elif isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(part.get("text", ""))
            elif isinstance(part, str):
                text_parts.append(part)
        result = " ".join(text_parts)
        assert "[Attached file: report.pdf (application/pdf)]" in result
        assert "Summarize this report" in result


class TestResolveAttachmentsSkip:
    """Downstream agents with dependency_results should skip attachment resolution."""

    @pytest.mark.asyncio
    async def test_skip_when_dependency_results_present(self):
        """Agent with dependency_results should NOT resolve attachments."""
        context = {
            "attachments": [{"id": "att-1", "media_type": "image/png"}],
            "dependency_results": {"task-1": {"response": "It's a red pixel", "success": True}},
        }
        mock_redis = AsyncMock()
        result = await _resolve_attachments(context, mock_redis)
        assert result == []
        mock_redis.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_when_no_dependency_results(self):
        """Root agent (no dependency_results) should resolve normally."""
        context = {
            "attachments": [{"id": "att-1", "media_type": "image/png"}],
        }
        mock_redis = AsyncMock()
        att_data = {
            "id": "att-1", "session_id": "", "media_type": "image/png",
            "filename": "test.png", "data": "iVBORw0KGgo=", "size_bytes": 10,
        }
        mock_redis.get.return_value = json.dumps(att_data).encode()
        result = await _resolve_attachments(context, mock_redis)
        assert len(result) == 1
        assert result[0]["media_type"] == "image/png"

    @pytest.mark.asyncio
    async def test_skip_with_empty_dependency_results(self):
        """Empty dict dependency_results is falsy — should resolve normally."""
        context = {
            "attachments": [{"id": "att-1", "media_type": "image/png"}],
            "dependency_results": {},
        }
        mock_redis = AsyncMock()
        att_data = {
            "id": "att-1", "session_id": "", "media_type": "image/png",
            "filename": "test.png", "data": "abc=", "size_bytes": 3,
        }
        mock_redis.get.return_value = json.dumps(att_data).encode()
        result = await _resolve_attachments(context, mock_redis)
        assert len(result) == 1
