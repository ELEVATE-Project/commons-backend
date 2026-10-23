"""Shared Redis-backed payload for the themes API and media search."""
from django.apps import apps
from django.conf import settings
from django.core.cache import cache

from chatbot.constants.constants import PRIMARY_THEME_LIST_CACHE_KEY, THEME_LIST_CACHE_KEY


def invalidate_theme_list_cache():
    if settings.REDIS_CACHE_ENABLED:
        cache.delete_many([THEME_LIST_CACHE_KEY, PRIMARY_THEME_LIST_CACHE_KEY])


def get_theme_list(primary_only=False):
    cache_key = PRIMARY_THEME_LIST_CACHE_KEY if primary_only else THEME_LIST_CACHE_KEY
    if settings.REDIS_CACHE_ENABLED:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    from chatbot.serializer.theme_serializer import ResourceThemeSerializer

    model = apps.get_model('chatbot', 'ResourceTheme')
    themes = model.objects.order_by('id')
    if primary_only:
        themes = themes.filter(is_primary=True)
    result = ResourceThemeSerializer(themes, many=True).data
    payload = {'count': len(result), 'result': result}
    if settings.REDIS_CACHE_ENABLED:
        cache.set(cache_key, payload, settings.THEME_CACHE_TTL)
    return payload
