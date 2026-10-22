"""Regression coverage for cached name matching; no Redis or AI calls required."""
import os
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from chatbot.utils.theme_cache import (
    THEME_LIST_CACHE_KEY, get_theme_list, invalidate_theme_list_cache,
)
from chatbot.utils.theme_search import resolve_theme_names


@override_settings(
    REDIS_CACHE_ENABLED=True,
    THEME_CACHE_TTL=3600,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class ThemeSearchTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        cache.set(THEME_LIST_CACHE_KEY, {'count': 2, 'result': [
            {'name': 'Foundational Learning', 'code': 'private-code-one'},
            {'name': 'School Governance', 'code': 'private-code-two'},
        ]})
        self.env = patch.dict(os.environ, {
            'SEARCH_FILTER_THEME_CONFIDENCE_THRESHOLD': '90',
            'SEARCH_FILTER_NEGATION_WORDS': '["except","excluding","not"]',
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(cache.clear)

    def test_cached_names_are_used_without_database(self):
        with patch('chatbot.utils.theme_cache.apps.get_model') as model:
            names, excluded, remaining = resolve_theme_names('Foundational Learning')
        self.assertEqual(names, ['Foundational Learning'])
        self.assertEqual(excluded, [])
        self.assertEqual(remaining, '')
        model.assert_not_called()

    def test_codes_are_not_matched(self):
        self.assertEqual(resolve_theme_names('private-code-one'),
                         ([], [], 'private-code-one'))

    def test_typo_and_remaining_query(self):
        names, excluded, remaining = resolve_theme_names('foundatinal learning classroom activities')
        self.assertEqual(names, ['Foundational Learning'])
        self.assertEqual(excluded, [])
        self.assertIn('classroom activities', remaining)
        self.assertNotIn('foundatinal', remaining)

    def test_generic_fragment_is_not_a_theme(self):
        self.assertEqual(resolve_theme_names('learning'), ([], [], 'learning'))

    def test_multiple_names(self):
        names, _, _ = resolve_theme_names('Foundational Learning or School Governance')
        self.assertEqual(set(names), {'Foundational Learning', 'School Governance'})

    def test_excluded_name(self):
        names, excluded, _ = resolve_theme_names('activities except School Governance')
        self.assertEqual(names, [])
        self.assertEqual(excluded, ['School Governance'])

    def test_configured_threshold(self):
        with patch.dict(os.environ, {'SEARCH_FILTER_THEME_CONFIDENCE_THRESHOLD': '100'}):
            self.assertEqual(resolve_theme_names('foundatinal learning'),
                             ([], [], 'foundatinal learning'))

    def test_empty_cache_payload_is_a_hit(self):
        cache.set(THEME_LIST_CACHE_KEY, {'count': 0, 'result': []})
        with patch('chatbot.utils.theme_cache.apps.get_model') as model:
            self.assertEqual(resolve_theme_names('learning'), ([], [], 'learning'))
        model.assert_not_called()

    def test_invalidation(self):
        invalidate_theme_list_cache()
        self.assertIsNone(cache.get(THEME_LIST_CACHE_KEY))

    def test_cold_cache_hydrates_and_disabled_cache_is_bypassed(self):
        cache.clear()
        serializer = Mock(return_value=Mock(data=[{'name': 'New Theme'}]))
        with patch('chatbot.utils.theme_cache.apps.get_model'), patch(
            'chatbot.serializer.theme_serializer.ResourceThemeSerializer', serializer
        ):
            self.assertEqual(get_theme_list()['result'], [{'name': 'New Theme'}])
            get_theme_list()
            self.assertEqual(serializer.call_count, 1)
            with override_settings(REDIS_CACHE_ENABLED=False):
                get_theme_list()
                get_theme_list()
            self.assertEqual(serializer.call_count, 3)
