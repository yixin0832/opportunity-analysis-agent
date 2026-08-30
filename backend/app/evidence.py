from __future__ import annotations

import re

from .schemas import Evidence, EvidenceCandidate


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    chars: list[str] = []
    index_map: list[int] = []
    for idx, char in enumerate(text):
        if char.isspace():
            continue
        chars.append(char)
        index_map.append(idx)
    return "".join(chars), index_map


def locate_quote(original_text: str, quote: str) -> tuple[int | None, int | None]:
    if not quote:
        return None, None

    exact_start = original_text.find(quote)
    if exact_start >= 0:
        return exact_start, exact_start + len(quote)

    normalized_text, index_map = _normalize_with_map(original_text)
    normalized_quote, _ = _normalize_with_map(quote)
    if not normalized_quote:
        return None, None

    normalized_start = normalized_text.find(normalized_quote)
    if normalized_start < 0:
        return None, None

    original_start = index_map[normalized_start]
    original_end = index_map[normalized_start + len(normalized_quote) - 1] + 1
    return original_start, original_end


def validate_evidence(original_text: str, candidates: list[EvidenceCandidate]) -> list[Evidence]:
    seen: set[str] = set()
    evidence: list[Evidence] = []
    for candidate in candidates:
        if candidate.id in seen:
            continue
        seen.add(candidate.id)
        if candidate.start_char is not None and original_text[candidate.start_char : candidate.start_char + len(candidate.quote)] == candidate.quote:
            start = candidate.start_char
            end = candidate.end_char if candidate.end_char is not None else candidate.start_char + len(candidate.quote)
        else:
            start, end = locate_quote(original_text, candidate.quote)
        evidence.append(
            Evidence(
                id=candidate.id,
                quote=candidate.quote,
                start_char=start,
                end_char=end,
                field=candidate.field,
                valid=start is not None and end is not None,
            )
        )
    return evidence


def summarize_input(text: str, max_len: int = 80) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1] + "…"
