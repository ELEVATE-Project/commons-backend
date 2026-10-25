"""Populate ResourceTheme.icon from the SVG files shipped with the application.

Run from the repository root using the target environment's database settings:

    python -m chatbot.scripts.migrate_theme_icons --dry-run
    python -m chatbot.scripts.migrate_theme_icons

Existing icon values are replaced when they differ. Unmatched files/themes are
reported and left unchanged. Ambiguous mappings abort the entire operation.
Stored paths are application-relative, never machine-specific absolute paths.
"""
import argparse
import os
from pathlib import Path


PORTAL_DIR = Path(__file__).resolve().parents[1] / 'static' / 'portal'
ICON_PATH_PREFIX = '/chatbot/static/portal/'
# The seeded theme was named Movement; deployments may rename it to Network.
ICON_ALIASES = {
    'network': {'movement'},
    'miscellaneous': {'misscellaneous'},
    'misscellaneous': {'miscellaneous'},
}


def normalize(value):
    """Ignore case and separators while preserving all words in a name/code."""
    return ''.join(character for character in value.casefold() if character.isalnum())


def build_icon_mapping(themes, portal_dir=PORTAL_DIR):
    """Match exact normalized theme names/codes; never guess using fuzzy scores."""
    if not portal_dir.is_dir():
        raise ValueError(f'Icon directory does not exist: {portal_dir}')
    files = sorted(path for path in portal_dir.iterdir()
                   if path.is_file() and path.suffix.lower() == '.svg')
    if not files:
        raise ValueError(f'No SVG icons found in {portal_dir}')

    mapping = {}
    unmatched_files = []
    for path in files:
        keys = {normalize(path.stem)}
        keys.update(normalize(alias) for alias in ICON_ALIASES.get(path.stem, set()))
        matches = [theme for theme in themes
                   if normalize(theme.name) in keys or normalize(theme.code) in keys]
        if len(matches) > 1:
            codes = ', '.join(theme.code for theme in matches)
            raise ValueError(f'Ambiguous icon {path.name}: matches {codes}')
        if not matches:
            unmatched_files.append(path.name)
            continue
        theme = matches[0]
        if theme.pk in mapping:
            raise ValueError(f'Multiple icons match theme {theme.code}: '
                             f'{mapping[theme.pk]} and {path.name}')
        mapping[theme.pk] = ICON_PATH_PREFIX + path.name
    return mapping, unmatched_files


def run(dry_run=False):
    """Update the configured Django database atomically and expire cached icons."""
    from django.db import transaction
    from chatbot.models.theme_models import ResourceTheme
    from chatbot.utils.theme_cache import invalidate_theme_list_cache

    with transaction.atomic():
        queryset = ResourceTheme.objects.order_by('pk')
        if not dry_run:
            queryset = queryset.select_for_update()
        themes = list(queryset)
        mapping, unmatched_files = build_icon_mapping(themes)
        changed = []
        for theme in themes:
            target = mapping.get(theme.pk)
            if target is None:
                print(f'SKIP theme {theme.code!r} ({theme.name}): no matching icon')
            elif theme.icon != target:
                print(f'{"WOULD UPDATE" if dry_run else "UPDATE"} {theme.code!r}: '
                      f'{theme.icon!r} -> {target!r}')
                theme.icon = target
                changed.append(theme)
        for filename in unmatched_files:
            print(f'SKIP icon {filename!r}: no matching theme')
        if changed and not dry_run:
            ResourceTheme.objects.bulk_update(changed, ['icon'])
            transaction.on_commit(invalidate_theme_list_cache)

    print(f'{"Dry run" if dry_run else "Complete"}: '
          f'{len(changed)} {"would change" if dry_run else "updated"}, '
          f'{len(mapping) - len(changed)} already correct, '
          f'{len(themes) - len(mapping)} themes without icons, '
          f'{len(unmatched_files)} unmatched icons.')
    return len(changed)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dry-run', action='store_true',
                        help='Print proposed updates without writing to the database or cache.')
    args = parser.parse_args()
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'shikshalokam_mohini.settings')
    import django
    django.setup()
    try:
        run(dry_run=args.dry_run)
    except ValueError as exc:
        parser.exit(1, f'Icon migration aborted: {exc}\n')


if __name__ == '__main__':
    main()
