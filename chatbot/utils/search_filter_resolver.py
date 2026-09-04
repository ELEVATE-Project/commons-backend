import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from rapidfuzz import fuzz, process

OrgEntry = Tuple[str, str, List[str]]


@dataclass(frozen=True)
class MatchResult:
    display_value: str
    slug: Optional[str]
    method: str
    score: int
    matched_span: str
    negated: bool = False
    alternates: List[str] = field(default_factory=list)

    @property
    def confidence(self) -> str:
        if self.score >= 90:
            return "high"
        if self.score >= 75:
            return "medium"
        return "low"


@dataclass
class ResolvedFilters:
    organization: List[MatchResult] = field(default_factory=list)
    file_type: List[MatchResult] = field(default_factory=list)
    search_text: str = ""
    confidence: float = 0.0
    candidates: Dict[str, List[str]] = field(default_factory=dict)


class CategoryMatcher:
    def __init__(
        self,
        entries: List[OrgEntry],
        auto_alias: bool = False,
        auto_alias_leading_word: bool = True,
        excluded_aliases: Optional[set] = None,
    ):
        self._lookup = {}  # type: Dict[str, Tuple[str, str]]
        self._all_names = []  # type: List[str]
        excluded_aliases = _normalized_excluded_aliases(
            excluded_aliases or set()
        )

        for display_name, slug, aliases in entries:
            all_aliases = list(aliases)
            if auto_alias:
                for auto in derive_auto_aliases(display_name, include_leading_word=auto_alias_leading_word):
                    if auto.lower() not in {alias.lower() for alias in all_aliases} and auto.lower() != display_name.lower():
                        all_aliases.append(auto)

            for name in (display_name,) + tuple(all_aliases):
                for variant in _name_variants(name):
                    key = variant.strip().lower()
                    if not key or key in excluded_aliases:
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
                    matched_span=query[start:end],
                    negated=_is_negated(lowered, start),
                )))
                claimed_spans.append((start, end))
                found_display_values.add(display_value)

        hits.sort(key=lambda hit: hit[0])
        return [result for _, result in hits]


def resolve_query_exact(
    query: str,
    organization_vocabulary: Optional[Dict[str, List[str]]] = None,
    file_type_vocabulary: Optional[Dict[str, List[str]]] = None,
) -> ResolvedFilters:
    remaining = query or ""
    results = {
        "organization": [],
        "file_type": [],
    }  # type: Dict[str, List[MatchResult]]
    matchers = _build_matchers(
        organization_vocabulary=organization_vocabulary,
        file_type_vocabulary=file_type_vocabulary,
    )

    for field_name in ("organization", "file_type"):
        matcher = matchers[field_name]
        matches = matcher.find_all_exact(remaining)
        results[field_name] = matches
        if matches:
            remaining = _strip_all(remaining, matches)

    candidates = {}
    for field_name in ("organization", "file_type"):
        if not _should_run_fuzzy_match(field_name, query):
            continue

        existing_matches = results.get(field_name, [])
        threshold = _confidence_threshold(field_name)
        fuzzy_matches = matchers[field_name].find_all_fuzzy(
            remaining,
            threshold,
            exclude_display_values=[
                match.display_value for match in existing_matches
            ],
        )
        if fuzzy_matches:
            results[field_name].extend(fuzzy_matches)
            candidates[field_name] = [
                match.slug if match.slug else match.display_value
                for match in fuzzy_matches[:_candidate_limit()]
            ]
            remaining = _strip_all(remaining, fuzzy_matches)
        else:
            near_matches = matchers[field_name].find_all_fuzzy(
                remaining,
                _candidate_threshold(field_name),
                exclude_display_values=[
                    match.display_value for match in existing_matches
                ],
            )
            if near_matches:
                candidates[field_name] = [
                    match.slug if match.slug else match.display_value
                    for match in near_matches[:_candidate_limit()]
                ]

    scores = [
        match.score
        for matches in results.values()
        for match in matches
    ]
    confidence = (min(scores) / 100.0) if scores else 0.0

    return ResolvedFilters(
        organization=results["organization"],
        file_type=results["file_type"],
        search_text=clean_search_text(remaining),
        confidence=confidence,
        candidates=candidates,
    )


def included_values(matches: Iterable[MatchResult], use_slug: bool = False) -> List[str]:
    values = []
    for match in matches:
        if match.negated:
            continue
        values.append(match.slug if use_slug and match.slug else match.display_value)
    return list(dict.fromkeys(values))


def to_response_dict(query: str, resolved: ResolvedFilters) -> Dict:
    return {
        "query": query,
        "resolved": {
            "organization": [_match_to_dict(match) for match in resolved.organization],
            "file_type": [_match_to_dict(match) for match in resolved.file_type],
        },
        "search_text": resolved.search_text,
        "confidence": resolved.confidence,
        "candidates": resolved.candidates,
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
    removable_words = _noise_words() | _negation_words() | _stopwords()
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


def _normalized_excluded_aliases(aliases: Iterable[str]) -> set:
    normalized = set()
    for alias in aliases:
        for variant in _name_variants(str(alias)):
            key = variant.strip().lower()
            if key:
                normalized.add(key)
    return normalized


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
    return (
        _stopwords()
        | _noise_words()
        | _generic_leading_words()
        | _fuzzy_candidate_stopwords()
    )


def _auto_alias_excluded_words() -> set:
    return _generic_leading_words() | _stopwords() | _noise_words()


def _strip_noise_phrases(text: str) -> str:
    working = text
    for phrase in _noise_phrases():
        working = re.sub(r"\b" + re.escape(phrase) + r"\b", " ", working, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", working).strip()


def _should_run_fuzzy_match(field_name: str, query: str) -> bool:
    if field_name != "organization":
        return True
    return _has_trigger_word(query, _organization_trigger_words())


def _has_trigger_word(query: str, triggers: Iterable[str]) -> bool:
    lowered = (query or "").lower()
    for trigger in triggers:
        trigger = str(trigger).strip().lower()
        if not trigger:
            continue
        if re.search(r"\b" + re.escape(trigger) + r"\b", lowered):
            return True
    return False


def _split_alnum_boundaries(value: str) -> str:
    with_digit_boundaries = re.sub(r"(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])", " ", value)
    return re.sub(r"\s+", " ", with_digit_boundaries).strip()


def _clean_fuzzy_candidate(candidate: str) -> str:
    stop_words = (
        _noise_words()
        | _negation_words()
        | _fuzzy_candidate_stopwords()
    )
    words = [
        word
        for word in candidate.strip(" ?.!,").split()
        if word.lower() not in stop_words
    ]
    while words and words[-1].lower() in _fuzzy_trailing_words():
        words.pop()
    return " ".join(words).strip()


def _build_matchers(
    organization_vocabulary: Optional[Dict[str, List[str]]] = None,
    file_type_vocabulary: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, CategoryMatcher]:
    return {
        "organization": CategoryMatcher(
            _organization_entries(organization_vocabulary),
            auto_alias=True,
            auto_alias_leading_word=False,
        ),
        "file_type": CategoryMatcher(
            _file_type_entries(file_type_vocabulary),
            auto_alias=False,
            excluded_aliases=_excluded_file_type_aliases(),
        ),
    }


def _organization_entries(vocabulary) -> List[OrgEntry]:
    if not vocabulary:
        return _organization_entries_from_env()
    return _entries_from_vocabulary(vocabulary)


def _file_type_entries(vocabulary) -> List[OrgEntry]:
    if not vocabulary:
        return _file_type_entries_from_env()
    return _merge_env_aliases(
        _entries_from_vocabulary(vocabulary),
        _file_type_entries_from_env(),
    )


def _entries_from_vocabulary(vocabulary) -> List[OrgEntry]:
    entries = []
    for slug, aliases in (vocabulary or {}).items():
        aliases = [str(alias) for alias in aliases or [] if alias]
        display_name = aliases[0] if aliases else str(slug)
        extra_aliases = list(dict.fromkeys(aliases + [str(slug)]))
        entries.append((display_name, str(slug), extra_aliases))
    return entries


def _merge_env_aliases(entries: List[OrgEntry], env_entries: List[OrgEntry]) -> List[OrgEntry]:
    by_slug = {
        slug: (display_name, slug, list(aliases))
        for display_name, slug, aliases in entries
    }
    for display_name, slug, aliases in env_entries:
        existing = by_slug.get(slug)
        if existing is None:
            by_slug[slug] = (display_name, slug, list(aliases))
            continue

        existing_display, _, existing_aliases = existing
        merged_aliases = list(dict.fromkeys(existing_aliases + list(aliases)))
        by_slug[slug] = (existing_display or display_name, slug, merged_aliases)
    return list(by_slug.values())


def _organization_entries_from_env() -> List[OrgEntry]:
    return _load_env_entries("SEARCH_FILTER_ORGANIZATIONS")


def _file_type_entries_from_env() -> List[OrgEntry]:
    return _load_env_entries("SEARCH_FILTER_FILE_TYPES")


def _organization_confidence_threshold() -> int:
    return _int_env("SEARCH_FILTER_ORGANIZATION_CONFIDENCE_THRESHOLD", default_value=70, min_value=0, max_value=100)


def _confidence_threshold(field_name: str) -> int:
    if field_name == "organization":
        return _organization_confidence_threshold()
    return _int_env(
        f"SEARCH_FILTER_{field_name.upper()}_CONFIDENCE_THRESHOLD",
        default_value=85,
        min_value=0,
        max_value=100,
    )


def _candidate_threshold(field_name: str) -> int:
    return max(50, _confidence_threshold(field_name) - 15)


def _candidate_limit() -> int:
    return _int_env("SEARCH_FILTER_CANDIDATE_LIMIT", default_value=5, min_value=1)


def _load_env_entries(env_name: str) -> List[OrgEntry]:
    raw_value = os.getenv(env_name, "").strip()
    if not raw_value:
        return []

    try:
        entries = json.loads(raw_value)
    except json.JSONDecodeError:
        return []

    normalized_entries = []
    for entry in entries:
        if not isinstance(entry, list):
            continue

        try:
            display_value, slug, aliases = entry
        except ValueError:
            continue

        if not display_value or not slug:
            continue
        if not isinstance(aliases, list):
            aliases = []

        normalized_entries.append((str(display_value), str(slug), [str(alias) for alias in aliases]))

    return normalized_entries


def _stopwords() -> set:
    return _env_string_set("SEARCH_FILTER_STOPWORDS")


def _excluded_file_type_aliases() -> set:
    return _env_string_set("SEARCH_FILTER_EXCLUDED_FILE_TYPE_ALIASES")


def _fuzzy_candidate_stopwords() -> set:
    return _env_string_set("SEARCH_FILTER_FUZZY_CANDIDATE_STOPWORDS")


def _organization_trigger_words() -> List[str]:
    return _env_string_list("SEARCH_FILTER_ORGANIZATION_TRIGGER_WORDS")


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


def _match_to_dict(match: MatchResult) -> Dict:
    return {
        "display_value": match.display_value,
        "slug": match.slug,
        "method": match.method,
        "score": match.score,
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

    last_negation = max(
        (lowered_query.rfind(cue, 0, match_start) for cue in _negation_words()),
        default=-1,
    )
    if last_negation == -1:
        return False

    scope_breakers = ("about", "regarding", "related to", "covering", "from", "on")
    last_breaker = max(
        (lowered_query.rfind(breaker, 0, match_start) for breaker in scope_breakers),
        default=-1,
    )
    if last_breaker > last_negation:
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
