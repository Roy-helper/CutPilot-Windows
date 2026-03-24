"""Product category auto-detection from transcript text.

Uses keyword matching against the full transcript to determine the
product category, which drives category-specific prompt selection.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Category keyword definitions: category_name -> list of Chinese keywords
_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "wig": ["假发", "发片", "头套", "秃头", "发量", "发际线"],
    "makeup": ["口红", "唇膏", "唇釉", "化妆", "粉底", "眼影", "腮红", "遮瑕"],
    "skincare": ["面膜", "精华", "水乳", "护肤", "保湿", "补水", "防晒"],
    "clothing": ["衣服", "裙子", "裤子", "外套", "穿搭", "显瘦"],
}


def detect_category(transcript_text: str) -> str:
    """Detect product category from transcript text via keyword matching.

    Counts keyword hits per category and returns the category with the
    most matches. Returns "general" if no keywords match.

    Args:
        transcript_text: Full transcript text (concatenated sentences).

    Returns:
        Category name: "wig", "makeup", "skincare", "clothing", or "general".
    """
    if not transcript_text:
        return "general"

    hit_counts: dict[str, int] = {}
    for category, keywords in _CATEGORY_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in transcript_text)
        if count > 0:
            hit_counts[category] = count

    if not hit_counts:
        logger.info("No category keywords matched, using 'general'")
        return "general"

    best_category = max(hit_counts, key=lambda k: hit_counts[k])
    logger.info(
        "Detected category '%s' with %d keyword hits (all hits: %s)",
        best_category,
        hit_counts[best_category],
        hit_counts,
    )
    return best_category
