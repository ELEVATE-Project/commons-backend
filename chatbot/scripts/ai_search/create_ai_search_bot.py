#!/usr/bin/env python3
"""Seed the AI Search Filter bot and its prompt/tool configuration."""

import argparse
import os
import sys

if __name__ == '__main__' and not os.environ.get('DJANGO_SETTINGS_MODULE'):
    # Allow the script to run directly from the project root.
    sys.path.insert(0, os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', '..', '..')))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'shikshalokam_mohini.settings')
    import django
    django.setup()

from chatbot.models.company_models import Company, CompanyBot          # noqa: E402
from chatbot.models.enums import EntityStatus, LLMProvider             # noqa: E402
from chatbot.services.search.config import (                           # noqa: E402
    SETTINGS,
    bot_params,
    get_search_llm_setting,
)
from chatbot.services.search.prompts import (                          # noqa: E402
    LEGACY_SEARCH_BOT_ROUTE,
    SEARCH_BOT_ROUTE,
    SYSTEM_PROMPT,
    USER_MESSAGE_TEMPLATE,
    tool_context_json,
)

# Gateway config is seeded from the environment; existing admin values win.
GATEWAY_KEYS = (
    ('ai_provider', 'AI_SERVICE_PROVIDER'),
    ('ai_model', 'AI_SERVICE_MODEL'),
    ('ai_tenant_id', 'AI_SERVICE_TENANT_ID'),
)

DEFAULT_OWNER_SLUG = 'shikshalokamstaging'
FALLBACK_NAME = 'Search Bot'

CREATED = 'created'
UPDATED = 'updated'
UNCHANGED = 'unchanged'


def _owner(owner_slug, log):
    """Get or create the company used when creating a new bot."""
    company = Company.objects.filter(slug=owner_slug).first()
    if company is not None:
        return company

    company, _ = Company.objects.get_or_create(
        slug=owner_slug,
        defaults={'name': owner_slug, 'status': EntityStatus.ACTIVE},
    )
    log(f'Created owner company {owner_slug!r} for the search bot.')
    return company


def _name(log):
    """Return the name for a newly created bot."""
    name = (os.getenv('AI_SEARCH_BOT_NAME') or '').strip()
    if not name:
        log(
            f'AI_SEARCH_BOT_NAME is unset; naming the new row {FALLBACK_NAME!r}. '
            'Set the variable or rename it in admin.'
        )
    return name or FALLBACK_NAME


def _seed_params():
    """Return search settings using their currently effective values."""
    params = {
        key: get_search_llm_setting(None, key)
        for key in SETTINGS
    }

    for key, env_var in GATEWAY_KEYS:
        params[key] = (os.getenv(env_var) or '').strip()

    return params


def _merge_params(existing):
    """Add missing settings without changing existing admin values."""
    merged = dict(existing)

    for key, value in _seed_params().items():
        merged.setdefault(key, value)

    return merged


def create_ai_search_bot(owner_slug=DEFAULT_OWNER_SLUG, force=False, log=None):
    """Create or update the AI Search Filter bot."""
    log = log or (lambda message: None)

    # Never seed the legacy search bot.
    if SEARCH_BOT_ROUTE == LEGACY_SEARCH_BOT_ROUTE:
        raise ValueError(
            f'AI_SEARCH_BOT_ROUTE is set to {LEGACY_SEARCH_BOT_ROUTE!r}, '
            'the legacy search bot. Use a different route.'
        )

    # Use the same deterministic lookup as the search path.
    bot = (
        CompanyBot.objects
        .filter(route=SEARCH_BOT_ROUTE)
        .order_by('-updated_at', '-id')
        .first()
    )

    if bot is None:
        return CompanyBot.objects.create(
            name=_name(log),
            company=_owner(owner_slug, log),
            route=SEARCH_BOT_ROUTE,
            context=SYSTEM_PROMPT,
            pre_context=USER_MESSAGE_TEMPLATE,
            tool_context=tool_context_json(),
            other_params=_seed_params(),
            provider=LLMProvider.AI_SERVICE,
            bot_temperature=0.0,
            max_token=1024,
            connect_timeout=5.0,
            read_timeout=10.0,
        ), CREATED

    fields = []

    # Prompt and tool schema are code-managed; --force re-syncs them.
    if force or not bot.tool_context:
        bot.context = SYSTEM_PROMPT
        bot.tool_context = tool_context_json()
        bot.provider = LLMProvider.AI_SERVICE
        fields += ['context', 'tool_context', 'provider']

    # Seeded on its own condition so a row created before the template existed
    # gets one without --force rewriting its prompt as a side effect.
    if force or not bot.pre_context:
        bot.pre_context = USER_MESSAGE_TEMPLATE
        fields.append('pre_context')

    # Admin-configured values are preserved; only missing values are added.
    existing = bot_params(bot)
    merged = _merge_params(existing)

    if merged != existing:
        bot.other_params = merged
        fields.append('other_params')
        log(f'Added {len(merged) - len(existing)} default(s) to other_params.')

    if not fields:
        return bot, UNCHANGED

    bot.save(update_fields=fields + ['updated_at'])
    return bot, UPDATED


def build_parser(prog=None):
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        prog=prog,
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_arguments(parser)
    return parser


def add_arguments(parser):
    parser.add_argument(
        '--owner-slug',
        type=str,
        default=DEFAULT_OWNER_SLUG,
        help=f'Company used when creating a new bot (default: {DEFAULT_OWNER_SLUG}).',
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Re-seed context and tool_context; existing other_params values are preserved.',
    )
    return parser


def _gateway_target():
    """Return the configured AI Service provider and model."""
    provider = (os.getenv('AI_SERVICE_PROVIDER') or '').strip()
    model = (os.getenv('AI_SERVICE_MODEL') or '').strip()

    if provider and model:
        return f'{provider} {model}'

    return '<unset — set AI_SERVICE_PROVIDER and AI_SERVICE_MODEL>'


def describe(bot, action):
    """Return a short summary of the operation."""
    headline = {
        CREATED: f'Created search bot at {bot.route} (company: {bot.company.slug})',
        UPDATED: f'Seeded configuration at {bot.route}',
        UNCHANGED: (
            f'Search bot at {bot.route} is already seeded. '
            'Pass --force to re-seed.'
        ),
    }[action]

    detail = (
        f'  id={bot.id}  route={bot.route}  name={bot.name!r}  '
        f'company={bot.company.slug}  provider={bot.provider}  '
        f'gateway={_gateway_target()}'
    )

    return headline, detail


def main(argv=None):
    options = build_parser().parse_args(argv)

    try:
        bot, action = create_ai_search_bot(
            owner_slug=options.owner_slug,
            force=options.force,
            log=print,
        )
    except ValueError as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1

    for line in describe(bot, action):
        print(line)

    return 0


if __name__ == '__main__':
    sys.exit(main())