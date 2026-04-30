"""
AI-derived tool-to-activity mapping suggestions (spec §7.1 / ADR-001).

Calls Claude with the tool's details and the full list of framework activities,
asking it to suggest which activities the tool likely contributes to.

Graceful-degrade: returns ([], error_message) if API is unavailable or the
response cannot be parsed. Logs the raw request/response for audit.
"""
import json
import time
import logging
from typing import Any

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a cybersecurity expert helping map security tools to Zero Trust framework "
    "activities. You will receive a tool description and a list of framework activities. "
    "Respond ONLY with a valid JSON array — no markdown fences, no preamble, no trailing "
    "text. Each element must have exactly the keys: activity_id, confidence, rationale. "
    "confidence must be one of: high, medium, low. rationale must be 1-2 sentences. "
    "Only include activities where the tool genuinely contributes. Omit activities where "
    "there is no meaningful contribution."
)


def build_mapping_prompt(tool, framework: dict) -> str:
    """
    Build the prompt sent to the LLM for mapping suggestion.

    *tool* is a ToolInventory instance.
    *framework* is the loaded framework dict.
    """
    tool_lines = [
        f"Tool Name: {tool.name}",
        f"Vendor: {tool.vendor or 'Unknown'}",
        f"Category: {tool.category or 'Unknown'}",
        f"Notes/Description: {tool.notes or 'None provided'}",
    ]
    tool_block = "\n".join(tool_lines)

    activity_lines = []
    for pillar in framework["pillars"]:
        activity_lines.append(f"\n[Pillar: {pillar['name']}]")
        for activity in pillar["activities"]:
            activity_lines.append(
                f"  {activity['id']}: {activity['name']} — {activity.get('description', '')}"
            )
    activities_block = "\n".join(activity_lines)

    total = sum(len(p["activities"]) for p in framework["pillars"])

    return (
        f"Security Tool:\n{tool_block}\n\n"
        f"Framework: {framework['name']} ({total} activities across {len(framework['pillars'])} pillars)\n"
        f"{activities_block}\n\n"
        "Task: For each activity that this tool meaningfully contributes to, provide your "
        "assessment as a JSON array with fields: activity_id, confidence (high/medium/low), "
        "rationale (1-2 sentences explaining how this tool contributes).\n\n"
        "Respond with ONLY the JSON array."
    )


def suggest_mappings(
    tool,
    framework: dict,
    api_key: str,
    model: str,
) -> tuple[list[dict], str | None]:
    """
    Call the Anthropic API and return (suggestions, error_message).

    suggestions is a list of dicts: {activity_id, confidence, rationale}
    error_message is None on success, a string on failure.

    The caller is responsible for persisting the log entry.
    """
    if not api_key:
        return [], "ANTHROPIC_API_KEY not configured — map activities manually."

    prompt = build_mapping_prompt(tool, framework)

    try:
        import anthropic
    except ImportError:
        return [], "anthropic package not installed."

    client = anthropic.Anthropic(api_key=api_key)
    start_ms = int(time.time() * 1000)

    try:
        message = client.messages.create(
            model=model,
            max_tokens=2048,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        logger.warning("Mapping suggestion API call failed for tool %s: %s", tool.id, exc)
        return [], f"API call failed: {exc}"

    elapsed_ms = int(time.time() * 1000) - start_ms
    raw_response = message.content[0].text if message.content else ""

    logger.info(
        "Mapping suggestion for tool %s: model=%s tokens_in=%d tokens_out=%d elapsed=%dms",
        tool.id, message.model, message.usage.input_tokens,
        message.usage.output_tokens, elapsed_ms,
    )

    suggestions = _parse_suggestions(raw_response, framework)
    return suggestions, None, prompt, raw_response, message.model


def _parse_suggestions(raw: str, framework: dict) -> list[dict]:
    """
    Parse the LLM JSON response into a list of suggestion dicts.

    Returns [] if parsing fails or response is malformed.
    Filters out any activity_ids not in the framework.
    """
    valid_ids = {
        activity["id"]
        for pillar in framework["pillars"]
        for activity in pillar["activities"]
    }

    # Strip markdown fences if model added them despite instructions
    text = raw.strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
        if text.endswith("```"):
            text = text[:-3].strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse mapping suggestion JSON: %s — raw: %.200s", exc, raw)
        return []

    if not isinstance(data, list):
        logger.warning("Mapping suggestion response is not a list")
        return []

    results = []
    seen = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        aid = item.get("activity_id", "")
        if aid not in valid_ids or aid in seen:
            continue
        confidence = item.get("confidence", "medium")
        if confidence not in ("high", "medium", "low"):
            confidence = "medium"
        results.append({
            "activity_id": aid,
            "confidence": confidence,
            "rationale": str(item.get("rationale", ""))[:500],
        })
        seen.add(aid)

    return results
