from unittest.mock import AsyncMock, MagicMock

import pytest
from openai import APIConnectionError, APIStatusError

from warden.adapters.outbound.llm.openai_client import OpenAIClient
from warden.domain.models.decision import Action
from warden.infrastructure.config import Settings
from warden.infrastructure.exceptions import LLMResponseMalformedError, LLMUnavailableError
from tests.fixtures.events import make_event

_VALID = (
    '{"action": "restart", "confidence": 0.85,'
    ' "reasoning": "cpu spike detected above threshold", "safe_to_auto": true}'
)


def make_client() -> OpenAIClient:
    settings = Settings(
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        USE_MOCK_LLM=False,
        OPENAI_API_KEY="test-key",
    )
    return OpenAIClient(settings)


def test_parse_valid_json_returns_decision():
    result = make_client()._parse(_VALID)
    assert result.action == Action.RESTART
    assert result.confidence == 0.85
    assert result.safe_to_auto is True


def test_parse_invalid_json_raises():
    with pytest.raises(LLMResponseMalformedError, match="Invalid JSON"):
        make_client()._parse("not valid json {{")


def test_parse_wrong_schema_raises():
    with pytest.raises(LLMResponseMalformedError, match="schema mismatch"):
        make_client()._parse(
            '{"action": "restart", "confidence": "nan", "reasoning": "ok", "safe_to_auto": true}'
        )


def test_parse_unknown_action_raises():
    with pytest.raises(LLMResponseMalformedError):
        make_client()._parse(
            '{"action": "nuke", "confidence": 0.9,'
            ' "reasoning": "valid reason for testing purposes here", "safe_to_auto": false}'
        )


def test_parse_empty_reasoning_raises():
    with pytest.raises(LLMResponseMalformedError, match="empty or insufficient"):
        make_client()._parse(
            '{"action": "restart", "confidence": 0.8, "reasoning": "", "safe_to_auto": true}'
        )


def test_parse_short_reasoning_raises():
    with pytest.raises(LLMResponseMalformedError, match="empty or insufficient"):
        make_client()._parse(
            '{"action": "restart", "confidence": 0.8, "reasoning": "short", "safe_to_auto": true}'
        )


def test_strip_fences_removes_code_block():
    raw = "```json\n{\"key\": \"value\"}\n```"
    assert OpenAIClient._strip_fences(raw) == '{"key": "value"}'


def test_strip_fences_plain_json_unchanged():
    raw = '{"action": "restart"}'
    assert OpenAIClient._strip_fences(raw) == raw


async def test_reason_connection_error_raises_llm_unavailable():
    client = make_client()
    client._client = AsyncMock()
    client._client.chat.completions.create.side_effect = APIConnectionError(request=MagicMock())
    with pytest.raises(LLMUnavailableError):
        await client.reason(make_event(), [])


async def test_reason_api_status_error_raises_llm_unavailable():
    client = make_client()
    client._client = AsyncMock()
    client._client.chat.completions.create.side_effect = APIStatusError(
        "error", response=MagicMock(status_code=500), body={}
    )
    with pytest.raises(LLMUnavailableError):
        await client.reason(make_event(), [])


async def test_reason_success_returns_decision():
    client = make_client()
    mock_response = MagicMock()
    mock_response.choices[0].message.content = _VALID
    client._client = AsyncMock()
    client._client.chat.completions.create.return_value = mock_response
    result = await client.reason(make_event(), [])
    assert result.action == Action.RESTART
    assert result.confidence == 0.85
