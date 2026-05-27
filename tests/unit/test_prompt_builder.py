import uuid
from datetime import datetime, timezone

from warden.adapters.outbound.llm.prompt_builder import SYSTEM_PROMPT, build_user_prompt
from warden.domain.models.decision import Action
from warden.domain.models.workload_history import OutcomeStatus, WorkloadHistoryEntry
from tests.fixtures.events import make_event


def make_entry(
    signal: str = "high_cpu",
    action: Action = Action.RESTART,
    was_auto: bool = True,
    outcome: OutcomeStatus = OutcomeStatus.SUCCESS,
    human_feedback: str | None = None,
    feedback_reason: str | None = None,
    alternative_action: str | None = None,
) -> WorkloadHistoryEntry:
    return WorkloadHistoryEntry(
        id=uuid.uuid4(),
        project_id="svc",
        environment_id="dev",
        event_id=uuid.uuid4(),
        signal=signal,
        action_decided=action,
        was_auto=was_auto,
        outcome=outcome,
        human_feedback=human_feedback,
        created_at=datetime.now(timezone.utc),
        feedback_reason=feedback_reason,
        alternative_action=alternative_action,
    )


def test_no_history_contains_no_incidents_message():
    prompt = build_user_prompt(make_event(), [])
    assert "No previous incidents" in prompt


def test_event_fields_appear_in_prompt():
    event = make_event(project_id="payments", environment_id="prod", signal="latency_spike",
                       context={"p99_ms": 2500})
    prompt = build_user_prompt(event, [])
    assert "payments" in prompt
    assert "prod" in prompt
    assert "latency_spike" in prompt
    assert "2500" in prompt


def test_history_auto_executed_label():
    prompt = build_user_prompt(make_event(), [make_entry(was_auto=True)])
    assert "auto-executed" in prompt


def test_history_required_approval_label():
    prompt = build_user_prompt(make_event(), [make_entry(was_auto=False)])
    assert "required human approval" in prompt


def test_history_shows_human_feedback():
    prompt = build_user_prompt(make_event(), [make_entry(human_feedback="risky during peak")])
    assert "risky during peak" in prompt


def test_history_shows_feedback_reason():
    prompt = build_user_prompt(make_event(), [make_entry(feedback_reason="too_risky")])
    assert "too_risky" in prompt


def test_history_shows_alternative_action():
    prompt = build_user_prompt(make_event(), [make_entry(alternative_action="scale_up")])
    assert "scale_up" in prompt


def test_multiple_history_entries_all_shown():
    entries = [
        make_entry(signal="cpu_spike", action=Action.RESTART),
        make_entry(signal="memory_leak", action=Action.ROLLBACK, was_auto=False),
    ]
    prompt = build_user_prompt(make_event(), entries)
    assert "cpu_spike" in prompt
    assert "memory_leak" in prompt


def test_context_marked_as_untrusted():
    prompt = build_user_prompt(make_event(), [])
    assert "UNTRUSTED" in prompt


def test_system_prompt_contains_all_actions():
    for action in ["rollback", "restart", "scale_up", "notify_human", "no_action"]:
        assert action in SYSTEM_PROMPT
