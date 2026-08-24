import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple, Union

from rapidfuzz import fuzz, process

OrgEntry = Tuple[str, str, List[str]]
SimpleEntry = Tuple[str, List[str]]


@dataclass(frozen=True)
class MatchResult:
    display_value: str
    slug: Optional[str]
    method: str
    score: int
    confidence: str
    matched_span: str
    negated: bool = False
    alternates: List[str] = field(default_factory=list)


@dataclass
class ResolvedFilters:
    organization: List[MatchResult] = field(default_factory=list)
    theme: List[MatchResult] = field(default_factory=list)
    resource_type: List[MatchResult] = field(default_factory=list)
    file_type: List[MatchResult] = field(default_factory=list)
    search_text: str = ""


class CategoryMatcher:
    def __init__(
        self,
        entries: Union[List[OrgEntry], List[SimpleEntry]],
        has_slug: bool = True,
        auto_alias: bool = False,
        auto_alias_leading_word: bool = True,
    ):
        self._lookup = {}  # type: Dict[str, Tuple[str, str]]
        self._all_names = []  # type: List[str]

        for entry in entries:
            if has_slug:
                display_name, slug, aliases = entry
            else:
                display_name, aliases = entry
                slug = display_name

            all_aliases = list(aliases)
            if auto_alias:
                for auto in derive_auto_aliases(display_name, include_leading_word=auto_alias_leading_word):
                    if auto.lower() not in {alias.lower() for alias in all_aliases} and auto.lower() != display_name.lower():
                        all_aliases.append(auto)

            for name in (display_name,) + tuple(all_aliases):
                for variant in _name_variants(name):
                    key = variant.strip().lower()
                    if not key:
                        continue
                    self._lookup[key] = (display_name, slug)
                    self._all_names.append(variant)

        self._all_names.sort(key=len, reverse=True)
        self._fuzzy_names = [name for name in self._all_names if len(name) >= _min_fuzzy_length()]
        self._compiled_patterns = [
            (_compile_gazetteer_pattern(name), name)
            for name in self._all_names
        ]

    def find_all_exact(self, query: str) -> List[MatchResult]:
        if not query or not query.strip():
            return []
        return self._gazetteer_match_all(query)

    def find_fuzzy(self, query: str, score_threshold: int) -> Optional[MatchResult]:
        matches = self.find_all_fuzzy(query, score_threshold)
        return matches[0] if matches else None

    def find_all_fuzzy(
        self,
        query: str,
        score_threshold: int,
        exclude_display_values: Optional[Iterable[str]] = None,
    ) -> List[MatchResult]:
        if not query or not query.strip() or not self._fuzzy_names:
            return []

        excluded = set(exclude_display_values or [])
        candidates = [
            candidate
            for candidate in self._generate_candidates(query)
            if len(candidate) >= _min_fuzzy_length()
        ]
        if not candidates:
            return []

        best_by_display = {}
        scored = []
        for candidate in candidates:
            result = process.extractOne(
                candidate,
                self._fuzzy_names,
                scorer=fuzz.WRatio,
            )
            if result is None:
                continue

            matched_name, score, _ = result
            display_value, slug = self._lookup[matched_name.lower()]
            if display_value in excluded:
                continue

            candidate_tokens = len(candidate.split())
            matched_tokens = len(matched_name.split())
            if matched_tokens >= 2 and candidate_tokens < matched_tokens and score < score_threshold:
                continue

            scored.append((matched_name, int(score)))
            current = best_by_display.get(display_value)
            if (
                current is None
                or score > current[2] + _ambiguity_delta()
                or (
                    score >= current[2] - _ambiguity_delta()
                    and len(candidate) > len(current[0])
                )
            ):
                best_by_display[display_value] = (candidate, matched_name, int(score), slug)

        matches = []
        for display_value, (candidate, matched_name, score, slug) in best_by_display.items():
            if score < score_threshold:
                continue

            alternates = self._fuzzy_alternates(scored, matched_name, score, display_value)
            span_start = query.lower().find(candidate.lower())
            matches.append(MatchResult(
                display_value=display_value,
                slug=slug,
                method="fuzzy",
                score=score,
                confidence="high",
                matched_span=candidate,
                negated=_is_negated(query.lower(), span_start) if span_start != -1 else False,
                alternates=alternates,
            ))

        matches.sort(key=lambda match: query.lower().find(match.matched_span.lower()))
        return matches

    def _generate_candidates(self, query: str) -> List[str]:
        candidates = set()
        query = _strip_noise_phrases(query)
        tokens = re.findall(r"[A-Za-z0-9']+", query)
        lowered_tokens = [token.lower() for token in tokens]
        lowered_query = query.lower()
        candidate_stopwords = _candidate_stopwords()

        for trigger in _trigger_words():
            idx = lowered_query.find(" " + trigger + " ")
            if idx != -1:
                tail = _clean_fuzzy_candidate(query[idx + len(trigger) + 2:].strip(" ?.!,"))
                if tail:
                    candidates.add(tail)

        token_count = len(tokens)
        for size in range(1, 5):
            for start in range(0, token_count - size + 1):
                window = tokens[start:start + size]
                window_lower = lowered_tokens[start:start + size]
                if all(word in candidate_stopwords for word in window_lower):
                    continue
                candidate = _clean_fuzzy_candidate(" ".join(window))
                if candidate:
                    candidates.add(candidate)

        candidates.discard("")
        return list(candidates)

    def _fuzzy_alternates(
        self,
        scored: List[Tuple[str, int]],
        matched_name: str,
        score: int,
        display_value: str,
    ) -> List[str]:
        alt_names = sorted(
            {
                name
                for name, candidate_score in scored
                if name != matched_name and candidate_score >= score - _ambiguity_delta()
            },
            key=lambda name: -next(candidate_score for scored_name, candidate_score in scored if scored_name == name),
        )
        alternates = []
        seen = set()
        for name in alt_names:
            alternate_display = self._lookup[name.lower()][0]
            if alternate_display == display_value or alternate_display in seen:
                continue
            alternates.append(alternate_display)
            seen.add(alternate_display)
        return alternates

    def _gazetteer_match_all(self, query: str) -> List[MatchResult]:
        lowered = query.lower()
        claimed_spans = []  # type: List[Tuple[int, int]]
        found_display_values = set()
        hits = []  # type: List[Tuple[int, MatchResult]]

        for pattern, name in self._compiled_patterns:
            for match in pattern.finditer(lowered):
                start, end = match.start(), match.end()
                if any(not (end <= claimed_start or start >= claimed_end) for claimed_start, claimed_end in claimed_spans):
                    continue

                display_value, slug = self._lookup[name.lower()]
                if display_value in found_display_values:
                    continue

                hits.append((start, MatchResult(
                    display_value=display_value,
                    slug=slug,
                    method="gazetteer_exact",
                    score=100,
                    confidence="high",
                    matched_span=query[start:end],
                    negated=_is_negated(lowered, start),
                )))
                claimed_spans.append((start, end))
                found_display_values.add(display_value)

        hits.sort(key=lambda hit: hit[0])
        return [result for _, result in hits]


def resolve_query_exact(query: str) -> ResolvedFilters:
    remaining = query or ""
    results = {
        "organization": [],
        "theme": [],
        "resource_type": [],
        "file_type": [],
    }  # type: Dict[str, List[MatchResult]]
    matchers = _build_matchers()

    for field_name in ("organization", "file_type"):
        matcher = matchers[field_name]
        matches = matcher.find_all_exact(remaining)
        results[field_name] = matches
        if matches:
            remaining = _strip_all(remaining, matches)

    org_threshold = _organization_confidence_threshold()
    org_matches = results.get("organization", [])
    org_score = max((match.score for match in org_matches), default=0)
    if org_score < org_threshold:
        fuzzy_matches = matchers["organization"].find_all_fuzzy(remaining, org_threshold)
        if fuzzy_matches:
            results["organization"] = fuzzy_matches
            remaining = _strip_all(remaining, fuzzy_matches)
    else:
        fuzzy_matches = matchers["organization"].find_all_fuzzy(
            remaining,
            org_threshold,
            exclude_display_values=[match.display_value for match in org_matches],
        )
        if fuzzy_matches:
            results["organization"].extend(fuzzy_matches)
            remaining = _strip_all(remaining, fuzzy_matches)

    return ResolvedFilters(
        organization=results["organization"],
        theme=results["theme"],
        resource_type=results["resource_type"],
        file_type=results["file_type"],
        search_text=clean_search_text(remaining),
    )


def included_values(matches: Iterable[MatchResult], use_slug: bool = False) -> List[str]:
    values = []
    for match in matches:
        if match.negated:
            continue
        values.append(match.slug if use_slug and match.slug else match.display_value)
    return list(dict.fromkeys(values))


def build_qdrant_filter(resolved: ResolvedFilters, min_confidence: str = "low") -> Dict[str, List[Dict]]:
    field_mapping = {
        "organization": ("metadata.company", True),
        "theme": ("tag", False),
        "resource_type": ("metadata.DOCUMENT_TYPE", False),
        "file_type": ("metadata.type", True),
    }
    confidence_order = {"low": 0, "medium": 1, "high": 2}
    min_rank = confidence_order.get(min_confidence, 0)

    qdrant_filter = {"must": [], "must_not": []}
    for field_name, (payload_key, use_slug) in field_mapping.items():
        matches = getattr(resolved, field_name)
        included = []
        excluded = []

        for match in matches:
            if confidence_order.get(match.confidence, 0) < min_rank:
                continue

            value = match.slug if use_slug and match.slug else match.display_value
            if match.negated:
                excluded.append(value)
            else:
                included.append(value)

        _append_qdrant_match(qdrant_filter["must"], payload_key, included)
        _append_qdrant_match(qdrant_filter["must_not"], payload_key, excluded)

    return {key: value for key, value in qdrant_filter.items() if value}


def to_response_dict(query: str, resolved: ResolvedFilters) -> Dict:
    qdrant_filter = build_qdrant_filter(resolved)
    return {
        "query": query,
        "resolved": {
            "organization": [_match_to_dict(match) for match in resolved.organization],
            "theme": [_match_to_dict(match) for match in resolved.theme],
            "resource_type": [_match_to_dict(match) for match in resolved.resource_type],
            "file_type": [_match_to_dict(match) for match in resolved.file_type],
        },
        "search_text": resolved.search_text,
        "qdrant_filter": qdrant_filter,
    }


def clean_search_text(text: str) -> str:
    if not text or not text.strip():
        return ""

    working = text.lower()
    for phrase in _noise_phrases():
        working = working.replace(phrase, " ")
    for phrase in _negation_words():
        if " " in phrase:
            working = working.replace(phrase, " ")

    words = working.split()
    removable_words = _noise_words() | _negation_words()
    return " ".join(word for word in words if word not in removable_words).strip()


def derive_auto_aliases(display_name: str, include_leading_word: bool = True) -> List[str]:
    spaced_compound = _split_alnum_boundaries(display_name)
    words = [word for word in re.findall(r"[A-Za-z0-9]+", spaced_compound)]
    if not words:
        return []

    aliases = []
    if spaced_compound.lower() != display_name.lower():
        aliases.append(spaced_compound)

    acronym_words = [word for word in words if word.lower() not in _acronym_stopwords()]
    if len(acronym_words) >= 2:
        aliases.append("".join(word[0] for word in acronym_words).upper())

    aliases.extend(_derive_suffix_trimmed_aliases(words))

    if (
        include_leading_word
        and len(words) >= 2
        and words[0].lower() not in _auto_alias_excluded_words()
        and len(words[0]) >= _min_fuzzy_length()
    ):
        aliases.append(words[0])

    return aliases


def _derive_suffix_trimmed_aliases(words: List[str]) -> List[str]:
    aliases = []
    trimmed_words = list(words)
    while len(trimmed_words) > 1 and trimmed_words[-1].lower() in _generic_leading_words():
        trimmed_words = trimmed_words[:-1]
        alias = " ".join(trimmed_words)
        if (
            alias
            and alias.lower() not in _auto_alias_excluded_words()
            and alias.lower() not in {item.lower() for item in aliases}
        ):
            aliases.append(alias)
    return aliases


def _name_variants(name: str) -> List[str]:
    variants = []
    for variant in (name, _split_alnum_boundaries(name), _tokenized_name(name)):
        variant = re.sub(r"\s+", " ", variant).strip()
        if variant and variant.lower() not in {item.lower() for item in variants}:
            variants.append(variant)
    return variants


def _tokenized_name(name: str) -> str:
    return " ".join(re.findall(r"[A-Za-z0-9]+", _split_alnum_boundaries(name)))


def _compile_gazetteer_pattern(name: str):
    tokens = re.findall(r"[a-z0-9]+", _split_alnum_boundaries(name.lower()))
    if not tokens:
        return re.compile(r"\b" + re.escape(name.lower()) + r"\b")
    if len(tokens) == 1:
        return re.compile(r"\b" + re.escape(tokens[0]) + r"\b")
    flexible_separator = r"[\s\-_./]*"
    return re.compile(r"\b" + flexible_separator.join(re.escape(token) for token in tokens) + r"\b")


def _candidate_stopwords() -> set:
    return _stopwords() | _noise_words() | _generic_leading_words()


def _auto_alias_excluded_words() -> set:
    return _generic_leading_words() | _stopwords() | _noise_words()


def _strip_noise_phrases(text: str) -> str:
    working = text
    for phrase in _noise_phrases():
        working = re.sub(r"\b" + re.escape(phrase) + r"\b", " ", working, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", working).strip()


def _split_alnum_boundaries(value: str) -> str:
    with_digit_boundaries = re.sub(r"(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])", " ", value)
    return re.sub(r"\s+", " ", with_digit_boundaries).strip()


def _clean_fuzzy_candidate(candidate: str) -> str:
    stop_words = _noise_words() | _negation_words()
    words = [
        word
        for word in candidate.strip(" ?.!,").split()
        if word.lower() not in stop_words
    ]
    while words and words[-1].lower() in _fuzzy_trailing_words():
        words.pop()
    return " ".join(words).strip()


def _build_matchers() -> Dict[str, CategoryMatcher]:
    return {
        "organization": CategoryMatcher(_organization_entries_from_env(), has_slug=True, auto_alias=True, auto_alias_leading_word=True),
        "theme": CategoryMatcher(_theme_entries_from_env(), has_slug=False, auto_alias=True, auto_alias_leading_word=False),
        "resource_type": CategoryMatcher(_resource_type_entries_from_env(), has_slug=False, auto_alias=True, auto_alias_leading_word=False),
        "file_type": CategoryMatcher(_file_type_entries_from_env(), has_slug=True, auto_alias=False),
    }


def _organization_entries_from_env() -> List[OrgEntry]:
    return _load_env_entries("SEARCH_FILTER_ORGANIZATIONS", expected_length=3)


def _file_type_entries_from_env() -> List[OrgEntry]:
    return _load_env_entries("SEARCH_FILTER_FILE_TYPES", expected_length=3)


def _resource_type_entries_from_env() -> List[SimpleEntry]:
    return _load_env_entries("SEARCH_FILTER_RESOURCE_TYPES", expected_length=2)


def _theme_entries_from_env() -> List[SimpleEntry]:
    return _load_env_entries("SEARCH_FILTER_THEMES", expected_length=2)


def _organization_confidence_threshold() -> int:
    return _int_env("SEARCH_FILTER_ORGANIZATION_CONFIDENCE_THRESHOLD", default_value=70, min_value=0, max_value=100)


def _load_env_entries(env_name: str, expected_length: int) -> List[OrgEntry]:
    raw_value = os.getenv(env_name, "").strip()
    if not raw_value:
        return []

    try:
        entries = json.loads(raw_value)
    except json.JSONDecodeError:
        return []

    normalized_entries = []
    for entry in entries:
        if not isinstance(entry, list) or len(entry) != expected_length:
            continue

        if expected_length == 3:
            display_value, slug, aliases = entry
        else:
            display_value, aliases = entry
            slug = display_value

        if not display_value or not slug:
            continue
        if not isinstance(aliases, list):
            aliases = []

        if expected_length == 3:
            normalized_entries.append((str(display_value), str(slug), [str(alias) for alias in aliases]))
        else:
            normalized_entries.append((str(display_value), [str(alias) for alias in aliases]))

    return normalized_entries


def _stopwords() -> set:
    return _env_string_set("SEARCH_FILTER_STOPWORDS")


def _trigger_words() -> List[str]:
    return _env_string_list("SEARCH_FILTER_TRIGGER_WORDS")


def _ambiguity_delta() -> int:
    return _int_env("SEARCH_FILTER_AMBIGUITY_DELTA", default_value=5, min_value=0)


def _fuzzy_trailing_words() -> set:
    return _env_string_set("SEARCH_FILTER_FUZZY_TRAILING_WORDS")


def _negation_words() -> set:
    return _env_string_set("SEARCH_FILTER_NEGATION_WORDS")


def _negation_window_words() -> int:
    return _int_env("SEARCH_FILTER_NEGATION_WINDOW_WORDS", default_value=5, min_value=0)


def _generic_leading_words() -> set:
    return _env_string_set("SEARCH_FILTER_GENERIC_LEADING_WORDS")


def _acronym_stopwords() -> set:
    return _env_string_set("SEARCH_FILTER_ACRONYM_STOPWORDS")


def _min_fuzzy_length() -> int:
    return _int_env("SEARCH_FILTER_MIN_FUZZY_LENGTH", default_value=4, min_value=1)


def _noise_phrases() -> List[str]:
    return _env_string_list("SEARCH_FILTER_NOISE_PHRASES")


def _noise_words() -> set:
    return _env_string_set("SEARCH_FILTER_NOISE_WORDS")


def _env_string_list(env_name: str) -> List[str]:
    values = _env_json_list(env_name)
    return [str(value).strip().lower() for value in values if str(value).strip()]


def _env_string_set(env_name: str) -> set:
    return set(_env_string_list(env_name))


def _env_json_list(env_name: str) -> List:
    raw_value = os.getenv(env_name, "").strip()
    if not raw_value:
        return []
    try:
        values = json.loads(raw_value)
    except json.JSONDecodeError:
        return []
    return values if isinstance(values, list) else []


def _int_env(env_name: str, default_value: int, min_value: Optional[int] = None, max_value: Optional[int] = None) -> int:
    raw_value = os.getenv(env_name, str(default_value))
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = default_value
    if min_value is not None:
        value = max(min_value, value)
    if max_value is not None:
        value = min(max_value, value)
    return value


def _append_qdrant_match(filters: List[Dict], key: str, values: List[str]) -> None:
    values = list(dict.fromkeys(value for value in values if value))
    if not values:
        return

    match = {"value": values[0]} if len(values) == 1 else {"any": values}
    filters.append({"key": key, "match": match})


def _match_to_dict(match: MatchResult) -> Dict:
    return {
        "display_value": match.display_value,
        "slug": match.slug,
        "method": match.method,
        "score": match.score,
        "confidence": match.confidence,
        "matched_span": match.matched_span,
        "negated": match.negated,
        "alternates": match.alternates,
    }


def _is_negated(lowered_query: str, match_start: int) -> bool:
    preceding_text = lowered_query[:match_start]
    words = preceding_text.split()
    if not words:
        return False
    window_size = _negation_window_words()
    if window_size <= 0:
        return False
    window_words = words[-window_size:]
    window_text = " ".join(window_words)
    for cue in _negation_words():
        if " " in cue:
            cue_words = cue.split()
            cue_index = _find_word_sequence(window_words, cue_words)
            if cue_index != -1:
                if _negation_consumed_before_match(window_words[cue_index:], cue_words):
                    continue
                return True
        elif cue in window_words:
            cue_index = len(window_words) - 1 - window_words[::-1].index(cue)
            if _negation_consumed_before_match(window_words[cue_index:], [cue]):
                continue
            return True
    return False


def _find_word_sequence(words: List[str], sequence: List[str]) -> int:
    if not sequence or len(sequence) > len(words):
        return -1
    for index in range(0, len(words) - len(sequence) + 1):
        if words[index:index + len(sequence)] == sequence:
            return index
    return -1


def _negation_consumed_before_match(window_words: List[str], cue_words: List[str]) -> bool:
    words_after_cue = window_words[len(cue_words):]
    if not words_after_cue:
        return False

    trigger_words = set(_trigger_words())
    removable_words = _noise_words() | _stopwords()
    for index, word in enumerate(words_after_cue):
        if word in trigger_words:
            previous_content = [
                previous
                for previous in words_after_cue[:index]
                if previous not in removable_words and previous not in _negation_words()
            ]
            if previous_content:
                return True
    return False


def _strip_span(query: str, span: str) -> str:
    if not span:
        return query
    idx_lower = query.lower().find(span.lower())
    if idx_lower == -1:
        return query
    return (query[:idx_lower] + " " + query[idx_lower + len(span):]).strip()


def _strip_all(query: str, matches: List[MatchResult]) -> str:
    remaining = query
    for match in matches:
        remaining = _strip_span(remaining, match.matched_span)
    return remaining
