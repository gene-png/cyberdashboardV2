"""Unit tests for attack_mapper service."""
import json
import pytest
from unittest.mock import MagicMock, patch

from app.services.attack_mapper import (
    classify_gap_status,
    get_tool_fingerprint,
    build_attack_mapping_prompt,
    map_tool_to_techniques,
    _parse_results,
)


# ---- classify_gap_status ----

def test_gap_none_when_no_tools():
    assert classify_gap_status([], [], []) == "None"

def test_gap_full_when_detect_and_prevent():
    assert classify_gap_status(["ToolA"], ["ToolB"], []) == "Full"

def test_gap_full_when_same_tool_detect_and_prevent():
    assert classify_gap_status(["ToolA"], ["ToolA"], []) == "Full"

def test_gap_single_tool_when_only_one_tool_total():
    assert classify_gap_status(["ToolA"], [], []) == "Single Tool"

def test_gap_detect_only_when_multiple_detect_no_prevent():
    assert classify_gap_status(["ToolA", "ToolB"], [], []) == "Detect Only"

def test_gap_prevent_only_when_multiple_prevent_no_detect():
    assert classify_gap_status([], ["ToolA", "ToolB"], []) == "Prevent Only"

def test_gap_single_tool_respond_only():
    assert classify_gap_status([], [], ["ToolA"]) == "Single Tool"

def test_gap_full_with_respond_present():
    assert classify_gap_status(["ToolA"], ["ToolB"], ["ToolC"]) == "Full"


# ---- get_tool_fingerprint ----

def _make_tool(name="Splunk", vendor="Splunk Inc", category="SIEM", notes=""):
    t = MagicMock()
    t.name = name
    t.vendor = vendor
    t.category = category
    t.notes = notes
    return t

def test_fingerprint_is_deterministic():
    tool = _make_tool()
    fp1 = get_tool_fingerprint(tool, ["1.1.1", "2.2.2"])
    fp2 = get_tool_fingerprint(tool, ["2.2.2", "1.1.1"])  # same activities, different order
    assert fp1 == fp2

def test_fingerprint_changes_when_activity_added():
    tool = _make_tool()
    fp1 = get_tool_fingerprint(tool, ["1.1.1"])
    fp2 = get_tool_fingerprint(tool, ["1.1.1", "2.2.2"])
    assert fp1 != fp2

def test_fingerprint_changes_when_tool_name_changes():
    t1 = _make_tool(name="Splunk")
    t2 = _make_tool(name="QRadar")
    fp1 = get_tool_fingerprint(t1, [])
    fp2 = get_tool_fingerprint(t2, [])
    assert fp1 != fp2

def test_fingerprint_is_32_chars():
    tool = _make_tool()
    fp = get_tool_fingerprint(tool, [])
    assert len(fp) == 32


# ---- _parse_results ----

VALID_IDS = {"T1078", "T1098", "T1055.001"}

def test_parse_valid_response():
    raw = json.dumps([
        {"technique_id": "T1078", "coverage_type": "detect", "confidence": "high", "rationale": "Logs auth events."}
    ])
    results = _parse_results(raw, VALID_IDS)
    assert len(results) == 1
    assert results[0]["technique_id"] == "T1078"
    assert results[0]["coverage_type"] == "detect"

def test_parse_strips_markdown_fences():
    raw = "```json\n" + json.dumps([
        {"technique_id": "T1098", "coverage_type": "prevent", "confidence": "medium", "rationale": "Blocks changes."}
    ]) + "\n```"
    results = _parse_results(raw, VALID_IDS)
    assert len(results) == 1

def test_parse_filters_unknown_technique_ids():
    raw = json.dumps([
        {"technique_id": "T9999", "coverage_type": "detect", "confidence": "high", "rationale": "Unknown."},
        {"technique_id": "T1078", "coverage_type": "detect", "confidence": "high", "rationale": "Valid."},
    ])
    results = _parse_results(raw, VALID_IDS)
    assert len(results) == 1
    assert results[0]["technique_id"] == "T1078"

def test_parse_invalid_coverage_type_defaults_to_detect():
    raw = json.dumps([
        {"technique_id": "T1078", "coverage_type": "INVALID", "confidence": "high", "rationale": "Test."}
    ])
    results = _parse_results(raw, VALID_IDS)
    assert results[0]["coverage_type"] == "detect"

def test_parse_bad_json_returns_empty():
    assert _parse_results("not json", VALID_IDS) == []

def test_parse_deduplicates():
    raw = json.dumps([
        {"technique_id": "T1078", "coverage_type": "detect", "confidence": "high", "rationale": "First."},
        {"technique_id": "T1078", "coverage_type": "prevent", "confidence": "low", "rationale": "Dup."},
    ])
    results = _parse_results(raw, VALID_IDS)
    assert len(results) == 1


# ---- map_tool_to_techniques — caching ----

def _make_technique(full_id):
    t = MagicMock()
    t.full_id = full_id
    t.technique_id = full_id.split(".")[0]
    t.name = f"Technique {full_id}"
    t.tactic = "Initial Access"
    return t

TECHNIQUES = [_make_technique("T1078"), _make_technique("T1098")]

def test_map_uses_cache_when_fingerprint_matches():
    tool = _make_tool()
    activity_ids = ["act.1"]
    cached = MagicMock()
    cached.tool_fingerprint = get_tool_fingerprint(tool, activity_ids)
    cached.response_payload = json.dumps([
        {"technique_id": "T1078", "coverage_type": "detect", "confidence": "high", "rationale": "From cache."}
    ])

    # anthropic is lazily imported inside the function; patch at the top-level module
    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        results, error = map_tool_to_techniques(
            tool, activity_ids, TECHNIQUES, api_key="sk-test",
            model="claude-sonnet-4-6", cached_run=cached,
        )

    assert error is None
    assert len(results) == 1
    assert results[0]["rationale"] == "From cache."
    mock_anthropic_cls.assert_not_called()

def test_map_calls_api_when_no_cache():
    tool = _make_tool()
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps([
        {"technique_id": "T1078", "coverage_type": "detect", "confidence": "high", "rationale": "Fresh."}
    ]))]
    mock_message.model = "claude-sonnet-4-6"
    mock_message.usage.input_tokens = 500
    mock_message.usage.output_tokens = 100

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with patch("anthropic.Anthropic", return_value=mock_client):
        results, error = map_tool_to_techniques(
            tool, ["act.1"], TECHNIQUES, api_key="sk-test",
            model="claude-sonnet-4-6", cached_run=None,
        )

    assert error is None
    assert len(results) == 1

def test_map_returns_error_when_no_api_key():
    tool = _make_tool()
    results, error = map_tool_to_techniques(
        tool, [], TECHNIQUES, api_key="", model="claude-sonnet-4-6", cached_run=None
    )
    assert results == []
    assert "ANTHROPIC_API_KEY" in error

def test_map_returns_error_on_api_exception():
    tool = _make_tool()
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("timeout")

    with patch("anthropic.Anthropic", return_value=mock_client):
        results, error = map_tool_to_techniques(
            tool, [], TECHNIQUES, api_key="sk-test",
            model="claude-sonnet-4-6", cached_run=None,
        )

    assert results == []
    assert "API call failed" in error
