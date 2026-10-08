# Release 1.1.0

## Release Summary

This release improves AI search filter resolution for SG Commons media search.
The main change is a stronger deterministic RapidFuzz-based resolver for
organization and file-type filters, with structured fallback to the LLM for
queries that are too complex or ambiguous for deterministic parsing.

The release also adds support for cross-field OR filters through `any_of`,
negative filters such as excluded organizations/file types, richer search
diagnostics, and safer vector-service payload construction.

## New Features and Improvements

### Deterministic Search Filter Resolution

- Added RapidFuzz-based exact and fuzzy matching for organization and file-type
  filters.
- Added confidence scoring and candidate reporting for uncertain fuzzy matches.
- Added alias normalization for organization and file-type vocabulary.
- Added handling for negated matches, for example `except`, `without`,
  `excluding`, and similar configured negation words.
- Added generic file/document noun filtering so words like `document`, `docs`,
  and `files` do not accidentally become file-type filters.

### File-Type Handling

- Added contextual handling for `doc` so generic words such as `doc`,
  `docs`, and `document` are not treated as Microsoft Word filters unless
  the query gives enough file-format context.
- Added explicit file-type aliases for common formats such as PDF, DOC, CSV,
  spreadsheet, and presentation formats through environment
  configuration.
- File-type payloads now use canonical media-type slugs when sending filters to
  the vector service and database paths.
- Media-type aliases are expanded at the datastore boundary so Qdrant receives
  the spellings it may actually store.

### `any_of` Alternative Filters

- Added `FilterBlock` to represent one OR branch in a search filter.
- Added deterministic support for cross-field alternatives such as:
  - `PDF from Shikshalokam OR DOCX from CSF`
  - `PDF from A or B`
  - `A or B PDFs`
- Added safeguards to drop empty `any_of` blocks and one-branch alternatives.
- Added support for excluding organizations and file types inside filter blocks.
- Added logic to avoid sending alternatives that flatten back to the same
  normal AND filter.

### LLM Fallback and Diagnostics

- Added configurable fallback behavior through `AI_SEARCH_LLM_MODE`.
- Added complexity reasons that force LLM fallback when deterministic parsing is
  likely unsafe:
  - `complex_alternatives_query_length`
  - `complex_alternatives_count`
  - `complex_alternatives_organizations`
  - `complex_alternatives_exclusions`
- Added `alternative_llm_reason` in search filter diagnostics.
- Logged alternative LLM reasons through the Django logger so they appear in
  `logs/debug.log` with the current logging configuration.

### Vector Search Payload Improvements

- Added a shared metadata search payload builder.
- Added support for sending these filters to the vectorization service:
  - `organizations`
  - `file_type`
  - `exclude_organizations`
  - `exclude_file_type`
  - `any_of`
- Added filter-only fallback to the database listing path when no semantic
  query remains after filter extraction.
- Added `rapidfuzz_filters` metadata
  to search responses for easier debugging.

## Environment Keys Changed in This Release

The following `sample.env` keys were added or modified by the commits covered
in this release.

### Newly Added Keys

```env
SEARCH_FILTER_ANY_OF_MAX_QUERY_WORDS=40
SEARCH_FILTER_ANY_OF_MAX_ALTERNATIVES=4
SEARCH_FILTER_ANY_OF_MAX_ORGANIZATIONS=2
SEARCH_FILTER_ANY_OF_MAX_EXCLUSIONS=1
```

These keys cap deterministic `any_of` parsing. Queries beyond these limits are
treated as complex and can force LLM fallback when LLM fallback mode is enabled.

### Modified Keys

```env
SEARCH_FILTER_FILE_TYPES
```

- DOC aliases were narrowed so generic `doc/docx` handling does not over-match
  generic document-language queries.

```env
SEARCH_FILTER_ORGANIZATION_CONFIDENCE_THRESHOLD
```

- Default organization fuzzy threshold changed from `70` to `90` to reduce
  false-positive organization matches.

```env
SEARCH_FILTER_STOPWORDS
```

- Added extra generic words such as `library` and `every` so they are ignored
  during filter extraction.

```env
SEARCH_FILTER_NEGATION_WORDS
```

- Added additional exclusion phrases including `apart from`, `but`, `but not`,
  and `but nothing`.

```env
SEARCH_FILTER_TRIGGER_WORDS
```

- Added `belonging to` as a phrase that can introduce a filter candidate.

```env
SEARCH_FILTER_NOISE_PHRASES
```

- Added `belonging to` as removable query noise after filter extraction.

```env
SEARCH_FILTER_NOISE_WORDS
```

- Added `are` as removable query noise.

The following existing/search-related configuration is used heavily by this
release:

```env
SEARCH_FILTER_FILE_TYPES
SEARCH_FILTER_EXCLUDED_FILE_TYPE_ALIASES
SEARCH_FILTER_FUZZY_CANDIDATE_STOPWORDS
SEARCH_FILTER_ORGANIZATION_CONFIDENCE_THRESHOLD
SEARCH_FILTER_STOPWORDS
SEARCH_FILTER_TRIGGER_WORDS
SEARCH_FILTER_AMBIGUITY_DELTA
SEARCH_FILTER_FUZZY_TRAILING_WORDS
SEARCH_FILTER_NEGATION_WORDS
SEARCH_FILTER_NEGATION_WINDOW_WORDS
SEARCH_FILTER_GENERIC_LEADING_WORDS
SEARCH_FILTER_ACRONYM_STOPWORDS
SEARCH_FILTER_MIN_FUZZY_LENGTH
SEARCH_FILTER_NOISE_PHRASES
SEARCH_FILTER_NOISE_WORDS
AI_SEARCH_LLM_MODE
AI_SEARCH_LLM_CONFIDENCE_THRESHOLD
```

## RapidFuzz Resolver: What It Can Handle

The deterministic RapidFuzz path is intended for bounded, vocabulary-driven
filter extraction. It can handle:

- Exact organization and file-type aliases from configured vocabularies.
- Fuzzy organization matching for short natural-language queries when the
  candidate is close enough to a known organization name or alias.
- Organization names with punctuation, casing, spacing, hyphen, underscore,
  slash, and dot variations.
- Positive file-type filters, for example `PDF files`.
- Negative filters, for example `except Shikshalokam` or `without PDF`.
- Simple include/exclude polarity conflicts, where exclusion takes precedence.
- Common filler/noise text, such as `show me`, `give me`, `documents`, and
  similar configured stopwords/noise phrases.
- Compact OR alternatives where branches are simple and field-based.
- Shared qualifier alternatives such as `PDF from A or B`.
- File-type-only alternatives such as `PDF or CSV`.
- Organization-only alternatives such as `A or B`.
- Queries that reduce to filters only, where the semantic query can be empty.

## RapidFuzz Resolver: Known Limitations

RapidFuzz is not a semantic parser. The deterministic path intentionally stays
conservative and hands off to LLM fallback when queries exceed configured
complexity limits. Known limitations:

- It only matches against configured organizations, file types, and aliases.
  Unknown organizations or missing aliases cannot be reliably discovered.
- It cannot infer intent from broad semantic language unless that language maps
  to configured trigger words, stopwords, aliases, or negation terms.
- It does not understand deep grammar or nested logical expressions.
- It supports simple OR alternatives, but complex nested combinations of AND,
  OR, exclusions, and topic clauses may require LLM fallback.
- It does not resolve pronouns or conversational references such as `those`,
  `same org`, or `the previous one`.
- It may miss abbreviations that are not configured and cannot be safely derived
  from the organization name.
- It may treat ambiguous short words conservatively to avoid false positives.
- Generic words such as `doc`, `docs`, `document`, and `file` are intentionally
  not treated as file-type filters unless the query gives clear format context.
- It does not validate whether a matched organization actually has matching
  media for a requested file type before sending the filter.
- It cannot perfectly scope every negation in long natural-language queries.
  More exclusion-heavy queries are routed toward LLM fallback using configured
  limits.
- It does not perform semantic topic extraction. After removing filter spans,
  remaining text is passed as the semantic query.
- It depends on confidence thresholds; raising thresholds reduces false
  positives but increases LLM fallback or missed fuzzy matches.

## Backward Compatibility

- Existing search requests continue to work with flat filters.
- `any_of`, `exclude_organizations`, and `exclude_file_type` are additive
  payload fields for vector search.
- If the vector service does not support newer filter fields, callers still
  receive structured error metadata instead of an unhandled failure.
- LLM fallback can be disabled with `AI_SEARCH_LLM_MODE=off`.

## Operational Notes

- Review `sample.env` and ensure all `SEARCH_FILTER_*` and `AI_SEARCH_*`
  settings are present in deployment environments.
- Ensure AI-Service credentials are configured if `AI_SEARCH_LLM_MODE` is
  `fallback` or `always`.
- Check `search_metadata.filter_resolution` in API responses when debugging
  filter decisions.
- Check `logs/debug.log` for alternative LLM fallback reasons.
