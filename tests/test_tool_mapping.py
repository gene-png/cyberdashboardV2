"""Tests for the mapping_suggester service."""
import json
import pytest
from unittest.mock import MagicMock, patch
from app.services.mapping_suggester import (
    build_mapping_prompt,
    suggest_mappings,
    _parse_suggestions,
)


# Minimal framework fixture
FRAMEWORK = {
    "name": "Test Framework",
    "pillars": [
        {
            "id": "identity",
            "name": "Identity",
            "activities": [
                {"id": "ID-1.1", "name": "MFA Enforcement", "description": "Require MFA"},
                {"id": "ID-1.2", "name": "Identity Governance", "description": "Manage identities"},
            ],
        },
        {
            "id": "device",
            "name": "Device",
            "activities": [
                {"id": "DE-1.1", "name": "Device Inventory", "description": "Track all devices"},
            ],
        },
    ],
}


def _mock_tool(name="CrowdStrike Falcon", vendor="CrowdStrike", category="EDR"):
    tool = MagicMock()
    tool.id = "tool-uuid-1"
    tool.name = name
    tool.vendor = vendor
    tool.category = category
    tool.notes = "Deployed to 500 endpoints"
    return tool


# ---- build_mapping_prompt ----

def test_build_prompt_contains_tool_name():
    tool = _mock_tool()
    prompt = build_mapping_prompt(tool, FRAMEWORK)
    assert "CrowdStrike Falcon" in prompt


def test_build_prompt_contains_all_activity_ids():
    tool = _mock_tool()
    prompt = build_mapping_prompt(tool, FRAMEWORK)
    assert "ID-1.1" in prompt
    assert "ID-1.2" in prompt
    assert "DE-1.1" in prompt


def test_build_prompt_contains_pillar_names():
    tool = _mock_tool()
    prompt = build_mapping_prompt(tool, FRAMEWORK)
    assert "Identity" in prompt
    assert "Device" in prompt


def test_build_prompt_shows_activity_count():
    tool = _mock_tool()
    prompt = build_mapping_prompt(tool, FRAMEWORK)
    assert "3" in prompt  # 3 total activities


# ---- _parse_suggestions ----

def test_parse_valid_json():
    raw = json.dumps([
        {"activity_id": "ID-1.1", "confidence": "high", "rationale": "EDR monitors identity events."},
    ])
    results = _parse_suggestions(raw, FRAMEWORK)
    assert len(results) == 1
    assert results[0]["activity_id"] == "ID-1.1"
    assert results[0]["confidence"] == "high"


def test_parse_strips_markdown_fences():
    raw = "```json\n" + json.dumps([
        {"activity_id": "DE-1.1", "confidence": "medium", "rationale": "Tracks devices."}
    ]) + "\n```"
    results = _parse_suggestions(raw, FRAMEWORK)
    assert len(results) == 1
    assert results[0]["activity_id"] == "DE-1.1"


def test_parse_filters_invalid_activity_ids():
    raw = json.dumps([
        {"activity_id": "INVALID-99", "confidence": "high", "rationale": "Does not exist."},
        {"activity_id": "ID-1.1", "confidence": "low", "rationale": "Valid."},
    ])
    results = _parse_suggestions(raw, FRAMEWORK)
    assert len(results) == 1
    assert results[0]["activity_id"] == "ID-1.1"


def test_parse_deduplicates():
    raw = json.dumps([
        {"activity_id": "ID-1.1", "confidence": "high", "rationale": "First."},
        {"activity_id": "ID-1.1", "confidence": "low", "rationale": "Duplicate."},
    ])
    results = _parse_suggestions(raw, FRAMEWORK)
    assert len(results) == 1


def test_parse_bad_json_returns_empty():
    results = _parse_suggestions("this is not json", FRAMEWORK)
    assert results == []


def test_parse_non_list_returns_empty():
    results = _parse_suggestions('{"activity_id": "ID-1.1"}', FRAMEWORK)
    assert results == []


def test_parse_invalid_confidence_normalized():
    raw = json.dumps([
        {"activity_id": "ID-1.1", "confidence": "very_high", "rationale": "Test."}
    ])
    results = _parse_suggestions(raw, FRAMEWORK)
    assert results[0]["confidence"] == "medium"


def test_parse_rationale_truncated():
    long_rationale = "x" * 600
    raw = json.dumps([
        {"activity_id": "ID-1.1", "confidence": "high", "rationale": long_rationale}
    ])
    results = _parse_suggestions(raw, FRAMEWORK)
    assert len(results[0]["rationale"]) <= 500


# ---- suggest_mappings ----

def test_suggest_mappings_no_api_key():
    tool = _mock_tool()
    result = suggest_mappings(tool, FRAMEWORK, api_key="", model="claude-sonnet-4-6")
    assert len(result) == 2
    suggestions, error = result
    assert suggestions == []
    assert "ANTHROPIC_API_KEY" in error


def test_suggest_mappings_success():
    tool = _mock_tool()
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps([
        {"activity_id": "ID-1.1", "confidence": "high", "rationale": "EDR covers identity."}
    ]))]
    mock_message.model = "claude-sonnet-4-6"
    mock_message.usage.input_tokens = 100
    mock_message.usage.output_tokens = 50

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with patch("anthropic.Anthropic", return_value=mock_client):
        result = suggest_mappings(tool, FRAMEWORK, api_key="sk-test", model="claude-sonnet-4-6")

    assert len(result) == 5
    suggestions, error, prompt_text, raw_response, used_model = result
    assert error is None
    assert len(suggestions) == 1
    assert suggestions[0]["activity_id"] == "ID-1.1"
    assert "ID-1.1" in prompt_text
    assert used_model == "claude-sonnet-4-6"


def test_suggest_mappings_api_exception():
    tool = _mock_tool()
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("Connection refused")

    with patch("anthropic.Anthropic", return_value=mock_client):
        result = suggest_mappings(tool, FRAMEWORK, api_key="sk-test", model="claude-sonnet-4-6")

    assert len(result) == 2
    suggestions, error = result
    assert suggestions == []
    assert "API call failed" in error
