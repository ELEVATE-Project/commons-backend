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
from string import Template

from chatbot.models.company_models import CompanyBot
from chatbot.models.enums import FileTypeChoices

logger = logging.getLogger('django')

# Seeds the schema below, and is the fallback the extractor matches on when a
# bot has no usable tool_context. A bot that renames the function in its own
# tool_context is honoured — llm_extractor reads the name back out of the row —
# but rule 8 of SYSTEM_PROMPT names the function literally, so a rename means
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
matcher. Your job is to decide which filters the user is asking for, and \
whether anything is left over that is a genuine search topic.

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
4. Only filter by organization when the user names one. "from all \
organizations", "from all companies", "across organizations" and similar mean \
the user wants no organization filter — return an empty list for organizations. \
Never answer these by listing every organization you were shown.
5. A value the user asks to leave out is an exclusion. Put it in \
exclude_organizations or exclude_file_types, never in organizations or \
file_types. Exclusion values come from the same lists and follow rules 1 and 2 \
just like positive ones. Words that signal an exclusion: "except", "excluding", \
"other than", "apart from", "besides", "not from", "without".
  - "all organizations except X" is still not an organization filter: return an \
empty list for organizations and put X in exclude_organizations. Never answer \
it by listing every other organization.
  - A field can have positives and exclusions at once, and a request may be \
exclusions only.
6. semantic_query is a subject the user wants documents *about*, and nothing \
else. Return "" whenever the request is only asking to list or filter \
documents. These are never a semantic_query, alone or in combination:
  - requesting words: "get", "get me", "give me", "show", "list", "find", \
"fetch", "search for", "I want", "I need"
  - quantity words: "all", "every", "any", "a list of", "the list of"
  - document words: "file", "files", "document", "documents", "doc", "docs"
  - file type names: "PDF", "PDFs", "CSV", "spreadsheet", and the other listed \
types
  - organization words: "organization", "organizations", "company", \
"companies", and any organization name
  - exclusion words: "except", "excluding", "other than", "apart from", \
"besides", "not from", "without", and whatever is being excluded
7. When there is a genuine topic, semantic_query is that topic and nothing \
more. Keep it short and faithful to the user's words — usually what follows \
"about", "on", "regarding", or "related to". Do not add words they did not use, \
and do not carry the words from rule 6 into it.
8. Report the result by calling the apply_search_filters function. If function \
calling is not available to you, return the same fields as a single JSON object \
and nothing else: {"organizations": [...], "file_types": [...], \
"exclude_organizations": [...], "exclude_file_types": [...], \
"semantic_query": "..."}. Never answer in prose and never add explanation \
around the result.

Examples, assuming the organization list contains shikshalokam and csf:

  "get list of all PDF files"
    -> file_types ["application/pdf"], organizations omitted, semantic_query ""
  "get the PDF from all organizations"
    -> file_types ["application/pdf"], organizations [], semantic_query ""
  "get all PDF files across organizations"
    -> file_types ["application/pdf"], organizations [], semantic_query ""
  "list all PDFs from the Shikshalokam organization"
    -> file_types ["application/pdf"], organizations ["shikshalokam"], \
semantic_query ""
  "find PDF files about teacher training"
    -> file_types ["application/pdf"], organizations omitted, semantic_query \
"teacher training"
  "find PDFs from Shikshalokam about teacher training"
    -> file_types ["application/pdf"], organizations ["shikshalokam"], \
semantic_query "teacher training"
  "get all PDF files from all organizations except Shikshalokam"
    -> file_types ["application/pdf"], organizations [], \
exclude_organizations ["shikshalokam"], semantic_query ""
  "give me all doc/files except PDF"
    -> exclude_file_types ["application/pdf"], organizations omitted, \
semantic_query ""
  "find PDF files about teacher training except files from CSF"
    -> file_types ["application/pdf"], exclude_organizations ["csf"], \
semantic_query "teacher training"\
"""


# The per-request message layout. Seeded into CompanyBot.pre_context and read
# back from there, so the wording is editable in admin without a deploy; this
# constant is only the fallback for an empty column.
#
# $query, $organizations, $file_types and $candidates are filled in per request.
# $candidates renders to nothing when the fuzzy matcher suggested nothing.
USER_MESSAGE_TEMPLATE = """\
User query: $query

Organization values you may return (value — also known as):
$organizations

File type values you may return (value — also known as):
$file_types
$candidates\
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
    is why rule 8 of SYSTEM_PROMPT also spells out the plain JSON shape, and why
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
                                'Omit if the user did not ask to filter by organization. '
                                'Return an empty list if they asked for all '
                                'organizations; never list every value instead.'
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
                        'exclude_organizations': {
                            'type': 'array',
                            'description': (
                                'Organization values from the supplied list that the '
                                'user asked to leave out ("except X", "not from X"). '
                                'Omit if they excluded no organization.'
                            ),
                            'items': {'type': 'string'},
                        },
                        'exclude_file_types': {
                            'type': 'array',
                            'description': (
                                'File type values from the supplied list that the user '
                                'asked to leave out ("except PDF"). Omit if they '
                                'excluded no file type.'
                            ),
                            'items': {
                                'type': 'string',
                                'enum': [choice.value for choice in FileTypeChoices],
                            },
                        },
                        'semantic_query': {
                            'type': 'string',
                            'description': (
                                'The subject the user wants documents about, once '
                                'filter words are removed. Empty when the request '
                                'is only asking to list or filter documents.'
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


def _vocabulary_block(vocabulary, empty=''):
    """Render ``{value: [alias, ...]}`` as indented "value — aliases" lines."""
    lines = []
    for value, aliases in (vocabulary or {}).items():
        known_as = ', '.join(a for a in aliases if a) or value
        lines.append(f'  {value} — {known_as}')
    return '\n'.join(lines) or empty


def _candidates_block(candidates):
    """Render the fuzzy matcher's suggestions, or '' when there are none."""
    lines = [
        f"  {field}: {', '.join(str(v) for v in values)}"
        for field, values in (candidates or {}).items() if values
    ]
    if not lines:
        return ''
    return (
        '\nSuggestions from the fuzzy matcher (confirm or correct these):\n'
        + '\n'.join(lines)
    )


def build_user_message(raw_query, organizations, file_types, candidates=None,
                       template=None):
    """
    Assemble the per-request message: the query, the vocabularies the model may
    choose from, and any fuzzy-matcher suggestions.

    ``organizations`` maps the value to filter on (the slug) to its aliases;
    the value is what the model must return, the aliases only help it recognise
    what the user meant.

    ``template`` is the bot's own layout (CompanyBot.pre_context), so the wording
    can be reworded in admin without a deploy — the same way context holds the
    system prompt. USER_MESSAGE_TEMPLATE is the fallback when the column is
    empty. Only the prose is editable: the vocabulary blocks are always rendered
    here, from the data that actually exists.
    """
    values = {
        'query': raw_query,
        'organizations': _vocabulary_block(organizations, empty='  (none available)'),
        'file_types': _vocabulary_block(file_types),
        'candidates': _candidates_block(candidates),
    }
    layout = (template or '').strip() or USER_MESSAGE_TEMPLATE
    # safe_substitute, not substitute: an admin-edited template with a typo'd or
    # unknown $placeholder must degrade to literal text, never raise mid-search.
    return Template(layout).safe_substitute(values).strip()
