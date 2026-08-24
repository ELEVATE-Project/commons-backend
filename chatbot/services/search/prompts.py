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
  - Not recognizing an organization in the request at all is rule 3's omit \
case, not this one — return an empty list only for one of the phrasings \
above, never merely because you found no match. An organization name can \
appear with no "from"/"by" before it, directly modifying what follows, e.g. \
"csf reports" means organization ["csf"], not organizations omitted.
  - Before settling on an answer for organizations, check the organization \
list you were given one entry at a time against the query: does this value, \
its display name, or any of its aliases appear anywhere in the text — a \
bare mention, part of a longer clause, at the start of the sentence with no \
"from"/"by" before it, or a word that could also be read another way? If it \
does, it belongs in organizations or exclude_organizations; do not leave it \
out because the rest of the sentence was hard to parse or because the word \
had another possible reading. Do this for every organization in the list, \
not only the one that stands out at a glance.
  - That check runs in one direction only: it finds the listed entries the \
query names, and never turns a name the query contains into an entry it does \
not. So for each entry you are about to return — in organizations or in \
exclude_organizations, the test is the same — point at the words in the query \
that spell its value, its display name or one of its aliases, allowing \
differences of case, spacing, punctuation and obvious typos. Can you point at \
them? Return it, in whichever of the two lists rule 5 calls for. Cannot? Leave \
it out of both. A display name made of ordinary words is still that \
organization's name when the query spells it out. Match it as a whole phrase, \
however many words long it is and even where the value you return shares no \
letters with it: a display name that reads like a topic or a field of study is \
still that organization when the query spells its words out in order.
  - Generic words are not evidence: "Corporation", "Corp", "Company", \
"Foundation", "Trust", "Institute", "Org" and "Ltd" belong to no organization \
in particular, so a listed name ending in one is not matched by any other name \
ending in the same word. Neither are shared initials, a shared first letter or \
a shared opening syllable — two names can begin alike and be different \
companies. What has to be present is the distinctive part of the listed name, \
whole.
  - A query may name a company that is not listed here, and that needs no \
answer from you: the name stays in semantic_query, no organization filter is \
set, and the search still finds documents mentioning it. Never reach for the \
nearest entry, the only entry left, or any entry at all merely because the \
query clearly names some company — a wrong organization is worse than none, \
because it silently hides everything the user did want. Names are answered \
one at a time: matching one is no reason to match another, and failing to \
match one is no reason to drop the one you did match.
5. A value the user asks to leave out is an exclusion. Put it in \
exclude_organizations or exclude_file_types, never in organizations or \
file_types. Exclusion values come from the same lists and follow rules 1 and 2 \
just like positive ones. Words that signal an exclusion: "except", "excluding", \
"other than", "apart from", "besides", "not from", "without", "no", "not", \
"but not", "none of", "leave out", "omit".
  - A short "no X" or "not X" clause after a comma is an exclusion of X, not a \
second thing being asked for. Before putting any value in file_types or \
organizations, look at the word just before it: if that word is one of the \
signals above, the value belongs in the matching exclude_ field. A request may \
carry more than one exclusion, on different fields — finding one is no reason \
to stop looking for the next.
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
  - quantity words: "all", "every", "any", "a list of", "the list of", and the \
same words standing in for a noun: "everything", "anything", "something", \
"everything else", "all of them"
  - document words: "file", "files", "document", "documents", "doc", "docs", \
and other words meaning documents in general: "resource", "resources", \
"material", "materials", "content", "records", "items", "data"
  - file type names used to say what format of document to return: "PDF \
files", "the PDFs", a bare "pdf", and the same for the other listed types. A \
format word that is part of the subject instead stays in semantic_query — see \
rule 10
  - organization words: "organization", "organizations", "company", \
"companies", and any organization name
  - exclusion words: "except", "excluding", "other than", "apart from", \
"besides", "not from", "without", and whatever is being excluded
  - connector words: "or", "either", "and" — these join filter conditions, \
they never describe a topic
  - A phrase built only out of the words above is filler too: joining two of \
them does not make a topic. Ask of whatever you are about to keep: could a \
document be *about* this? If not, semantic_query is "".
7. When there is a genuine topic, semantic_query is that topic and nothing \
more. Keep it short and faithful to the user's words — usually what follows \
"about", "on", "regarding", or "related to". Whatever follows one of those \
markers is the topic, copied verbatim — take the user at their word even when \
the phrase reads as vague, and let rule 6 empty semantic_query only where the \
query has no such marker. Do not add words they did not use, \
and do not carry the words from rule 6 into it. A word naming a format is one \
of rule 6's words only when rule 10 says it is a filter; otherwise it stays in \
semantic_query exactly as the user wrote it.
8. Report the result by calling the apply_search_filters function. If function \
calling is not available to you, return the same fields as a single JSON object \
and nothing else: {"organizations": [...], "file_types": [...], \
"exclude_organizations": [...], "exclude_file_types": [...], \
"any_of": [...], "semantic_query": "..."}. Never answer in prose and never add \
explanation around the result.
9. any_of is for one thing only: an "or" that joins conditions on two \
different fields, like "PDF files from Shikshalokam, or DOC files from CSF". \
Each entry is a complete filter in its own right — the fields inside one entry \
are combined with AND, the entries are combined with OR, and nothing is \
inherited from the top-level fields or from another entry. Whatever you leave \
in the top-level fields still applies to every entry. Leave any_of out \
entirely unless the request needs it. In particular:
  - An "or" between values of the same field is one list, not two entries. \
"PDF or DOC files from Shikshalokam or CSF" is file_types with two values and \
organizations with two values, and no any_of.
  - A value that sits inside an entry goes there and nowhere else. Do not also \
copy it into the top-level organizations or file_types: those are ANDed with \
the alternatives, so they may hold only conditions that are true of every \
entry alike. Repeating an entry's values above narrows the search to their \
intersection and defeats the "or" you just built. When the alternatives carry \
the whole request, organizations and file_types are left empty.
  - Anything that is an exclusion under rule 5 stays an exclusion, however \
compound the sentence sounds. "all documents except PDF files from companies \
other than Shikshalokam" means every company except Shikshalokam, and nothing \
that is a PDF: exclude_organizations ["shikshalokam"] and exclude_file_types \
["application/pdf"], with no any_of.
  - Where an exclusion goes depends on what it applies to. One that narrows \
the whole request is a top-level exclude_ field, as above. But when the \
request already has alternatives and a "not"/"no"/"except" qualifies only one \
of them, it belongs inside that entry: at the top level it would drop the very \
documents the other alternative asked for. "documents from CSF that are not \
TXT, or anything from Involve" is two entries — {organizations ["csf"], \
exclude_file_types ["text/plain"]} and {organizations ["involve"]} — because \
Involve's text files were plainly asked for.
  - An entry does not need every field — it may filter on a single field \
only, and the two entries need not match each other's shape. "documents from \
Shikshalokam, or any DOCX file" is two one-field entries: one with only \
organizations, one with only file_types. Do not force both fields into a \
single entry just because the example above happens to show two.
  - Once any_of (or the fields above it) fully captures the request, \
semantic_query is "" — never repeat any part of the sentence there as a \
hedge in case the filters do not fully capture it. The "or" itself is a \
connector under rule 6, not a topic.
10. A file type name is a filter only when it says what format the returned \
documents should be in. The same word can instead name part of the subject, and \
then it is not a filter at all — decide which before filling in file_types. \
This applies to every listed type equally, PDF included: no format word is a \
filter by default, however often it is used as one.
  - It is a filter when it is the whole request, when it stands alone as the \
thing being asked for, when it directly modifies a document word ("PDF files", \
"docx documents", "the PDFs", "in PDF format", "as a spreadsheet"), or when it \
is what rule 5 excludes.
  - It is part of the topic when it modifies some other noun — something that \
is not the documents being requested, as in "CSV parsing", "spreadsheet \
modelling", "XLSX accessibility", "PDF encryption" — or when it sits inside \
what follows "about", "on", "regarding", "related to" or "covering".
  - A format word is also topical when it is what the subject is *about* \
rather than a description of the documents — the thing being converted, \
migrated, compared, opened or generated, as in "migrating from xls to xlsx" or \
"converting docx to pdf". Two format words joined by "to", "into", "versus" or \
"vs" are a subject, never two filters.
  - Deletion test: take out the format word together with the noun it \
modifies. If what is left still says which documents to return, the word was \
topical — leave it in semantic_query and set no file type filter. If taking it \
out leaves nothing to return, it was a format request — filter on it.
  - Subject test: could the phrase name something a document could be *about*? \
"CSV parsing" is such a subject; "CSV files" is not.
  - Both can happen in one query: filter on the occurrence that names the \
format and keep the other in semantic_query.
  - When it is genuinely unclear which one is meant, leave the word in \
semantic_query and omit the filter. A filter the user did not ask for hides \
documents they wanted; a slightly broader topic still finds them.
  - The file type list is closed, exactly as the organization list is. A format \
word the query names but that list does not contain — an unfamiliar extension, \
an invented one, or a short run of letters that merely resembles a listed value \
— gets no filter and stays in semantic_query. Never answer it with the listed \
type it looks most like; sharing letters or length identifies nothing.

Examples, assuming the organization list contains shikshalokam, csf and involve:

  "get list of all PDF files"
    -> file_types ["application/pdf"], organizations omitted, semantic_query ""
  "get the PDF from all organizations"
    -> file_types ["application/pdf"], organizations [], semantic_query ""
  "get all PDF files across organizations"
    -> file_types ["application/pdf"], organizations [], semantic_query ""
  "list all PDFs from the Shikshalokam organization"
    -> file_types ["application/pdf"], organizations ["shikshalokam"], \
semantic_query ""
  "csf reports that are not xlsx"
    -> organizations ["csf"], exclude_file_types \
["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"], \
semantic_query ""
  "find PDF files about teacher training"
    -> file_types ["application/pdf"], organizations omitted, semantic_query \
"teacher training"
  "find PDFs from Shikshalokam about teacher training"
    -> file_types ["application/pdf"], organizations ["shikshalokam"], \
semantic_query "teacher training"
  "notes on PDF encryption"
    -> file_types omitted, organizations omitted, semantic_query "PDF \
encryption" \
(a format word is topical or not on its own merits — being the most commonly \
requested format does not make this one a filter)
  "documents about CSV parsing"
    -> file_types omitted, organizations omitted, semantic_query "CSV parsing" \
(the format word modifies "parsing", not the documents being asked for)
  "guidelines on spreadsheet modelling"
    -> file_types omitted, organizations omitted, semantic_query "spreadsheet \
modelling"
  "PDF files about CSV parsing"
    -> file_types ["application/pdf"], semantic_query "CSV parsing" \
(one occurrence names the format, the other is part of the subject)
  "reports on XLSX accessibility from CSF"
    -> organizations ["csf"], file_types omitted, semantic_query "XLSX \
accessibility"
  "documents from Involute Systems" (not listed; only "involve" is)
    -> organizations omitted, semantic_query "Involute Systems" \
(beginning like a listed name is not being that name)
  "files from Redwood Foundation" (not listed)
    -> organizations omitted, semantic_query "Redwood Foundation" \
(a listed name also ending in "Foundation" is a different organization)
  "files from Involve and Northwind Corporation" (only Involve is listed)
    -> organizations ["involve"], semantic_query "Northwind Corporation" \
(each name is answered on its own: the listed one is a filter, the unlisted \
one is not turned into the nearest entry)
  "files from Northwind Corporation" (no such organization is listed)
    -> organizations omitted, file_types omitted, semantic_query "Northwind \
Corporation" \
(sharing the word "Corporation" with a listed name identifies nothing; an \
unlisted company means no organization filter, never the closest entry)
  "get all PDF files from all organizations except Shikshalokam"
    -> file_types ["application/pdf"], organizations [], \
exclude_organizations ["shikshalokam"], semantic_query ""
  "give me all doc/files except PDF"
    -> exclude_file_types ["application/pdf"], organizations omitted, \
semantic_query ""
  "find PDF files about teacher training except files from CSF"
    -> file_types ["application/pdf"], exclude_organizations ["csf"], \
semantic_query "teacher training"
  "all documents except PDF files from companies other than Shikshalokam"
    -> exclude_organizations ["shikshalokam"], exclude_file_types \
["application/pdf"], no any_of, semantic_query ""
  "get PDF files from Shikshalokam, or DOC files from CSF"
    -> any_of [{"file_types": ["application/pdf"], "organizations": \
["shikshalokam"]}, {"file_types": ["application/msword"], "organizations": \
["csf"]}], semantic_query ""
  "documents from Involve, or any CSV file"
    -> any_of [{"organizations": ["involve"]}, {"file_types": \
["text/csv"]}], semantic_query "" \
(each entry has only the one field it needs — do not merge them into one \
entry with both fields)
  "documents about budget planning from Involve, or any CSV file"
    -> any_of [{"organizations": ["involve"]}, {"file_types": \
["text/csv"]}], semantic_query "budget planning" \
(a genuine topic does not change how any_of is built — still two \
single-field entries, not one merged entry)
  "get PDF or DOC files from Shikshalokam or CSF"
    -> file_types ["application/pdf", "application/msword"], organizations \
["shikshalokam", "csf"], no any_of, semantic_query ""\
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

Return one of these organization values only if the query spells out that \
value, its display name or one of its aliases. The query may name a company \
that is not on this list: return no organization for that name, and leave it \
in semantic_query. Do not answer it with the closest entry on the list.

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
                                'organizations; never list every value instead. '
                                'Not recognizing an organization in the request is the '
                                'omit case, not the empty-list case — an organization '
                                'name can appear with no "from"/"by" before it, directly '
                                'modifying what follows. Check every listed organization '
                                'against the query one at a time before answering — do not '
                                'skip one just because it is not in the most obvious spot '
                                'or its name could also be read another way.'
                            ),
                            'items': {'type': 'string'},
                        },
                        'file_types': {
                            'type': 'array',
                            'description': (
                                'File type values from the supplied list. '
                                'Omit if the user did not ask to filter by file type. '
                                'Only fill this in when the user is asking for '
                                'documents in that format — the word stands alone, or '
                                'modifies a document word ("PDF files", "the PDFs"). A '
                                'format word that modifies something other than the '
                                'documents themselves ("CSV parsing", "spreadsheet '
                                'modelling") is part of the subject: omit this field '
                                'and leave the word in semantic_query. When it is '
                                'unclear which is meant, omit.'
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
                        'any_of': {
                            'type': 'array',
                            'description': (
                                'Alternatives, at least one of which must match. Use '
                                'ONLY for an "or" joining conditions on two different '
                                'fields ("PDFs from shikshalokam, or DOC files from '
                                'csf"). Each entry is complete on its own: its fields '
                                'are ANDed, entries are ORed, and nothing is inherited '
                                'from the fields above or from another entry — which '
                                'still apply to every entry, so a value placed in an '
                                'entry must NOT also be repeated in the top-level '
                                'organizations/file_types (that would AND it across '
                                'every alternative). An entry may filter on a '
                                'single field only ("shikshalokam, or any DOCX file" is '
                                'two one-field entries) — the OR still spans two '
                                'different fields. Once any_of captures the request, '
                                'semantic_query is "" — never duplicate the sentence '
                                'there as a hedge. Omit any_of for an "or" between '
                                'values of one field (use a longer list) and for '
                                'anything excluded (use exclude_organizations / '
                                'exclude_file_types), however compound the request '
                                'sounds.'
                            ),
                            'items': {
                                'type': 'object',
                                'properties': {
                                    'organizations': {
                                        'type': 'array',
                                        'items': {'type': 'string'},
                                    },
                                    'file_types': {
                                        'type': 'array',
                                        'items': {
                                            'type': 'string',
                                            'enum': [choice.value for choice in FileTypeChoices],
                                        },
                                    },
                                    'exclude_organizations': {
                                        'type': 'array',
                                        'items': {'type': 'string'},
                                    },
                                    'exclude_file_types': {
                                        'type': 'array',
                                        'items': {
                                            'type': 'string',
                                            'enum': [choice.value for choice in FileTypeChoices],
                                        },
                                    },
                                },
                            },
                        },
                        'semantic_query': {
                            'type': 'string',
                            'description': (
                                'The subject the user wants documents about, once '
                                'filter words are removed. Empty when the request '
                                'is only asking to list or filter documents. A format '
                                'word that names part of the subject belongs here, not '
                                'in file_types.'
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
