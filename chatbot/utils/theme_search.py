"""Resolve cached theme names deterministically, independently of AI filters."""
import re

from rapidfuzz import fuzz, process

from chatbot.utils.search_filter_resolver import (
    _confidence_threshold, _is_negated,
)
from chatbot.utils.theme_cache import get_theme_list


def resolve_theme_names(query):
    """Return included names, excluded names, and unclaimed search text.

    Match whole names against token windows: partial word matches must not
    turn a generic topic like "learning" into "Foundational Learning".
    Cached codes are never supplied to RapidFuzz.
    Only primary themes are searchable, matching the media assignment filter.
    """
    names = list(dict.fromkeys(
        theme['name'] for theme in get_theme_list(primary_only=True)['result']
        if theme.get('name')
    ))
    if not names:
        return [], [], query
    normalized = [' '.join(re.findall(r'\w+', name.casefold())) for name in names]
    tokens = list(re.finditer(r'\w+', query))
    max_words = max(len(name.split()) for name in normalized) + 1
    threshold = _confidence_threshold('theme')
    candidates = []
    for start in range(len(tokens)):
        for size in range(1, min(max_words, len(tokens) - start) + 1):
            window = tokens[start:start + size]
            text = ' '.join(token.group().casefold() for token in window)
            match = process.extractOne(text, normalized, scorer=fuzz.ratio,
                                       score_cutoff=threshold)
            if match is not None:
                _, score, index = match
                candidates.append((score, window[0].start(), window[-1].end(), names[index]))

    # Prefer the closest complete name; do not claim overlapping query spans.
    candidates.sort(key=lambda item: (-item[0], -(item[2] - item[1]), item[1]))
    accepted = []
    for score, start, end, name in candidates:
        if not any(start < other_end and end > other_start
                   for other_start, other_end, _, _ in accepted):
            accepted.append((start, end, name, _is_negated(query.lower(), start)))
    accepted.sort()
    included, excluded = [], []
    for start, end, name, negated in accepted:
        target = excluded if negated else included
        if name not in target:
            target.append(name)
    included = [name for name in included if name not in excluded]
    remaining = query
    for start, end, _, _ in reversed(accepted):
        remaining = remaining[:start] + ' ' + remaining[end:]
    return included, excluded, re.sub(r'\s+', ' ', remaining).strip() if accepted else query
