"""Tests for cross-provider tool message compatibility in /v1/completions.

Tests production bugs:
1. prepare_openai_messages produces empty tool_call_id (base.py)
2. Anthropic provider gets invalid tool_use_id (anthropic_provider.py)
3. OpenAI/Groq send legacy 'functions' with role:'tool' messages (openai_provider.py)
4. Legacy function_call not upgraded to tool_calls when role:'tool' present (base.py)
"""
import importlib
import re
import pytest
from llm_provider.base import prepare_openai_messages, _has_function_call_tool_mismatch, sanitize_completion_messages

TOOL_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')

_has_openai = importlib.util.find_spec("openai") is not None


# --- Bug 1: base.py empty ID guard ---

class TestPrepareOpenAIMessagesToolIds:
    """prepare_openai_messages must never produce empty tool_call_id or tool_call.id."""

    def test_empty_tool_use_id_gets_fallback(self):
        """Anthropic-style messages with empty IDs must get valid fallbacks."""
        messages = [
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "", "name": "get_weather", "input": {}}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "", "content": "result"}
            ]},
        ]
        result = prepare_openai_messages(messages)
        for msg in result:
            if msg.get("role") == "tool":
                assert msg["tool_call_id"], "tool_call_id must not be empty"
            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    assert tc["id"], "tool_call id must not be empty"

    def test_missing_tool_use_id_key_gets_fallback(self):
        """tool_result blocks missing tool_use_id key entirely."""
        messages = [
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "", "name": "search", "input": {}}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "content": "data"}
                # Note: no tool_use_id key at all
            ]},
        ]
        result = prepare_openai_messages(messages)
        tool_msgs = [m for m in result if m.get("role") == "tool"]
        for msg in tool_msgs:
            assert msg["tool_call_id"], "tool_call_id must not be empty"

    def test_valid_ids_pass_through_unchanged(self):
        """Valid IDs (call_xxx, toolu_xxx) must not be modified."""
        messages = [
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "call_abc123", "name": "search", "input": {}}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "call_abc123", "content": "ok"}
            ]},
        ]
        result = prepare_openai_messages(messages)
        assistant_msg = [m for m in result if m.get("tool_calls")][0]
        assert assistant_msg["tool_calls"][0]["id"] == "call_abc123"
        tool_msg = [m for m in result if m.get("role") == "tool"][0]
        assert tool_msg["tool_call_id"] == "call_abc123"


# --- Bug 2: Anthropic tool_use_id sanitization ---

class TestAnthropicToolUseIdSanitization:
    """Anthropic _convert_messages_to_claude_format must produce valid tool_use_id."""

    def _convert(self, messages):
        from llm_provider.anthropic_provider import AnthropicProvider
        provider = AnthropicProvider.__new__(AnthropicProvider)
        return provider._convert_messages_to_claude_format(messages)

    def test_openai_ids_remain_valid(self):
        """OpenAI-format call_xxx IDs pass Anthropic regex."""
        messages = [
            {"role": "user", "content": "test"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_abc123", "type": "function",
                 "function": {"name": "search", "arguments": "{}"}}
            ]},
            {"role": "tool", "tool_call_id": "call_abc123", "content": "result"},
        ]
        _, claude_msgs = self._convert(messages)
        for msg in claude_msgs:
            if isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        assert TOOL_ID_PATTERN.match(block["id"]), f"Invalid: {block['id']!r}"
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        assert TOOL_ID_PATTERN.match(block["tool_use_id"]), f"Invalid: {block['tool_use_id']!r}"

    def test_empty_ids_get_valid_fallback(self):
        """Empty string IDs must be replaced with valid fallbacks."""
        messages = [
            {"role": "user", "content": "test"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "", "type": "function",
                 "function": {"name": "search", "arguments": "{}"}}
            ]},
            {"role": "tool", "tool_call_id": "", "content": "result"},
        ]
        _, claude_msgs = self._convert(messages)
        for msg in claude_msgs:
            if isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        assert TOOL_ID_PATTERN.match(block["id"]), \
                            f"Empty ID should be replaced: {block['id']!r}"
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        assert TOOL_ID_PATTERN.match(block["tool_use_id"]), \
                            f"Empty ID should be replaced: {block['tool_use_id']!r}"

    def test_ids_with_special_chars_sanitized(self):
        """IDs with dots/colons/spaces must be sanitized."""
        messages = [
            {"role": "user", "content": "test"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call.abc.123", "type": "function",
                 "function": {"name": "search", "arguments": "{}"}}
            ]},
            {"role": "tool", "tool_call_id": "call.abc.123", "content": "result"},
        ]
        _, claude_msgs = self._convert(messages)
        for msg in claude_msgs:
            if isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        assert TOOL_ID_PATTERN.match(block["id"]), \
                            f"Dotted ID should be sanitized: {block['id']!r}"
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        assert TOOL_ID_PATTERN.match(block["tool_use_id"]), \
                            f"Dotted ID should be sanitized: {block['tool_use_id']!r}"


# --- Integration: ShanClaw multi-turn conversation ---

class TestCrossProviderToolMessages:
    """Simulate the exact production failure: ShanClaw multi-turn tool
    conversation routed to different providers."""

    SHANCLAW_CONVERSATION = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What's the weather?"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "call_abc123", "type": "function",
             "function": {"name": "get_weather", "arguments": '{"city": "Tokyo"}'}}
        ]},
        {"role": "tool", "tool_call_id": "call_abc123", "content": "Sunny, 25C"},
        {"role": "assistant", "content": "The weather in Tokyo is sunny at 25C."},
        {"role": "user", "content": "How about Osaka?"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "call_def456", "type": "function",
             "function": {"name": "get_weather", "arguments": '{"city": "Osaka"}'}}
        ]},
        {"role": "tool", "tool_call_id": "call_def456", "content": "Rainy, 18C"},
    ]

    def test_shanclaw_messages_to_anthropic(self):
        """ShanClaw OpenAI-format messages must convert cleanly to Anthropic."""
        from llm_provider.anthropic_provider import AnthropicProvider
        provider = AnthropicProvider.__new__(AnthropicProvider)
        _, claude_msgs = provider._convert_messages_to_claude_format(
            self.SHANCLAW_CONVERSATION
        )
        for msg in claude_msgs:
            if isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        assert TOOL_ID_PATTERN.match(block["id"]), \
                            f"Invalid tool_use id: {block['id']!r}"
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        assert TOOL_ID_PATTERN.match(block["tool_use_id"]), \
                            f"Invalid tool_use_id: {block['tool_use_id']!r}"

    def test_shanclaw_messages_to_openai(self):
        """ShanClaw messages through prepare_openai_messages must have valid IDs."""
        result = prepare_openai_messages(self.SHANCLAW_CONVERSATION)
        for msg in result:
            if msg.get("role") == "tool":
                assert msg.get("tool_call_id"), f"Empty tool_call_id: {msg}"
            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    assert tc.get("id"), f"Empty tool_call id: {tc}"


# --- Bug 3: OpenAI/Groq functions → tools conversion ---

@pytest.mark.skipif(not _has_openai, reason="openai SDK not installed")
class TestFunctionsToToolsConversion:
    """OpenAI provider must detect role:'tool' messages and convert
    legacy functions to modern tools param."""

    SAMPLE_FUNCTIONS = [
        {"name": "get_weather", "description": "Get weather",
         "parameters": {"type": "object", "properties": {"city": {"type": "string"}}}}
    ]

    def test_has_tool_role_messages_true(self):
        from llm_provider.openai_provider import OpenAIProvider as cls
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "tool", "tool_call_id": "call_123", "content": "result"},
        ]
        assert cls._has_tool_role_messages(messages) is True

    def test_has_tool_role_messages_false(self):
        from llm_provider.openai_provider import OpenAIProvider as cls
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        assert cls._has_tool_role_messages(messages) is False

    def test_has_tool_role_messages_empty(self):
        from llm_provider.openai_provider import OpenAIProvider as cls
        assert cls._has_tool_role_messages([]) is False

    def test_functions_to_tools_wraps_correctly(self):
        from llm_provider.openai_provider import OpenAIProvider as cls
        tools = cls._functions_to_tools_param(self.SAMPLE_FUNCTIONS)
        assert len(tools) == 1
        assert tools[0]["type"] == "function"
        assert tools[0]["function"]["name"] == "get_weather"
        assert tools[0]["function"]["parameters"] == self.SAMPLE_FUNCTIONS[0]["parameters"]

    def test_functions_to_tools_idempotent(self):
        """Already-wrapped tools format should pass through unchanged."""
        from llm_provider.openai_provider import OpenAIProvider as cls
        already_wrapped = [{"type": "function", "function": self.SAMPLE_FUNCTIONS[0]}]
        tools = cls._functions_to_tools_param(already_wrapped)
        assert len(tools) == 1
        assert tools[0] is already_wrapped[0]  # same object, not re-wrapped

    def test_functions_to_tools_skips_non_dict(self):
        from llm_provider.openai_provider import OpenAIProvider as cls
        tools = cls._functions_to_tools_param(["not_a_dict", None, 42])
        assert tools == []


# --- Bug 4: Legacy function_call → tool_calls upgrade ---

class TestFunctionCallToToolCallsUpgrade:
    """When messages contain role:'tool' + assistant function_call (legacy),
    prepare_openai_messages must upgrade function_call to tool_calls."""

    LEGACY_CONVERSATION = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What's the weather?"},
        # Legacy format: function_call instead of tool_calls
        {"role": "assistant", "content": None,
         "function_call": {"name": "get_weather", "arguments": '{"city": "Tokyo"}'}},
        # Modern format: role:"tool"
        {"role": "tool", "tool_call_id": "call_abc123", "content": "Sunny, 25C"},
        {"role": "assistant", "content": "It's sunny in Tokyo."},
        {"role": "user", "content": "How about Osaka?"},
    ]

    def test_detects_function_call_tool_mismatch(self):
        """_has_function_call_tool_mismatch detects legacy + modern mix."""
        assert _has_function_call_tool_mismatch(self.LEGACY_CONVERSATION) is True

    def test_no_mismatch_when_no_tool_role(self):
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": None,
             "function_call": {"name": "foo", "arguments": "{}"}},
        ]
        assert _has_function_call_tool_mismatch(messages) is False

    def test_no_mismatch_when_already_tool_calls(self):
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_123", "type": "function",
                 "function": {"name": "foo", "arguments": "{}"}}
            ]},
            {"role": "tool", "tool_call_id": "call_123", "content": "result"},
        ]
        assert _has_function_call_tool_mismatch(messages) is False

    def test_upgrade_function_call_to_tool_calls(self):
        """Legacy function_call must be converted to tool_calls format."""
        result = prepare_openai_messages(self.LEGACY_CONVERSATION)

        # Find the upgraded assistant message
        upgraded = [m for m in result if m.get("tool_calls")]
        assert len(upgraded) == 1, f"Expected 1 upgraded message, got {len(upgraded)}"

        tc = upgraded[0]["tool_calls"][0]
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "get_weather"
        assert tc["function"]["arguments"] == '{"city": "Tokyo"}'
        assert tc["id"], "tool_call must have a non-empty ID"

        # function_call key should be removed
        assert "function_call" not in upgraded[0]

    def test_upgrade_preserves_other_messages(self):
        """Non-function_call messages must pass through unchanged."""
        result = prepare_openai_messages(self.LEGACY_CONVERSATION)
        # System, user, tool, assistant (text), user should all be present
        roles = [m["role"] for m in result]
        assert roles == ["system", "user", "assistant", "tool", "assistant", "user"]

    def test_fast_path_upgrade(self):
        """Fast path (all string content) should still upgrade function_call."""
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "Let me check.",
             "function_call": {"name": "search", "arguments": '{"q": "test"}'}},
            {"role": "tool", "tool_call_id": "call_999", "content": "result"},
            {"role": "assistant", "content": "Found it."},
        ]
        result = prepare_openai_messages(messages)
        upgraded = [m for m in result if m.get("tool_calls")]
        assert len(upgraded) == 1
        assert "function_call" not in upgraded[0]
        assert upgraded[0]["content"] == "Let me check."


# --- Bug 5: Defensive sanitization of malformed history ---

class TestSanitizeCompletionMessages:
    """sanitize_completion_messages must strip malformed entries that crash providers."""

    def test_strips_tool_call_placeholders(self):
        messages = [
            {"role": "user", "content": "search for cats"},
            {"role": "assistant", "content": "[tool_call: web_search]"},
            {"role": "assistant", "content": "Here are the results."},
        ]
        result = sanitize_completion_messages(messages)
        assert len(result) == 2
        assert result[-1]["content"] == "Here are the results."

    def test_strips_error_markers(self):
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "[error: agent failed to respond]"},
            {"role": "assistant", "content": "Hello!"},
        ]
        result = sanitize_completion_messages(messages)
        assert len(result) == 2

    def test_strips_friendly_error_messages(self):
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "I apologize, but I encountered an error."},
            {"role": "user", "content": "try again"},
            {"role": "assistant", "content": "Hello!"},
        ]
        result = sanitize_completion_messages(messages)
        # Error assistant stripped → two consecutive users merged → 2 messages
        assert len(result) == 2
        roles = [m["role"] for m in result]
        assert roles == ["user", "assistant"]
        assert result[0]["content"] == "try again"

    def test_drops_orphaned_tool_results(self):
        """role:'tool' without preceding tool_calls must be dropped."""
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "tool", "tool_call_id": "call_123", "content": "result"},
            {"role": "assistant", "content": "Hello!"},
        ]
        result = sanitize_completion_messages(messages)
        assert len(result) == 2
        assert not any(m.get("role") == "tool" for m in result)

    def test_keeps_valid_tool_results(self):
        """role:'tool' following tool_calls assistant must be kept."""
        messages = [
            {"role": "user", "content": "weather?"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_123", "type": "function",
                 "function": {"name": "get_weather", "arguments": "{}"}}
            ]},
            {"role": "tool", "tool_call_id": "call_123", "content": "Sunny"},
            {"role": "assistant", "content": "It's sunny!"},
        ]
        result = sanitize_completion_messages(messages)
        assert len(result) == 4

    def test_merges_consecutive_same_role(self):
        """Consecutive assistant messages should be merged (keep last)."""
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "first"},
            {"role": "assistant", "content": "second"},
            {"role": "user", "content": "ok"},
        ]
        result = sanitize_completion_messages(messages)
        assert len(result) == 3
        assert result[1]["content"] == "second"

    def test_preserves_consecutive_tool_messages(self):
        """Multiple role:'tool' messages in a row should NOT be merged."""
        messages = [
            {"role": "user", "content": "do both"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_1", "type": "function",
                 "function": {"name": "a", "arguments": "{}"}},
                {"id": "call_2", "type": "function",
                 "function": {"name": "b", "arguments": "{}"}},
            ]},
            {"role": "tool", "tool_call_id": "call_1", "content": "result_a"},
            {"role": "tool", "tool_call_id": "call_2", "content": "result_b"},
        ]
        result = sanitize_completion_messages(messages)
        assert len(result) == 4

    def test_empty_messages_unchanged(self):
        assert sanitize_completion_messages([]) == []

    def test_normal_conversation_unchanged(self):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        result = sanitize_completion_messages(messages)
        assert result == messages

    def test_production_corrupted_session(self):
        """Simulate the exact corruption pattern from little-v's session."""
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "search the web for AI news"},
            {"role": "assistant", "content": "Let me search for that."},
            # Heartbeat corruption starts here
            {"role": "assistant", "content": "[tool_call: web_search]"},
            {"role": "tool", "tool_call_id": "", "content": "search results here"},
            {"role": "assistant", "content": "[tool_call: web_search]"},
            {"role": "tool", "tool_call_id": "", "content": "more results"},
            {"role": "assistant", "content": "I apologize, but I encountered an error processing your request."},
            {"role": "assistant", "content": "[error: agent failed to respond]"},
            # Real user message after corruption
            {"role": "user", "content": "try again"},
        ]
        result = sanitize_completion_messages(messages)
        # Should be: system, user, assistant ("Let me search"), user ("try again")
        assert len(result) == 4
        roles = [m["role"] for m in result]
        assert roles == ["system", "user", "assistant", "user"]
        assert result[2]["content"] == "Let me search for that."
        assert result[3]["content"] == "try again"
