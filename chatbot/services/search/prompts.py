"""
The prompt and tool schema for search filter extraction, and the lookup that
finds the bot holding them.

**SYSTEM_PROMPT and build_tool_schema() are seeds, not the runtime prompt.**
create_ai_search_bot.py writes them into CompanyBot.context and
CompanyBot.tool_context, and the extractor reads the row from then on — editing
a prompt in the admin takes effect without a deploy, and SYSTEM_PROMPT is only
reached at all if context is empty. They live next to the lookup so the script
that seeds the bot cannot drift from what the extractor expects to find in it.

They live on a bot of their own, found by route with no company scoping: one
route, one row, shared by every organization.

Not to be confused with /sg_search_bot. That is a separate, older row whose
filter_score tunes the vector query in chatbot/views/Media/media_api_views.py.
Nothing here reads or writes it, and the seeding script refuses to target it.
"""

import json
import logging
import os

from chatbot.models.company_models import CompanyBot
from chatbot.models.enums import FileTypeChoices

logger = logging.getLogger('django')

# Seeds the schema below, and is the fallback the extractor matches on when a
# bot has no usable tool_context. A bot that renames the function in its own
# tool_context is honoured — llm_extractor reads the name back out of the row —
# but rule 5 of SYSTEM_PROMPT names the function literally, so a rename means
# editing that bot's context to match.
TOOL_NAME = 'apply_search_filters'

# The route of the filter bot, and the only bot route that is configurable.
# Resolved once at import rather than per call: the seeding script imports this
# same constant, so a value that could change mid-process would let the script
# seed one route while the resolver looked up another.
DEFAULT_BOT_ROUTE = '/ai_search_filters'
SEARCH_BOT_ROUTE = (os.getenv('AI_SEARCH_BOT_ROUTE') or '').strip() or DEFAULT_BOT_ROUTE

# The older search bot. Named here only so the script can refuse to seed onto it
# — media_api_views.py reads its filter_score, and overwriting that row's prompt
# and tool schema would take the vector query's tuning with it.
LEGACY_SEARCH_BOT_ROUTE = '/sg_search_bot'


def get_search_bot():
    """
    Return the CompanyBot holding the filter-extraction prompt, or None.

    Search is not company-scoped: one route, one row, no fallback chain. If it is
    missing the caller skips the LLM — an absent row is a reason to fall back to
    fuzzy matching, never to fail a search.
    """
    # Ordered explicitly: CompanyBot has no unique constraint on (company, route)
    # — only an index on company — so a bare .first() returns an arbitrary row
    # when duplicates exist, and a search would not behave the same way twice.
    # create_ai_search_bot.py orders the same way so seeding writes to the row
    # this reads.
    bot = (
        CompanyBot.objects
        .filter(route=SEARCH_BOT_ROUTE)
        .order_by('-updated_at', '-id')
        .first()
    )
    if bot is None:
        logger.warning(
            'ai_search: no search bot at %s; skipping the LLM', SEARCH_BOT_ROUTE)
    return bot


SYSTEM_PROMPT = """\
You convert a user's natural-language search request into structured search \
filters for a document library.

You are given the user's query, the list of organization values that exist in \
the system, and — when available — candidate matches suggested by a fuzzy \
matcher. Your job is to decide which filters the user is asking for, and to \
restate whatever is left of their request as a clean search query.

Rules:

1. Only ever return organization and file type values that appear in the lists \
given to you. Copy them exactly as written, character for character. Never \
invent a value, never reformat one, and never return an organization's display \
name in place of its listed value.
2. Treat the fuzzy matcher's candidates as suggestions. Confirm one if it is \
right, pick a different listed value if it is wrong, or return none if the user \
did not ask for that filter at all.
3. If the user did not ask to filter on something, omit that field entirely. \
Return an empty list only when the user explicitly asked for no such filter. \
Omitting a field and returning an empty list mean different things, so be \
deliberate about which you use.
4. semantic_query is what remains of the request once the filter words are \
removed — the topic the user actually wants documents about. Keep it short and \
faithful to their words. Do not add words they did not use. If removing the \
filter words leaves nothing meaningful, return their original query unchanged.
5. Report the result by calling the apply_search_filters function. If function \
calling is not available to you, return the same fields as a single JSON object \
and nothing else: {"organizations": [...], "file_types": [...], \
"semantic_query": "..."}. Never answer in prose and never add explanation \
around the result.

Example — for "list all PDFs from the Shikshalokam organization", where the \
organization list contains shikshalokam, you would return that organization, \
the PDF file type, and a semantic_query of "" (nothing is left to search for \
beyond the filters).\
"""


def build_tool_schema():
    """
    The function-calling schema, in the {"tool": [...], "tool_choice": ...}
    shape that CompanyBot.tool_context already uses elsewhere.

    File types carry an enum because FileTypeChoices is static. Organizations
    deliberately do not: Company rows change, and a baked-in enum would stale
    the bot row every time an organization is added. The organization vocabulary
    is supplied per request instead, and enforced by post-validation.

    The schema is a best effort, not a guarantee. AI Service calls LiteLLM with
    drop_params=True, so for a model without tool support both `tools` and
    `tool_choice` are dropped silently and the answer arrives as content — which
    is why rule 5 of SYSTEM_PROMPT also spells out the plain JSON shape, and why
    the client falls back to parsing it. Correctness comes from post-validation
    against the vocabulary either way; this only improves adherence.
    """
    return {
        'tool': [{
            'type': 'function',
            'function': {
                'name': TOOL_NAME,
                'description': (
                    'Record the search filters requested by the user and the '
                    'residual search query.'
                ),
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'organizations': {
                            'type': 'array',
                            'description': (
                                'Organization values from the supplied list. '
                                'Omit if the user did not ask to filter by organization.'
                            ),
                            'items': {'type': 'string'},
                        },
                        'file_types': {
                            'type': 'array',
                            'description': (
                                'File type values from the supplied list. '
                                'Omit if the user did not ask to filter by file type.'
                            ),
                            'items': {
                                'type': 'string',
                                'enum': [choice.value for choice in FileTypeChoices],
                            },
                        },
                        'semantic_query': {
                            'type': 'string',
                            'description': (
                                'What the user wants documents about, once filter '
                                'words are removed. May be empty.'
                            ),
                        },
                    },
                    'required': ['semantic_query'],
                },
            },
        }],
        'tool_choice': {'type': 'function', 'function': {'name': TOOL_NAME}},
    }


def tool_context_json():
    """The tool schema serialised for storage in CompanyBot.tool_context."""
    return json.dumps(build_tool_schema(), indent=2)


def build_user_message(raw_query, organizations, file_types, candidates=None):
    """
    Assemble the per-request message: the query, the vocabularies the model may
    choose from, and any fuzzy-matcher suggestions.

    ``organizations`` maps the value to filter on (the slug) to its aliases;
    the value is what the model must return, the aliases only help it recognise
    what the user meant.
    """
    lines = [f'User query: {raw_query}', '']

    lines.append('Organization values you may return (value — also known as):')
    if organizations:
        for value, aliases in organizations.items():
            known_as = ', '.join(a for a in aliases if a) or value
            lines.append(f'  {value} — {known_as}')
    else:
        lines.append('  (none available)')
    lines.append('')

    lines.append('File type values you may return (value — also known as):')
    for value, aliases in file_types.items():
        lines.append(f"  {value} — {', '.join(a for a in aliases if a)}")
    lines.append('')

    if candidates:
        lines.append('Suggestions from the fuzzy matcher (confirm or correct these):')
        for field, values in candidates.items():
            if values:
                lines.append(f"  {field}: {', '.join(str(v) for v in values)}")
        lines.append('')

    return '\n'.join(lines).strip()
