"""Regression coverage for merging natural-language and URL search filters."""
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory
from rest_framework.response import Response

from chatbot.services.search.filter_blocks import FilterBlock
from chatbot.services.search.llm_extractor import LLMFilterResult
from chatbot.utils.search_filter_resolver import resolve_query_exact
from chatbot.views.Media.media_api_views import FuzzyFilterResult, MediaSearchV2View

PDF = 'application/pdf'
DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
THEME = 'Community_Engagement'


class SearchFilterMergeTests(SimpleTestCase):
    def setUp(self):
        self.view = MediaSearchV2View()
        self.bot_patch = patch('chatbot.services.search.prompts.get_search_bot', return_value=None)
        self.bot_patch.start()
        self.addCleanup(self.bot_patch.stop)

    def resolve(self, fuzzy=None, explicit=None, mode='off', llm=None, branches=None):
        with patch('chatbot.services.search.config.get_search_llm_setting',
                   side_effect=lambda bot, key: mode if key == 'llm_mode' else 0.9), \
             patch('chatbot.services.search.llm_extractor.extract_search_filters', return_value=llm):
            return self.view._resolve_search_filters(
                'original query', fuzzy=fuzzy, explicit_filters=explicit,
                query_alternatives=branches,
            )

    def test_three_reported_requests_across_resolution_modes(self):
        for mode in ('off', 'fallback', 'always'):
            for extra in ({}, {'organizations': ['shikshalokamstaging']},
                          {'organizations': ['shikshalokamstaging'], 'themes': [THEME]}):
                with self.subTest(mode=mode, extra=extra):
                    result = self.resolve(
                        FuzzyFilterResult(media_types=[DOCX], themes=[THEME], query='', confidence=1),
                        {'media_types': [PDF], **extra}, mode,
                        LLMFilterResult(media_types=[DOCX], themes=[THEME]),
                    )
                    self.assertEqual(result.media_types, [DOCX, PDF])
                    self.assertEqual(result.themes, [THEME])
                    self.assertEqual(result.organizations, extra.get('organizations', []))
                    self.assertEqual(result.query, '')
                    self.assertEqual(result.diagnostics['media_types'], [DOCX, PDF])

    def test_all_fields_union_and_deduplicate(self):
        result = self.resolve(
            FuzzyFilterResult(organizations=['a'], media_types=[PDF], themes=['t1']),
            {'organizations': ['a', 'b', 'b'], 'media_types': [PDF, DOCX], 'themes': ['t2', 't1']},
        )
        self.assertEqual(result.organizations, ['a', 'b'])
        self.assertEqual(result.media_types, [PDF, DOCX])
        self.assertEqual(result.themes, ['t1', 't2'])

    def test_no_query_filters_and_no_url_filters(self):
        self.assertEqual(self.resolve(explicit={'media_types': [PDF]}).media_types, [PDF])
        self.assertEqual(self.resolve(FuzzyFilterResult(media_types=[DOCX])).media_types, [DOCX])
        self.assertEqual(self.resolve().media_types, [])

    def test_low_confidence_still_calls_llm_with_all_url_fields(self):
        result = self.resolve(
            FuzzyFilterResult(confidence=0),
            {'organizations': ['a'], 'media_types': [PDF], 'themes': ['t1']},
            'fallback', LLMFilterResult(media_types=[DOCX], themes=['t2']),
        )
        self.assertTrue(result.diagnostics['llm_used'])
        self.assertEqual(result.media_types, [DOCX, PDF])
        self.assertEqual(result.themes, ['t2', 't1'])

    def test_llm_failure_and_no_answer_keep_deterministic_merge(self):
        for failure in (False, True):
            with self.subTest(failure=failure), \
                 patch('chatbot.services.search.config.get_search_llm_setting',
                       side_effect=lambda bot, key: 'always' if key == 'llm_mode' else 0.9), \
                 patch.object(self.view, '_resolve_llm_filters',
                              side_effect=RuntimeError('unavailable') if failure else None), \
                 patch('chatbot.views.Media.media_api_views.logger.exception'):
                result = self.view._resolve_search_filters(
                    '', FuzzyFilterResult(media_types=[DOCX], query=''), {'media_types': [PDF]},
                )
                self.assertEqual(result.media_types, [DOCX, PDF])

    def test_llm_none_preserves_exact_and_empty_clears_query_values_only(self):
        for value, expected in ((None, [DOCX, PDF]), ([], [PDF])):
            with self.subTest(value=value):
                result = self.resolve(
                    FuzzyFilterResult(media_types=[DOCX]), {'media_types': [PDF]},
                    'always', LLMFilterResult(media_types=value),
                )
                self.assertEqual(result.media_types, expected)

    def test_exclusions_never_erase_positive_scope(self):
        for axis in ('media_types', 'organizations', 'themes'):
            with self.subTest(axis=axis):
                result = self.resolve(
                    FuzzyFilterResult(**{f'exclude_{axis}': ['x']}), {axis: ['x']},
                )
                self.assertEqual(getattr(result, axis), ['x'])
                self.assertEqual(getattr(result, f'exclude_{axis}'), ['x'])

    def test_alternatives_merge_without_cross_product_or_mutating_input(self):
        for mode in ('off', 'always'):
            branches = [FilterBlock(organizations=['a'], media_types=[PDF]),
                        FilterBlock(organizations=['b'], media_types=[DOCX])]
            with self.subTest(mode=mode):
                result = self.resolve(
                    FuzzyFilterResult(query='leadership'),
                    {'media_types': ['text/plain'], 'themes': [THEME]}, mode,
                    LLMFilterResult(any_of=branches, semantic_query='leadership'), branches,
                )
                self.assertEqual(result.media_types, [])
                self.assertEqual(result.themes, [])
                self.assertEqual(result.any_of[0].organizations, ['a'])
                self.assertEqual(result.any_of[1].organizations, ['b'])
                self.assertEqual(result.any_of[0].media_types, [PDF, 'text/plain'])
                self.assertEqual(result.any_of[1].media_types, [DOCX, 'text/plain'])
                self.assertTrue(all(b.themes == [THEME] for b in result.any_of))
                self.assertEqual(result.query, 'leadership')
                self.assertEqual(branches[0].media_types, [PDF])

    def test_global_constraints_and_branch_exclusions_survive(self):
        result = self.resolve(
            FuzzyFilterResult(themes=['t1'], exclude_organizations=['blocked']),
            {'themes': ['t2'], 'media_types': [PDF]},
            branches=[FilterBlock(organizations=['a'], exclude_media_types=[PDF]),
                      FilterBlock(organizations=['b'], media_types=[DOCX])],
        )
        self.assertEqual(result.themes, ['t1', 't2'])
        self.assertEqual(result.exclude_organizations, ['blocked'])
        self.assertEqual(result.any_of[0].media_types, [PDF])
        self.assertEqual(result.any_of[0].exclude_media_types, [PDF])

    def test_explicit_theme_does_not_suppress_query_theme_extraction(self):
        factory = APIRequestFactory()
        captured = {}

        def respond(**kwargs):
            captured.update(kwargs)
            return Response({})

        def resolve(query):
            return resolve_query_exact(query, organization_vocabulary={},
                                       file_type_vocabulary={DOCX: ['docx']},
                                       theme_vocabulary={THEME: ['community engagement']})

        with patch.object(MediaSearchV2View, '_resolve_query_filters', side_effect=resolve), \
             patch.object(MediaSearchV2View, '_get_vector_search_response', side_effect=respond):
            response = MediaSearchV2View.as_view()(factory.get('/api/v2/media/', {
                'q': 'fetch all docx files from community engagement',
                'theme': 'Other_Theme', 'media_types': PDF, 'limit': 6,
            }))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured['fuzzy'].themes, [THEME])
        self.assertEqual(captured['fuzzy'].media_types, [DOCX])
        self.assertEqual(captured['fuzzy'].query, '')
        self.assertEqual(captured['limit'], 6)

    def test_full_requests_reach_database_with_merged_filters_and_pagination(self):
        for theme in ('', THEME, 'Other_Theme'):
            with self.subTest(theme=theme), \
                 patch('chatbot.models.CompanyBot.objects.filter') as bots, \
                 patch('chatbot.services.search.config.get_search_llm_setting',
                       side_effect=lambda bot, key: 'off' if key == 'llm_mode' else 0.9), \
                 patch('chatbot.services.search.vocabularies.organization_vocabulary', return_value={}), \
                 patch('chatbot.services.search.vocabularies.theme_vocabulary',
                       return_value={THEME: ['community engagement']}), \
                 patch.object(MediaSearchV2View, '_get_database_list_response',
                              return_value=Response({})) as database:
                bots.return_value.first.return_value = None
                response = MediaSearchV2View.as_view()(APIRequestFactory().get('/api/v2/media/', {
                    'q': 'fetch all docx files from community engagement',
                    'media_types': PDF, 'organizations': 'shikshalokamstaging',
                    'theme': theme, 'limit': 6, 'offset': 12, 'ordering': '-created_at',
                }))
                self.assertEqual(response.status_code, 200)
                params = database.call_args.kwargs
                self.assertEqual(params['media_types'], [DOCX, PDF])
                self.assertEqual(params['themes'], [THEME] + (['Other_Theme'] if theme == 'Other_Theme' else []))
                self.assertEqual(params['organizations'], ['shikshalokamstaging'])
                self.assertEqual((params['limit'], params['offset'], params['ordering']), (6, 12, '-created_at'))

    def test_vector_payload_keeps_merged_alternative_themes(self):
        from rest_framework.request import Request
        self.view.request = Request(APIRequestFactory().get('/api/v2/media/', {
            'q': 'leadership', 'theme': 't2', 'media_types': PDF,
        }))
        with patch('chatbot.models.CompanyBot.objects.filter') as bots, \
             patch('chatbot.services.search.config.get_search_llm_setting',
                   side_effect=lambda bot, key: 'off' if key == 'llm_mode' else 0.9), \
             patch('chatbot.views.Media.media_api_views.query_database_with_metadata',
                   return_value={'error': True, 'status_code': 503}) as vector:
            bots.return_value.first.return_value = None
            self.view._get_vector_search_response(
                request=self.view.request, query='leadership', limit=6, offset=0,
                ordering='score', ordering_param='', tags=[], organizations=[],
                resource_types=[], media_types=[PDF], fuzzy=FuzzyFilterResult(query='leadership'),
                any_of=[FilterBlock(themes=['t1'], media_types=[DOCX]),
                        FilterBlock(themes=['t3'], media_types=['text/plain'])],
            )
            params = vector.call_args.kwargs
            self.assertEqual(params['query'], 'leadership')
            self.assertIsNone(params['themes'])
            self.assertIsNone(params['file_type'])
            self.assertEqual(params['any_of'][0]['themes'], ['t1', 't2'])
            self.assertEqual(params['any_of'][1]['themes'], ['t3', 't2'])
            self.assertIn(PDF, params['any_of'][0]['file_type'])
            self.assertIn(DOCX, params['any_of'][0]['file_type'])

    def test_database_compilation_keeps_contradictory_constraints(self):
        from django.db.models import F
        from chatbot.models.media_models import Media
        queryset = self.view._apply_database_filters(
            Media.objects.annotate(overridden_media_type=F('media_type')),
            tags=[], organizations=[], resource_types=[], media_types=[PDF],
            exclude_media_types=[PDF],
        )
        sql, params = queryset.query.sql_with_params()
        self.assertIn('NOT', sql)
        self.assertEqual(params.count(PDF), 2)
