"""AI script director for CutPilot.

Takes ASR transcript sentences, sends them to DeepSeek with a category-aware
prompt template, and parses the JSON response into multiple differentiated
ScriptVersion objects.

Adapted from VideoFactory3 src/script/writer.py.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path

from core.ai_client import create_openai_client
from core.category_detector import detect_category
from core.config import CutPilotConfig
from core.models import ScriptVersion, Sentence
from core.paths import get_prompts_dir

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)
_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _load_prompt_template() -> str:
    """Load the sentence selector prompt template from config/prompts/."""
    prompt_path = get_prompts_dir() / "sentence_selector.md"
    if not prompt_path.exists():
        raise FileNotFoundError(
            f"Prompt template not found at {prompt_path}. "
            "Expected config/prompts/sentence_selector.md"
        )
    return prompt_path.read_text(encoding="utf-8")


def _load_category_preferences(category: str) -> str:
    """Load category-specific content preferences, or empty string."""
    if category == "general":
        return ""
    category_path = get_prompts_dir() / "categories" / f"{category}.md"
    if not category_path.exists():
        logger.warning("No category prompt for '%s', using general", category)
        return ""
    return category_path.read_text(encoding="utf-8")


def _build_numbered_text(sentences: list[Sentence]) -> str:
    """Build numbered subtitle text for the AI prompt input."""
    return "\n".join(f"{s.id}. {s.text}" for s in sentences)


_BROKEN_HASHTAG_QUOTED_RE = re.compile(r'#"([^"]*)"')  # #"tag" → "#tag"
_BROKEN_HASHTAG_BARE_RE = re.compile(r'(?<=[\[,])\s*#([\w\u4e00-\u9fff]+)')  # #tag → "#tag"
_TRAILING_COMMA_RE = re.compile(r",\s*([\]}])")  # trailing comma before ] or }


def _fix_json_quirks(text: str) -> str:
    """Fix common JSON quirks from LLM responses.

    Known issues:
    - ``#"tag"`` instead of ``"#tag"`` in arrays
    - ``#tag`` (bare, no quotes at all) in arrays
    - Trailing commas before ``]`` or ``}``
    - Chinese quotation marks ``\u201c\u201d`` instead of ``""``
    """
    text = text.replace("\u201c", '"').replace("\u201d", '"')  # Chinese quotes
    text = _BROKEN_HASHTAG_QUOTED_RE.sub(r'"#\1"', text)
    text = _BROKEN_HASHTAG_BARE_RE.sub(r' "#\1"', text)
    text = _TRAILING_COMMA_RE.sub(r"\1", text)
    return text


def _repair_json_strings(text: str) -> str:
    """Escape unescaped double quotes inside JSON string values.

    DeepSeek sometimes embeds raw ``"`` inside string values, e.g.:
    ``"why": "小户型用户"客厅小"的痛点"``
    This finds such cases and replaces the inner ``"`` with ``\\"``.
    """
    result: list[str] = []
    i = 0
    n = len(text)

    while i < n:
        ch = text[i]
        if ch == '"':
            # Start of a JSON string — find the true end
            result.append('"')
            i += 1
            while i < n:
                c = text[i]
                if c == '\\':
                    result.append(c)
                    i += 1
                    if i < n:
                        result.append(text[i])
                        i += 1
                    continue
                if c == '"':
                    # Is this the true end of the string?
                    # Look ahead: should be followed by , : ] } or whitespace+one of those
                    rest = text[i + 1:].lstrip()
                    if not rest or rest[0] in ',:]}':
                        result.append('"')
                        i += 1
                        break
                    else:
                        # Unescaped quote inside value — escape it
                        result.append('\\"')
                        i += 1
                        continue
                result.append(c)
                i += 1
        else:
            result.append(ch)
            i += 1

    return "".join(result)


def _extract_json(raw_text: str) -> dict:
    """Parse JSON from raw API text, stripping markdown fences if present.

    Applies common quirk fixes and string repair before parsing.
    """
    fence_match = _JSON_FENCE_RE.search(raw_text)
    text = fence_match.group(1) if fence_match else raw_text
    text = _fix_json_quirks(text.strip())

    # Fast path: try parsing directly
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Slow path: repair unescaped quotes inside string values
    repaired = _repair_json_strings(text)
    return json.loads(repaired)


def _strip_think_tags(text: str) -> str:
    """Remove <think>...</think> blocks from AI response."""
    return _THINK_TAG_RE.sub("", text).strip()


def _call_llm(
    config: CutPilotConfig,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.3,
) -> str:
    """Synchronous OpenAI-compatible call (run via asyncio.to_thread)."""
    client = create_openai_client(config)
    response = client.chat.completions.create(
        model=config.model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
    )
    raw = response.choices[0].message.content or ""
    return _strip_think_tags(raw)


def parse_json_versions(raw_text: str) -> list[ScriptVersion]:
    """Parse JSON response from AI into ScriptVersion objects.

    Expects ``{"versions": [...]}``.  Each version may contain:
    version_id, approach_tag, publish_text, cover_title, cover_subtitle,
    tags, report (mapped to structure), clip_order.

    Raises:
        ValueError: If JSON is malformed or contains no valid versions.
    """
    cleaned = _strip_think_tags(raw_text)

    try:
        parsed = _extract_json(cleaned)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("Failed to parse AI JSON: %s", cleaned[:500])
        raise ValueError(f"AI response is not valid JSON: {exc}") from exc

    raw_versions = parsed.get("versions", [])
    if not raw_versions:
        raise ValueError("AI response JSON has no 'versions' array")

    versions: list[ScriptVersion] = []
    for v in raw_versions:
        clip_order = v.get("clip_order", [])
        if not clip_order:
            logger.warning(
                "Version %s has empty clip_order, skipping",
                v.get("version_id"),
            )
            continue

        sentence_ids = [int(sid) for sid in clip_order]
        tags = v.get("tags", [])
        if not isinstance(tags, list):
            tags = []

        versions.append(
            ScriptVersion(
                version_id=v.get("version_id", len(versions) + 1),
                title=v.get("cover_title", ""),
                structure=v.get("report", ""),
                sentence_ids=sentence_ids,
                approach_tag=v.get("approach_tag", ""),
                publish_text=v.get("publish_text", ""),
                cover_title=v.get("cover_title", ""),
                cover_subtitle=v.get("cover_subtitle", ""),
                tags=tags,
            )
        )

    if not versions:
        raise ValueError("No valid versions found in AI response")
    return versions


def compute_version_duration(
    version: ScriptVersion,
    sentence_map: dict[int, Sentence],
) -> float:
    """Compute estimated duration from sentence timestamps."""
    total = 0.0
    for sid in version.sentence_ids:
        sentence = sentence_map.get(sid)
        if sentence is not None:
            total += sentence.end_sec - sentence.start_sec
    return round(total, 2)


def _enrich_with_duration(
    versions: list[ScriptVersion],
    sentence_map: dict[int, Sentence],
) -> list[ScriptVersion]:
    """Return new ScriptVersion list with estimated_duration filled in."""
    enriched: list[ScriptVersion] = []
    for v in versions:
        duration = compute_version_duration(v, sentence_map)
        enriched.append(
            ScriptVersion(
                version_id=v.version_id,
                title=v.title,
                structure=v.structure,
                sentence_ids=v.sentence_ids,
                reason=v.reason,
                estimated_duration=duration,
                score=v.score,
                approach_tag=v.approach_tag,
                publish_text=v.publish_text,
                cover_title=v.cover_title,
                cover_subtitle=v.cover_subtitle,
                tags=v.tags,
            )
        )
    return enriched


async def generate_versions(
    sentences: list[Sentence],
    config: CutPilotConfig,
    version_count: int = 3,
) -> list[ScriptVersion]:
    """Generate multiple differentiated video script versions from transcript.

    Workflow:
    1. Auto-detect product category from transcript text
    2. Load category-specific prompt preferences
    3. Build system + user prompts
    4. Call DeepSeek API via asyncio.to_thread
    5. Parse JSON response into ScriptVersion objects
    6. Compute estimated_duration for each version

    Args:
        sentences: ASR transcript sentences with timing.
        config: CutPilot configuration (model, API key, etc.).
        version_count: Number of script versions to request.

    Returns:
        List of ScriptVersion objects with all fields populated.

    Raises:
        FileNotFoundError: If prompt template is missing.
        ValueError: If AI response cannot be parsed.
    """
    transcript_text = " ".join(s.text for s in sentences)
    category = detect_category(transcript_text)
    logger.info("Detected category: %s", category)

    prompt_template = _load_prompt_template()
    content_preferences = _load_category_preferences(category)

    system_prompt = prompt_template.replace(
        "{content_preferences}",
        content_preferences or "",
    )

    numbered_text = _build_numbered_text(sentences)
    user_prompt = (
        f"以下是原始口播内容（共{len(sentences)}句），"
        f"请生成{version_count}个爆款短视频脚本版本。\n\n"
        f"{numbered_text}"
    )

    raw_text = await asyncio.to_thread(
        _call_llm, config, system_prompt, user_prompt
    )

    logger.info("AI raw response (first 2000 chars): %s", raw_text[:2000])

    versions = parse_json_versions(raw_text)

    sentence_map = {s.id: s for s in sentences}
    enriched = _enrich_with_duration(versions, sentence_map)

    logger.info(
        "Generated %d versions with %s sentences each",
        len(enriched),
        [len(v.sentence_ids) for v in enriched],
    )
    return enriched
