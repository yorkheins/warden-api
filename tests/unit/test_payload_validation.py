import pytest
from pydantic import ValidationError

from warden.adapters.inbound.http.schemas.event_schemas import EventWebhookRequest

VALID = {
    "project_id": "my-service",
    "environment_id": "dev",
    "severity": "medium",
    "signal": "high_error_rate",
    "context": {"error_rate": 0.5},
    "timestamp": "2026-05-27T10:00:00Z",
}


def req(**overrides):
    return {**VALID, **overrides}


def test_valid_payload():
    r = EventWebhookRequest(**VALID)
    assert r.project_id == "my-service"


def test_severity_lowercase():
    r = EventWebhookRequest(**req(severity="medium"))
    assert r.severity.value == "medium"


def test_severity_uppercase_normalized():
    r = EventWebhookRequest(**req(severity="MEDIUM"))
    assert r.severity.value == "medium"


def test_severity_mixed_case_normalized():
    r = EventWebhookRequest(**req(severity="Medium"))
    assert r.severity.value == "medium"


def test_invalid_severity_rejected():
    with pytest.raises(ValidationError):
        EventWebhookRequest(**req(severity="ultra"))


def test_missing_project_id_rejected():
    payload = {k: v for k, v in VALID.items() if k != "project_id"}
    with pytest.raises(ValidationError):
        EventWebhookRequest(**payload)


def test_empty_signal_rejected():
    with pytest.raises(ValidationError):
        EventWebhookRequest(**req(signal=""))


def test_naive_timestamp_rejected():
    with pytest.raises(ValidationError):
        EventWebhookRequest(**req(timestamp="2026-05-27T10:00:00"))


def test_extra_field_forbidden():
    with pytest.raises(ValidationError):
        EventWebhookRequest(**req(unknown_field="value"))


def test_context_accepts_nested_json():
    r = EventWebhookRequest(**req(context={"nested": {"key": "value"}, "list": [1, 2, 3]}))
    assert r.context["nested"]["key"] == "value"


def test_context_defaults_to_empty_dict():
    payload = {k: v for k, v in VALID.items() if k != "context"}
    r = EventWebhookRequest(**payload)
    assert r.context == {}
