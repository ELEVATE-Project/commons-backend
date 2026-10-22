"""Shared Redis-backed payload for the themes API and media search."""
from django.apps import apps
from django.conf import settings
from django.core.cache import cache

THEME_LIST_CACHE_KEY = 'resource_themes:list:v1'


def invalidate_theme_list_cache():
    if settings.REDIS_CACHE_ENABLED:
        cache.delete(THEME_LIST_CACHE_KEY)


def get_theme_list():
    if settings.REDIS_CACHE_ENABLED:
        cached = cache.get(THEME_LIST_CACHE_KEY)
        if cached is not None:
            return cached

    from chatbot.serializer.theme_serializer import ResourceThemeSerializer

    model = apps.get_model('chatbot', 'ResourceTheme')
    result = ResourceThemeSerializer(model.objects.order_by('id'), many=True).data
    payload = {'count': len(result), 'result': result}
    if settings.REDIS_CACHE_ENABLED:
        cache.set(THEME_LIST_CACHE_KEY, payload, settings.THEME_CACHE_TTL)
    return payload
