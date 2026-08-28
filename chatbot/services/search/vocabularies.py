"""
Closed vocabularies the LLM may pick filter values from, plus validation
that holds it to them.

Values must be the DB slug, never the display name: Qdrant's MatchAny filter
is case-sensitive while Postgres's ``__iexact`` isn't, so a mis-cased slug
would silently drop results from one store but not the other. Aliases and
case-insensitive matching decide *whether* a value is valid, but
``canonicalise`` always returns the exact string from the database.
"""

import logging

from chatbot.models.enums import EntityStatus, FileTypeChoices
from chatbot.services.search.config import (
    VOCAB_AUTO,
    VOCAB_CANDIDATES,
    VOCAB_FULL,
    get_search_llm_setting,
)
from chatbot.utils.company_cache import get_all_companies

logger = logging.getLogger('django')


def organization_vocabulary(scope=None):
    """
    ``{slug: [display name]}`` for every active organization.

    The organization list comes from Vishwa's Redis-backed company cache
    (`get_all_companies`) instead of SEARCH_FILTER_ORGANIZATIONS. When the Redis
    cache is cold, that helper hydrates it from the database.
    """
    return {
        company.slug: [company.name]
        for company in get_all_companies()
        if (
            company.slug
            and company.status == EntityStatus.ACTIVE
        )
    }


def file_type_vocabulary():
    """``{mime: [label, ext, .ext]}`` from the static FileTypeChoices enum."""
    vector_type_aliases = {
        FileTypeChoices.CSV.value: ["project_task"],
        FileTypeChoices.XLS.value: ["xlsx_rag_optimized"],
        FileTypeChoices.XLSX.value: ["xlsx_rag_optimized"],
        FileTypeChoices.TXT.value: ["text", "markdown"],
    }
    extensions = FileTypeChoices.get_extension_mapping()
    vocabulary = {}
    for choice in FileTypeChoices:
        dotted = extensions.get(choice, '')
        bare = dotted.lstrip('.')
        label = str(choice.label)
        aliases = [label, bare, dotted]
        aliases.extend(vector_type_aliases.get(choice.value, []))
        if label:
            aliases.append(f"{label}s")
        if bare:
            aliases.append(f"{bare}s")
        vocabulary[choice.value] = list(dict.fromkeys(aliases))
    return vocabulary


def select_organization_vocabulary(bot, candidates=None, scope=None):
    """
    Decide how much of the organization vocabulary goes into the prompt.

    ``candidates`` = fuzzy matcher's top-N, ``full`` = every active org,
    ``auto`` = full while the list is small, candidates once it isn't.

    ``llm_org_use_fuzzy_candidates`` overrides all of that: when it is on and
    the matcher proposed something usable, only its result is sent.
    """
    full = organization_vocabulary(scope=scope)
    mode = get_search_llm_setting(bot, 'llm_org_vocab_mode')
    limit = get_search_llm_setting(bot, 'llm_org_candidate_limit')
    ceiling = get_search_llm_setting(bot, 'llm_org_full_max')

    known = [c for c in (candidates or []) if c in full]

    # Opt-in switch: send the fuzzy matcher's result instead of the whole list,
    # unpadded. Falls through when it proposed nothing this vocabulary knows.
    if known and get_search_llm_setting(bot, 'llm_org_use_fuzzy_candidates'):
        logger.info(
            'ai_search: sending %s fuzzy org candidate(s) instead of all %s',
            len(known[:limit]), len(full))
        return {slug: full[slug] for slug in known[:limit]}

    if mode == VOCAB_AUTO:
        mode = VOCAB_FULL if len(full) <= ceiling else VOCAB_CANDIDATES

    if mode == VOCAB_CANDIDATES and not known:
        # No candidates means the model would see no orgs at all, so fall back to full.
        logger.info('ai_search: no org candidates, sending the full list instead')
        mode = VOCAB_FULL

    if mode == VOCAB_FULL and len(full) > ceiling:
        # Enforced even for explicit 'full' mode: caps prompt cost and avoids
        # tripping AI-Service's input-size guardrail (which returns 400).
        logger.warning(
            'ai_search: %s active organizations exceeds llm_org_full_max=%s, '
            'sending candidates only', len(full), ceiling)
        mode = VOCAB_CANDIDATES

    if mode == VOCAB_FULL:
        return full

    # Known candidates stay in; top up from the full list without replacing them.
    selected = {slug: full[slug] for slug in known[:limit]}
    for slug, aliases in full.items():
        if len(selected) >= limit:
            break
        selected.setdefault(slug, aliases)
    return selected


def expand_aliases(values, vocabulary):
    """
    Each canonical value plus its aliases, de-duplicated, order preserved.

    Field-agnostic: any ``{value: [alias, ...]}`` vocabulary works. Needed
    because one logical value can be stored under several spellings — Qdrant's
    ``metadata.type`` holds both ``application/pdf`` and a bare ``pdf`` — so a
    value sent to the vector service has to be widened to all of them. A value
    that is not in the vocabulary is passed through untouched.
    """
    expanded = []
    for value in values or []:
        for candidate in [value] + list((vocabulary or {}).get(value) or []):
            if candidate and candidate not in expanded:
                expanded.append(candidate)
    return expanded


def canonicalise(value, vocabulary):
    """Match a value (or its alias) against the vocabulary, case-insensitively,
    and return the canonical stored form, or None if it's not in the vocabulary."""
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate:
        return None

    if candidate in vocabulary:
        return candidate

    folded = candidate.casefold()
    for canonical, aliases in vocabulary.items():
        if folded == canonical.casefold():
            return canonical
        for alias in aliases:
            if alias and folded == str(alias).casefold():
                return canonical
    return None


def canonicalise_all(values, vocabulary):
    """Canonicalise a list of values. Returns ``(accepted, rejected)`` — anything
    the model invented lands in ``rejected`` and never reaches a query."""
    accepted, rejected = [], []
    for value in values or []:
        canonical = canonicalise(value, vocabulary)
        if canonical is None:
            rejected.append(value)
        elif canonical not in accepted:
            accepted.append(canonical)
    return accepted, rejected
