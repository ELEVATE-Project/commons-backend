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

from django.core.cache import cache

from chatbot.models.company_models import Company
from chatbot.models.enums import EntityStatus, FileTypeChoices
from chatbot.services.search.config import (
    VOCAB_AUTO,
    VOCAB_CANDIDATES,
    VOCAB_FULL,
    get_search_llm_setting,
)

logger = logging.getLogger('django')

CACHE_TTL_SECONDS = 300
ORG_CACHE_KEY = 'ai_search:org_vocab:{scope}'


def organization_vocabulary(scope=None):
    """
    ``{slug: [display name]}`` for every active organization, cached per scope.

    ``scope`` is unused today (search is global) but keeps the cache key ready
    for tenant-scoped search, so an unscoped cache can't leak across tenants later.
    """
    key = ORG_CACHE_KEY.format(scope=scope or 'global')
    cached = cache.get(key)
    if cached is not None:
        return cached

    rows = (
        Company.objects
        .filter(status=EntityStatus.ACTIVE)
        .exclude(slug__isnull=True).exclude(slug='')
        .values_list('slug', 'name')
    )
    # Skip inactive orgs: suggesting one would offer a filter that matches nothing.
    vocabulary = {slug: [name] for slug, name in rows if slug}

    cache.set(key, vocabulary, CACHE_TTL_SECONDS)
    return vocabulary


def file_type_vocabulary():
    """``{mime: [label, ext, .ext]}`` from the static FileTypeChoices enum."""
    extensions = FileTypeChoices.get_extension_mapping()
    vocabulary = {}
    for choice in FileTypeChoices:
        dotted = extensions.get(choice, '')
        bare = dotted.lstrip('.')
        vocabulary[choice.value] = [str(choice.label), bare, dotted]
    return vocabulary


def select_organization_vocabulary(bot, candidates=None, scope=None):
    """
    Decide how much of the organization vocabulary goes into the prompt.

    ``candidates`` = fuzzy matcher's top-N, ``full`` = every active org,
    ``auto`` = full while the list is small, candidates once it isn't.
    """
    full = organization_vocabulary(scope=scope)
    mode = get_search_llm_setting(bot, 'llm_org_vocab_mode')
    limit = get_search_llm_setting(bot, 'llm_org_candidate_limit')
    ceiling = get_search_llm_setting(bot, 'llm_org_full_max')

    known = [c for c in (candidates or []) if c in full]

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
