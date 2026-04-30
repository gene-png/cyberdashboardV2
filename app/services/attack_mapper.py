"""
MITRE ATT&CK tool-to-technique mapping service.

For each tool with active mappings, calls the Anthropic API to suggest which
ATT&CK techniques the tool covers and in what capacity (detect/prevent/respond).

Caching: results are stored in attack_coverage_run by (tool_id, fingerprint).
If the fingerprint matches an existing run, the cached result is returned
without an API call.
"""
import hashlib
import json
import logging
import time

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a cybersecurity expert mapping security tools to MITRE ATT&CK Enterprise techniques. "
    "For each technique the tool meaningfully covers, specify the coverage_type: "
    "'detect' (the tool detects or alerts on this technique), "
    "'prevent' (the tool actively blocks or prevents it), or "
    "'respond' (the tool supports incident response for this technique). "
    "Respond ONLY with a valid JSON array — no markdown fences, no preamble. "
    "Each element must have exactly these keys: technique_id, coverage_type, confidence, rationale. "
    "confidence must be: high, medium, or low. rationale must be 1-2 sentences. "
    "Only include techniques where the tool has a meaningful, direct contribution."
)


def get_tool_fingerprint(tool, activity_ids: list[str]) -> str:
    """
    Stable hash of tool metadata + activity IDs.
    Used to detect whether the tool's coverage context has changed since the last run.
    """
    parts = [
        tool.name or "",
        tool.vendor or "",
        tool.category or "",
        tool.notes or "",
        *sorted(activity_ids),
    ]
    content = "|".join(parts)
    return hashlib.sha256(content.encode()).hexdigest()[:32]


def build_attack_mapping_prompt(tool, activity_ids: list[str], techniques) -> str:
    """
    Build the LLM prompt for technique mapping.

    techniques: list of MitreTechnique objects
    """
    tool_lines = [
        f"Tool Name: {tool.name}",
        f"Vendor: {tool.vendor or 'Unknown'}",
        f"Category: {tool.category or 'Unknown'}",
        f"Description/Notes: {tool.notes or 'None provided'}",
        f"Zero Trust Framework Activities Covered: {', '.join(activity_ids) if activity_ids else 'None specified'}",
    ]
    tool_block = "\n".join(tool_lines)

    # Group techniques by tactic for readability
    by_tactic: dict[str, list] = {}
    for t in techniques:
        tactic = (t.tactic or "Unknown").split(",")[0].strip()
        by_tactic.setdefault(tactic, []).append(t)

    technique_lines = []
    for tactic in sorted(by_tactic.keys()):
        technique_lines.append(f"\n[{tactic}]")
        for t in sorted(by_tactic[tactic], key=lambda x: x.full_id):
            technique_lines.append(f"  {t.full_id}: {t.name}")

    techniques_block = "\n".join(technique_lines)

    return (
        f"Security Tool:\n{tool_block}\n\n"
        f"MITRE ATT&CK Enterprise Techniques ({len(techniques)} total):\n"
        f"{techniques_block}\n\n"
        "Task: For each ATT&CK technique this tool meaningfully contributes to, "
        "provide your assessment as a JSON array with: technique_id, coverage_type "
        "(detect/prevent/respond), confidence (high/medium/low), rationale (1-2 sentences).\n\n"
        "Respond with ONLY the JSON array."
    )


def _parse_results(raw: str, valid_ids: set[str]) -> list[dict]:
    """Parse and validate the LLM JSON response."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3].strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse ATT&CK mapping JSON: %s — raw: %.200s", exc, raw)
        return []

    if not isinstance(data, list):
        return []

    results = []
    seen = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        tid = item.get("technique_id", "")
        if tid not in valid_ids or tid in seen:
            continue
        coverage_type = item.get("coverage_type", "detect")
        if coverage_type not in ("detect", "prevent", "respond"):
            coverage_type = "detect"
        confidence = item.get("confidence", "medium")
        if confidence not in ("high", "medium", "low"):
            confidence = "medium"
        results.append({
            "technique_id": tid,
            "coverage_type": coverage_type,
            "confidence": confidence,
            "rationale": str(item.get("rationale", ""))[:500],
        })
        seen.add(tid)

    return results


def map_tool_to_techniques(
    tool,
    activity_ids: list[str],
    techniques: list,
    api_key: str,
    model: str,
    cached_run=None,
) -> tuple[list[dict], str | None]:
    """
    Return (results, error_message) for the given tool.

    If cached_run is provided and its fingerprint matches, returns cached results
    without an API call.

    results: list of {technique_id, coverage_type, confidence, rationale}
    error_message: None on success, string on failure
    """
    fingerprint = get_tool_fingerprint(tool, activity_ids)

    # Use cache if fingerprint matches
    if cached_run and cached_run.tool_fingerprint == fingerprint:
        try:
            results = json.loads(cached_run.response_payload)
            if isinstance(results, list):
                logger.info("Cache hit for tool %s (fingerprint %s)", tool.id, fingerprint[:8])
                return results, None
        except json.JSONDecodeError:
            pass  # Fall through to API call

    if not api_key:
        return [], "ANTHROPIC_API_KEY not configured — set it in .env to generate coverage reports."

    try:
        import anthropic
    except ImportError:
        return [], "anthropic package not installed."

    valid_ids = {t.full_id for t in techniques}
    prompt = build_attack_mapping_prompt(tool, activity_ids, techniques)
    client = anthropic.Anthropic(api_key=api_key)
    start_ms = int(time.time() * 1000)

    try:
        message = client.messages.create(
            model=model,
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        logger.warning("ATT&CK mapping API call failed for tool %s: %s", tool.id, exc)
        return [], f"API call failed: {exc}"

    elapsed_ms = int(time.time() * 1000) - start_ms
    raw = message.content[0].text if message.content else ""

    logger.info(
        "ATT&CK mapping for tool %s: model=%s tokens_in=%d tokens_out=%d elapsed=%dms",
        tool.id, message.model,
        message.usage.input_tokens, message.usage.output_tokens, elapsed_ms,
    )

    results = _parse_results(raw, valid_ids)
    return results, None


def classify_gap_status(detect_tools: list[str], prevent_tools: list[str], respond_tools: list[str]) -> str:
    """
    Classify a technique's coverage gap status.

    Full        — has both detect AND prevent coverage
    Detect Only — has detect coverage but no prevent
    Prevent Only — has prevent coverage but no detect
    Single Tool  — covered by exactly 1 unique tool (any coverage type)
    None         — no coverage at all
    """
    all_tools = set(detect_tools) | set(prevent_tools) | set(respond_tools)
    has_detect = len(detect_tools) > 0
    has_prevent = len(prevent_tools) > 0

    if not all_tools:
        return "None"
    if has_detect and has_prevent:
        return "Full"
    if len(all_tools) == 1:
        return "Single Tool"
    if has_detect:
        return "Detect Only"
    if has_prevent:
        return "Prevent Only"
    return "Single Tool"  # respond-only with multiple tools = still single-type coverage
