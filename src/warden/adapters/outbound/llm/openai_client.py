import json
import re

import structlog
from openai import AsyncOpenAI, APIConnectionError, APIStatusError, APITimeoutError
from pydantic import BaseModel, Field, ValidationError

from warden.adapters.outbound.llm.prompt_builder import SYSTEM_PROMPT, build_user_prompt
from warden.domain.models.decision import Action, LLMRawDecision
from warden.domain.models.event import Event
from warden.domain.models.workload_history import WorkloadHistoryEntry
from warden.domain.ports.llm_client import LLMClient
from warden.infrastructure.config import Settings
from warden.infrastructure.exceptions import LLMResponseMalformedError, LLMUnavailableError

log = structlog.get_logger(__name__)


class _LLMResponse(BaseModel):
    action: Action
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    safe_to_auto: bool


class OpenAIClient(LLMClient):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )

    async def reason(
        self, event: Event, history: list[WorkloadHistoryEntry]
    ) -> LLMRawDecision:
        try:
            response = await self._client.chat.completions.create(
                model=self._settings.LLM_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_prompt(event, history)},
                ],
                response_format={"type": "json_object"},
            )
        except (APIConnectionError, APITimeoutError) as e:
            raise LLMUnavailableError(f"OpenAI unreachable: {e}") from e
        except APIStatusError as e:
            raise LLMUnavailableError(f"OpenAI error {e.status_code}: {e.message}") from e

        raw_content = response.choices[0].message.content or ""
        return self._parse(raw_content)

    def _parse(self, raw: str) -> LLMRawDecision:
        try:
            cleaned = self._strip_fences(raw)
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise LLMResponseMalformedError(f"Invalid JSON from LLM: {e}") from e

        try:
            parsed = _LLMResponse.model_validate(data)
        except ValidationError as e:
            raise LLMResponseMalformedError(f"LLM response schema mismatch: {e}") from e

        if not parsed.reasoning or len(parsed.reasoning.strip()) < 10:
            raise LLMResponseMalformedError("LLM returned empty or insufficient reasoning")

        return LLMRawDecision(
            action=parsed.action,
            confidence=parsed.confidence,
            reasoning=parsed.reasoning,
            safe_to_auto=parsed.safe_to_auto,
        )

    @staticmethod
    def _strip_fences(raw: str) -> str:
        match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
        return match.group(1) if match else raw.strip()
