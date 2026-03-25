"""Script version inspector for CutPilot.

Reviews AI-generated script versions for:
1. Prohibited / sensitive word scanning
2. Pairwise overlap detection (dedup)
3. AI quality scoring
4. Approval decision with fallback

Adapted from VideoFactory3 reviewer.py — simplified to return
only approved ScriptVersion objects instead of a ReviewReport.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path

from core.ai_client import call_ai
from core.config import CutPilotConfig
from core.models import ScriptVersion, Sentence
from core.paths import get_config_dir, get_prompts_dir

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)

# Thresholds
MIN_SCORE_APPROVED = 50.0
OVERLAP_REJECT_THRESHOLD = 0.50


# -- Prohibited / sensitive word checking ------------------------------------


def load_sensitive_words(
    path: Path | None = None,
) -> dict[str, list[str]]:
    """Load sensitive word lists from JSON config file.

    Returns dict with keys: prohibited, sensitive, platform_risk.
    Falls back to empty lists if file is missing.
    """
    if path is None:
        path = get_config_dir() / "sensitive_words.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            logger.warning("sensitive_words.json is not a dict, using empty")
            return {"prohibited": [], "sensitive": [], "platform_risk": []}
        return data
    logger.warning("Sensitive words file not found: %s", path)
    return {"prohibited": [], "sensitive": [], "platform_risk": []}


def check_prohibited_words(
    text: str,
    word_lists: dict[str, list[str]],
) -> tuple[list[str], list[str]]:
    """Scan text for prohibited and sensitive words.

    Returns:
        (prohibited_found, sensitive_found) — two separate hit lists.
    """
    prohibited = [w for w in word_lists.get("prohibited", []) if w in text]
    sensitive = [w for w in word_lists.get("sensitive", []) if w in text]
    sensitive += [w for w in word_lists.get("platform_risk", []) if w in text]
    return prohibited, sensitive


# -- Overlap calculation -----------------------------------------------------


def compute_overlap_ratio(ids_a: list[int], ids_b: list[int]) -> float:
    """Compute overlap ratio between two sentence ID lists.

    Uses intersection / min(len_a, len_b) to detect subset relationships.
    """
    set_a, set_b = set(ids_a), set(ids_b)
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / min(len(set_a), len(set_b))


def compute_overlap_matrix(
    versions: list[ScriptVersion],
) -> dict[tuple[int, int], float]:
    """Compute pairwise overlap ratios for all version pairs.

    Returns dict mapping (version_id_a, version_id_b) -> ratio.
    """
    matrix: dict[tuple[int, int], float] = {}
    for i, va in enumerate(versions):
        for vb in versions[i + 1 :]:
            ratio = compute_overlap_ratio(va.sentence_ids, vb.sentence_ids)
            matrix[(va.version_id, vb.version_id)] = ratio
    return matrix


def detect_overlap_groups(
    versions: list[ScriptVersion],
    threshold: float = OVERLAP_REJECT_THRESHOLD,
) -> dict[int, int]:
    """Group versions by high overlap using union-find style grouping.

    Returns dict mapping version_id -> group_number.
    Only versions with overlap >= threshold appear in the result.
    """
    matrix = compute_overlap_matrix(versions)
    groups: dict[int, int] = {}
    next_group = 1

    for (va_id, vb_id), ratio in matrix.items():
        if ratio < threshold:
            continue
        if va_id in groups:
            groups[vb_id] = groups[va_id]
        elif vb_id in groups:
            groups[va_id] = groups[vb_id]
        else:
            groups[va_id] = next_group
            groups[vb_id] = next_group
            next_group += 1

    return groups


# -- Hook text extraction ----------------------------------------------------


def extract_core_hook_text(
    version: ScriptVersion,
    sentence_map: dict[int, Sentence],
    max_seconds: float = 5.0,
) -> str:
    """Extract subtitle text from the first N seconds of a version.

    Walks sentence_ids in order, stopping when cumulative span
    from first sentence exceeds max_seconds.
    """
    texts: list[str] = []
    first_start: float | None = None

    for sid in version.sentence_ids:
        sentence = sentence_map.get(sid)
        if sentence is None:
            continue
        if first_start is None:
            first_start = sentence.start_sec
        if sentence.start_sec - first_start >= max_seconds:
            break
        texts.append(sentence.text)

    return "".join(texts)


# -- AI review prompt -------------------------------------------------------


def _load_system_prompt(path: Path | None = None) -> str:
    """Load inspector system prompt from markdown file."""
    if path is None:
        path = get_prompts_dir() / "inspector.md"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    logger.warning("Inspector prompt not found: %s", path)
    return "你是短视频脚本质量审核专家。请审核脚本版本并返回JSON评分。"


def _build_review_prompt(
    versions: list[ScriptVersion],
    sentence_map: dict[int, Sentence],
    overlap_matrix: dict[tuple[int, int], float],
) -> str:
    """Build user prompt with version texts and overlap hints."""
    blocks: list[str] = []
    for v in versions:
        lines = [f"版本{v.version_id}（{v.title}）："]
        for sid in v.sentence_ids:
            sentence = sentence_map.get(sid)
            text = sentence.text if sentence else f"[缺失句子{sid}]"
            lines.append(f"  [{sid}] {text}")
        blocks.append("\n".join(lines))

    prompt = "请审核以下脚本版本：\n\n" + "\n\n".join(blocks)

    if overlap_matrix:
        overlap_lines = ["\n\n## 句子重叠率参考（本地预计算）"]
        for (va_id, vb_id), ratio in sorted(overlap_matrix.items()):
            pct = round(ratio * 100, 1)
            overlap_lines.append(f"- 版本{va_id} vs 版本{vb_id}: {pct}%")
        prompt += "\n".join(overlap_lines)

    return prompt


# -- AI response parsing ----------------------------------------------------


def _parse_ai_reviews(raw_text: str) -> dict:
    """Parse AI review JSON response with fallback on failure.

    Handles markdown fences and <think> tags.
    """
    cleaned = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL)
    cleaned = cleaned.strip()

    fence_match = _JSON_FENCE_RE.search(cleaned)
    text = fence_match.group(1) if fence_match else cleaned

    try:
        parsed = json.loads(text.strip())
        if isinstance(parsed, dict):
            return parsed
        return {"reviews": parsed}
    except (json.JSONDecodeError, TypeError):
        logger.warning(
            "Failed to parse AI review response: %.500s", raw_text,
        )
        return {"reviews": []}


def _compute_weighted_score(dims: dict) -> float:
    """Compute weighted average from dimension scores.

    differentiation gets 1.5x weight.
    """
    total = (
        float(dims.get("hook_strength", 60))
        + float(dims.get("coherence", 60))
        + float(dims.get("structure", 60))
        + float(dims.get("differentiation", 60)) * 1.5
        + float(dims.get("commercial_value", 60))
    )
    return round(total / 5.5, 1)


# -- Decision helpers --------------------------------------------------------


def _decide_version(
    *,
    ai_decision: str,
    score: float,
    prohibited: list[str],
) -> str:
    """Determine approval decision from multiple signals."""
    if prohibited:
        return "rejected"
    if score < MIN_SCORE_APPROVED:
        return "rejected"
    if ai_decision == "rejected":
        return "rejected"
    return "approved"


def _dedup_within_groups(
    decisions: dict[int, str],
    scores: dict[int, float],
    overlap_groups: dict[int, int],
) -> dict[int, str]:
    """Within each overlap group, reject all but the highest scorer.

    Returns a new decisions dict (does not mutate the original).
    """
    group_best: dict[int, tuple[int, float]] = {}
    for vid, group in overlap_groups.items():
        s = scores.get(vid, 0.0)
        if group not in group_best or s > group_best[group][1]:
            group_best[group] = (vid, s)

    updated = dict(decisions)
    for vid, group in overlap_groups.items():
        if updated.get(vid) != "approved":
            continue
        best_vid, _ = group_best[group]
        if vid != best_vid:
            updated[vid] = "rejected"
            logger.info(
                "Dedup: version %d rejected (group %d, keeping %d)",
                vid, group, best_vid,
            )
    return updated


# -- Main entry point --------------------------------------------------------


async def review_versions(
    versions: list[ScriptVersion],
    sentences: list[Sentence],
    config: CutPilotConfig | None = None,
) -> list[ScriptVersion]:
    """Review versions and return only approved ones.

    Steps:
        1. Local: prohibited word scan per version
        2. Local: pairwise overlap detection
        3. AI: quality scoring via inspector prompt
        4. Decision: reject if prohibited words, low score, or AI rejected
        5. Dedup: within overlap groups keep only highest scorer
        6. Fallback: if all rejected, force-approve the best one
        7. Return approved ScriptVersion objects with updated scores

    Args:
        versions: Script versions to review.
        sentences: Full sentence list for text lookup.
        config: CutPilot configuration (auto-loaded if None).

    Returns:
        List of approved ScriptVersion objects.
    """
    if not versions:
        return []

    if config is None:
        config = CutPilotConfig()

    sentence_map = {s.id: s for s in sentences}
    word_lists = load_sensitive_words()

    # Step 1: Prohibited word scan
    prohibited_by_id: dict[int, list[str]] = {}
    for v in versions:
        full_text = " ".join(
            sentence_map[sid].text
            for sid in v.sentence_ids
            if sid in sentence_map
        )
        prohibited, _sensitive = check_prohibited_words(full_text, word_lists)
        prohibited_by_id[v.version_id] = prohibited

    # Step 2: Overlap detection
    overlap_matrix = compute_overlap_matrix(versions)
    overlap_groups = detect_overlap_groups(versions)

    # Step 3: AI quality scoring
    system_prompt = _load_system_prompt()
    review_prompt = _build_review_prompt(versions, sentence_map, overlap_matrix)
    raw_text = await asyncio.to_thread(
        call_ai, review_prompt, system_prompt, config, 0.1,
    )

    ai_reviews = _parse_ai_reviews(raw_text)
    ai_by_id: dict[int, dict] = {
        r["version_id"]: r
        for r in ai_reviews.get("reviews", [])
        if isinstance(r, dict) and "version_id" in r
    }

    # Step 4: Build decisions and scores
    scores: dict[int, float] = {}
    decisions: dict[int, str] = {}

    for v in versions:
        ai_review = ai_by_id.get(v.version_id, {})
        dims = ai_review.get("dimensions", {})
        score = float(ai_review.get("score", _compute_weighted_score(dims)))
        scores[v.version_id] = score

        decisions[v.version_id] = _decide_version(
            ai_decision=ai_review.get("decision", ""),
            score=score,
            prohibited=prohibited_by_id.get(v.version_id, []),
        )

    # Step 5: Dedup within overlap groups
    decisions = _dedup_within_groups(decisions, scores, overlap_groups)

    # Step 6: Fallback — if all rejected, force-approve the best
    if not any(d == "approved" for d in decisions.values()):
        best_vid = max(scores, key=scores.get)  # type: ignore[arg-type]
        decisions[best_vid] = "approved"
        logger.warning(
            "All versions rejected — fallback: force-approving version %d "
            "(score %.1f)",
            best_vid, scores[best_vid],
        )

    # Step 7: Return approved versions with updated scores
    approved: list[ScriptVersion] = []
    for v in versions:
        if decisions.get(v.version_id) != "approved":
            continue
        updated = v.model_copy(update={"score": scores[v.version_id]})
        approved.append(updated)

    logger.info(
        "Inspector: %d/%d versions approved", len(approved), len(versions),
    )
    return approved
