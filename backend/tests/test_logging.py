"""The log must never become an exfiltration path for credentials."""

import json

from app.logging_utils import configure_logging, log_event, request_id_var


def _emit(capsys, **fields) -> dict:
    # configure_logging installs its own stdout handler (replacing any others),
    # so the log line is read back from stdout rather than from caplog.
    configure_logging("INFO")
    log_event("test_event", **fields)
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def test_credential_shaped_fields_are_redacted(capsys):
    record = _emit(
        capsys,
        llm_api_key="sk-proj-realkeymaterial",
        authorization="Bearer sk-proj-realkeymaterial",
        access_token="t0ken",
        client_secret="shhh",
        query="melanoma by phase",
    )
    for field in ("llm_api_key", "authorization", "access_token", "client_secret"):
        assert record[field] == "***"
    assert "sk-proj-realkeymaterial" not in json.dumps(record)
    assert record["query"] == "melanoma by phase", "ordinary fields must survive"


def test_every_event_carries_the_request_id(capsys):
    request_id_var.set("abc123")
    try:
        record = _emit(capsys, detail="x")
        assert record["request_id"] == "abc123"
        assert record["event"] == "test_event"
    finally:
        request_id_var.set("-")


def test_llm_completion_logs_plan_field_names_not_values(capsys):
    """The field is named so the scrubber does not blank a useful diagnostic."""
    record = _emit(capsys, model="gpt-4.1-mini", plan_fields=["intent", "search_terms"])
    assert record["plan_fields"] == ["intent", "search_terms"]
