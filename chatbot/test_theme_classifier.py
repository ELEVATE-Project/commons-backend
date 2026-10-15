import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import requests
from django.test import SimpleTestCase

from chatbot.celery_tasks.knowledge_service import media_tasks
from chatbot.celery_tasks.knowledge_service.media_tasks import (
    ThemeSyncDecision, decide_theme_sync, sync_media_theme_to_vector_db
)

from chatbot.models import SecondaryThemeMatchType
from chatbot.utils.database_util import update_document_theme, upsert_single_file
from chatbot.utils.knowledge_service import theme_classification_service as service_module
from chatbot.utils.knowledge_service.processor.theme_classifier import (
    ClassifiedTheme, DocumentMetadata, PartialMatchPolicy, SecondaryCandidate, SecondaryMatchValidator,
    SecondaryThemeGenerator, SecondaryThemeSettings, ThemeClassifier, ThemeOption, ThemeRules, is_token_variant
)
from chatbot.utils.knowledge_service.theme_classification_service import (
    MediaThemeClassificationService, SecondaryThemeLink, ThemeClassificationStatus, _clean_summary, build_theme_code
)

SETUP_DIR = Path(__file__).resolve().parent.parent / 'setup'
EXTRACTOR_CONFIG_PATH = 'chatbot.utils.knowledge_service.base.extraction_config.parse_extractor_config'

THEMES = [
    ThemeOption(code='Child_Rights', name='Child Rights', description='Rights-based awareness and protection.'),
    ThemeOption(code='Community_Engagement', name='Community Engagement', description='Parents and community.'),
    ThemeOption(code='Foundational_Learning', name='Foundational Learning', description='Early literacy and numeracy.'),
    ThemeOption(code='Inclusion', name='Inclusion', description='Equitable access for all children.'),
    ThemeOption(code='Teaching_Learning_Practises', name='Teaching and Learning Practises',
                description='Classroom pedagogy.'),
]
FALLBACK = ThemeOption(code='Miscellaneous', name='Miscellaneous', description='Anything else.')

CANDIDATES = [
    SecondaryCandidate(id=11, name='Teacher Capacity Building', description='Training and coaching for teachers.'),
    SecondaryCandidate(id=12, name='Inclusive Classroom Practices'),
    SecondaryCandidate(id=13, name='Phonics Instruction', description='Teaching letter-sound relationships.'),
]

DOCUMENT = DocumentMetadata(
    title='Reading Fluency Toolkit',
    summary='A toolkit of phonics drills and reading-fluency trackers for grade 1-3 teachers.',
    tags=('Literacy', 'Phonics'),
    document_type='Toolkit',
    key_entities=('Pune',),
)


def load_bot(file_name='ThemeClassifierBot.json', bot_id=61, **overrides):
    config = json.loads((SETUP_DIR / file_name).read_text())[0]
    other_params = {**config['other_params'], **overrides}
    return SimpleNamespace(
        id=bot_id,
        context=config['context'],
        end_context=config['end_context'],
        tool_context=config['tool_context'],
        other_params=other_params,
        llm_model=config['llm_model'],
        bot_temperature=config['bot_temperature'],
        max_token=config['max_token'],
    )


def classify_call(primary='foundational learning', matches=None, raw_matches=None):
    payload = {'primary_theme': {'name': primary, 'confidence': 0.9, 'reasoning': 'Focuses on early reading.'}}
    if raw_matches is not None:
        payload['matched_secondary_themes'] = raw_matches
    else:
        payload['matched_secondary_themes'] = [
            {'id': theme_id, 'confidence': confidence, 'reason': 'Shown in the summary.'}
            for theme_id, confidence in (matches or [])
        ]
    return {'toolUseId': 'tooluse_1', 'name': 'theme_classification', 'input': payload}


def generate_call(names=None, raw=None):
    themes = raw if raw is not None else [
        {'name': name, 'description': f'{name} for classrooms.', 'confidence': 0.8, 'reason': 'In the summary.'}
        for name in (names or [])
    ]
    return {'toolUseId': 'tooluse_2', 'name': 'secondary_theme_generation', 'input': {'new_secondary_themes': themes}}


def rendered_prompt(invoke, call_index=-1):
    return invoke.call_args_list[call_index].kwargs['messages'][0]['content'][0]['text']


def tool_array_limit(invoke, property_name, call_index=-1):
    tools = invoke.call_args_list[call_index].kwargs['tools']
    schema = tools['toolConfig']['tools'][0]['toolSpec']['inputSchema']['json']['properties'][property_name]
    return schema['maxItems']


class SecondaryThemeSettingsTests(SimpleTestCase):

    def test_bot_config_defaults(self):
        settings = SecondaryThemeSettings.from_params(load_bot().other_params)

        self.assertEqual(settings.count, 2)
        self.assertEqual(settings.partial_match_policy, PartialMatchPolicy.EXISTING_PLUS_NEW)
        self.assertEqual(settings.candidate_statuses, ('draft', 'published'))
        self.assertEqual(settings.min_match_confidence, 0.7)

    def test_values_are_clamped_and_invalid_values_fall_back(self):
        settings = SecondaryThemeSettings.from_params({
            'secondary_theme_count': 50, 'secondary_min_match_confidence': 1.5,
            'secondary_partial_match_policy': 'unknown', 'secondary_candidate_limit': 'abc',
        })

        self.assertEqual(settings.count, 10)
        self.assertEqual(settings.min_match_confidence, 1.0)
        self.assertEqual(settings.partial_match_policy, PartialMatchPolicy.EXISTING_PLUS_NEW)
        self.assertEqual(settings.candidate_limit, 200)
        self.assertEqual(SecondaryThemeSettings.from_params({'secondary_theme_count': -3}).count, 0)

    def test_existing_plus_new_fills_remaining_slots(self):
        settings = SecondaryThemeSettings(count=5)

        self.assertEqual([settings.slots_to_generate(matched) for matched in (0, 2, 5, 6)], [5, 3, 0, 0])

    def test_existing_only_generates_only_when_nothing_matched(self):
        settings = SecondaryThemeSettings(count=2, partial_match_policy=PartialMatchPolicy.EXISTING_ONLY)

        self.assertEqual(settings.slots_to_generate(0), 2)
        self.assertEqual(settings.slots_to_generate(1), 0)

    def test_zero_count_disables_secondary_themes(self):
        self.assertEqual(SecondaryThemeSettings(count=0).slots_to_generate(0), 0)


class ThemeRulesTests(SimpleTestCase):

    def setUp(self):
        self.rules = ThemeRules(THEMES, FALLBACK)

    def test_primary_match_is_case_insensitive_and_maps_to_code(self):
        primary, errors = self.rules.validate_primary({'name': 'foundational learning', 'confidence': 0.9})

        self.assertEqual(errors, [])
        self.assertEqual(primary.code, 'Foundational_Learning')

    def test_fallback_is_a_valid_primary(self):
        primary, errors = self.rules.validate_primary({'name': 'MISCELLANEOUS', 'confidence': 0.6})

        self.assertEqual(errors, [])
        self.assertEqual(primary.code, 'Miscellaneous')

    def test_unknown_primary_is_rejected(self):
        primary, errors = self.rules.validate_primary({'name': 'Teacher Wellbeing', 'confidence': 0.9})

        self.assertIsNone(primary)
        self.assertIn('not a predefined theme', errors[0])

    def test_new_secondary_names_are_checked(self):
        raw = [
            {'name': 'Inclusion Practices', 'confidence': 0.8},
            {'name': 'Accessibility', 'confidence': 0.8},
            {'name': 'Sign Language Access', 'confidence': 0.8, 'description': 'Using sign language.'},
            {'name': 'sign  language access', 'confidence': 0.8},
        ]

        result = self.rules.validate_new_secondary(raw, needed=3)

        self.assertTrue(result.is_valid)
        self.assertEqual([theme.name for theme in result.themes], ['Sign Language Access'])
        self.assertEqual(result.themes[0].description, 'Using sign language.')
        self.assertEqual(len(result.rejected), 3)

    def test_token_variants(self):
        self.assertTrue(is_token_variant('Formative Assessment', 'Formative Assessment Strategies'))
        self.assertFalse(is_token_variant('Teacher Capacity Building', 'Teacher Capacity Development'))


class SecondaryMatchValidatorTests(SimpleTestCase):

    def validate(self, raw, **settings):
        return SecondaryMatchValidator(CANDIDATES, SecondaryThemeSettings(**settings)).validate(raw)

    def test_ids_in_any_common_format_map_to_stored_names(self):
        result = self.validate([
            {'id': 13, 'confidence': 0.9, 'reason': 'Phonics drills.'},
            {'id': '[11]', 'confidence': 0.8, 'reason': 'Teacher trackers.'},
        ])

        self.assertTrue(result.is_valid)
        self.assertEqual([(theme.theme_id, theme.name) for theme in result.themes],
                         [(13, 'Phonics Instruction'), (11, 'Teacher Capacity Building')])

    def test_unknown_duplicate_and_low_confidence_ids_are_dropped_without_error(self):
        result = self.validate([
            {'id': 99, 'confidence': 0.9},
            {'id': 13, 'confidence': 0.9},
            {'id': '13', 'confidence': 0.95},
            {'id': 12, 'confidence': 0.5},
        ])

        self.assertTrue(result.is_valid)
        self.assertEqual([theme.theme_id for theme in result.themes], [13])
        self.assertEqual(len(result.rejected), 3)

    def test_matches_are_capped_by_count_keeping_highest_confidence(self):
        result = self.validate([
            {'id': 11, 'confidence': 0.75}, {'id': 12, 'confidence': 0.95}, {'id': 13, 'confidence': 0.85},
        ], count=2)

        self.assertEqual([theme.theme_id for theme in result.themes], [12, 13])

    def test_missing_field_means_no_match_and_wrong_type_is_an_error(self):
        self.assertTrue(self.validate(None).is_valid)
        self.assertFalse(self.validate('11, 12').is_valid)

    def test_no_candidates_ignores_any_ids(self):
        result = SecondaryMatchValidator([], SecondaryThemeSettings()).validate([{'id': 11, 'confidence': 0.9}])

        self.assertEqual(result.themes, [])
        self.assertTrue(result.is_valid)


class ThemeClassifierTests(SimpleTestCase):

    def build(self, responses, candidates=CANDIDATES, **overrides):
        invoke = MagicMock(side_effect=responses)
        bot = load_bot(**overrides)
        settings = SecondaryThemeSettings.from_params(bot.other_params)
        return ThemeClassifier(bot, THEMES, FALLBACK, invoke=invoke, candidates=candidates, settings=settings), invoke

    def test_primary_and_existing_secondary_matches_in_one_call(self):
        classifier, invoke = self.build([classify_call(matches=[(13, 0.9), (11, 0.8)])])

        result = classifier.classify(DOCUMENT)

        self.assertEqual(invoke.call_count, 1)
        self.assertEqual(result.primary.code, 'Foundational_Learning')
        self.assertEqual([theme.theme_id for theme in result.matched_secondary], [13, 11])
        prompt = rendered_prompt(invoke)
        self.assertIn('[11] Teacher Capacity Building - Training and coaching for teachers.', prompt)
        self.assertIn('at most 2', prompt)
        self.assertEqual(tool_array_limit(invoke, 'matched_secondary_themes'), 2)

    def test_secondary_count_is_configurable(self):
        classifier, invoke = self.build([classify_call(matches=[(13, 0.9)])], secondary_theme_count=5)

        classifier.classify(DOCUMENT)

        self.assertIn('at most 5', rendered_prompt(invoke))
        self.assertEqual(tool_array_limit(invoke, 'matched_secondary_themes'), 5)

    def test_first_upload_without_candidates_tells_the_model_none_exist(self):
        classifier, invoke = self.build([classify_call(matches=[(13, 0.9)])], candidates=[])

        result = classifier.classify(DOCUMENT)

        self.assertIn('EXISTING SECONDARY THEMES: none', rendered_prompt(invoke))
        self.assertEqual(result.matched_secondary, [])

    def test_malformed_matches_are_retried_once(self):
        classifier, invoke = self.build([
            classify_call(raw_matches='13, 11'),
            classify_call(matches=[(13, 0.9)]),
        ])

        result = classifier.classify(DOCUMENT)

        self.assertEqual(invoke.call_count, 2)
        self.assertIn('must be a list', rendered_prompt(invoke))
        self.assertEqual([theme.theme_id for theme in result.matched_secondary], [13])
        self.assertFalse(result.needs_review)

    def test_malformed_matches_twice_keep_primary_and_fall_back_to_no_matches(self):
        classifier, invoke = self.build([classify_call(raw_matches='13'), classify_call(raw_matches='13')])

        result = classifier.classify(DOCUMENT)

        self.assertEqual(invoke.call_count, 2)
        self.assertFalse(result.needs_review)
        self.assertEqual(result.primary.code, 'Foundational_Learning')
        self.assertEqual(result.matched_secondary, [])

    def test_valid_primary_from_an_earlier_attempt_is_not_flagged_for_review(self):
        classifier, invoke = self.build([
            classify_call(raw_matches='13'),
            classify_call(primary='Unknown', matches=[(13, 0.9)]),
            classify_call(primary='Unknown', matches=[(13, 0.9)]),
        ])

        result = classifier.classify(DOCUMENT)

        self.assertEqual(invoke.call_count, 3)
        self.assertFalse(result.needs_review)
        self.assertEqual(result.primary.code, 'Foundational_Learning')
        self.assertEqual([theme.theme_id for theme in result.matched_secondary], [13])

    def test_unknown_primary_is_retried_with_feedback(self):
        classifier, invoke = self.build([
            classify_call(primary='Teacher Wellbeing', matches=[(13, 0.9)]),
            classify_call(matches=[(13, 0.9)]),
        ])

        result = classifier.classify(DOCUMENT)

        self.assertEqual(invoke.call_count, 2)
        self.assertIn('Teacher Wellbeing', rendered_prompt(invoke))
        self.assertFalse(result.needs_review)

    def test_primary_failures_fall_back_to_miscellaneous_and_keep_valid_matches(self):
        classifier, _ = self.build([
            classify_call(primary='Unknown', matches=[(13, 0.9)]), None, RuntimeError('throttled'),
        ])

        result = classifier.classify(DOCUMENT)

        self.assertTrue(result.needs_review)
        self.assertEqual(result.primary.code, 'Miscellaneous')
        self.assertEqual([theme.theme_id for theme in result.matched_secondary], [13])

    def test_llama_typed_value_wrappers_are_unwrapped(self):
        wrapped = {'input': {
            'primary_theme': {'type': 'object', 'value': {'name': 'Inclusion', 'confidence': 0.8, 'reasoning': 'x'}},
            'matched_secondary_themes': {'type': 'array', 'value': [{'id': 12, 'confidence': 0.9, 'reason': 'y'}]},
        }}
        classifier, _ = self.build([wrapped])

        result = classifier.classify(DOCUMENT)

        self.assertEqual(result.primary.code, 'Inclusion')
        self.assertEqual([theme.theme_id for theme in result.matched_secondary], [12])


class SecondaryThemeGeneratorTests(SimpleTestCase):

    PRIMARY = ClassifiedTheme(name='Foundational Learning', code='Foundational_Learning', confidence=0.9, reasoning='')
    MATCHED = [ClassifiedTheme(name='Phonics Instruction', confidence=0.9, reasoning='', theme_id=13)]

    def build(self, responses):
        invoke = MagicMock(side_effect=responses)
        bot = load_bot('SecondaryThemeGeneratorBot.json', bot_id=62)
        return SecondaryThemeGenerator(bot, THEMES, FALLBACK, invoke=invoke, retries=1), invoke

    def generate(self, generator, needed=1):
        existing_names = ['Phonics Instruction', 'Teacher Capacity Building']
        return generator.generate(DOCUMENT, self.PRIMARY, self.MATCHED, existing_names, needed)

    def test_generates_only_the_needed_number(self):
        generator, invoke = self.build([generate_call(['Reading Fluency Tracking', 'Peer Reading Circles'])])

        themes = self.generate(generator, needed=1)

        self.assertEqual([theme.name for theme in themes], ['Reading Fluency Tracking'])
        self.assertEqual(themes[0].description, 'Reading Fluency Tracking for classrooms.')
        self.assertEqual(tool_array_limit(invoke, 'new_secondary_themes'), 1)
        prompt = rendered_prompt(invoke)
        self.assertIn('Teacher Capacity Building', prompt)
        self.assertIn('THIS RESOURCE\'S PRIMARY THEME: Foundational Learning', prompt)

    def test_empty_list_is_a_valid_answer(self):
        generator, invoke = self.build([generate_call([])])

        self.assertEqual(self.generate(generator), [])
        self.assertEqual(invoke.call_count, 1)

    def test_names_that_repeat_matched_or_primary_themes_are_dropped(self):
        generator, _ = self.build([generate_call(['Phonics Instruction', 'Child Rights Advocacy'])])

        self.assertEqual(self.generate(generator, needed=2), [])

    def test_malformed_output_is_retried_once_then_gives_up(self):
        generator, invoke = self.build([generate_call(raw='Reading Fluency'), generate_call(raw='Reading Fluency')])

        self.assertEqual(self.generate(generator), [])
        self.assertEqual(invoke.call_count, 2)

    def test_nothing_needed_means_no_call(self):
        generator, invoke = self.build([])

        self.assertEqual(self.generate(generator, needed=0), [])
        invoke.assert_not_called()


class MediaThemeClassificationServiceTests(SimpleTestCase):

    def setUp(self):
        self.media = SimpleNamespace(
            id=42, name='Reading Fluency Toolkit', company_bot=SimpleNamespace(company=SimpleNamespace(id=1))
        )
        self.classifier_bot = load_bot()
        self.generator_bot = load_bot('SecondaryThemeGeneratorBot.json', bot_id=62)

    def bots(self, generator=True):
        routes = {'/theme_classifier': self.classifier_bot}
        if generator:
            routes['/secondary_theme_generator'] = self.generator_bot
        return lambda route, company: routes.get(route)

    def run_service(self, responses, candidates=CANDIDATES, generator=True, classifier_bot=None, links=()):
        if classifier_bot:
            self.classifier_bot = classifier_bot
        invoke = MagicMock(side_effect=responses)
        service = MediaThemeClassificationService(self.media, invoke=invoke)
        loaded_candidates = (list(candidates), len(candidates))
        with patch.object(service_module, 'build_document_metadata', return_value=DOCUMENT), \
                patch.object(service_module, 'get_company_bot', side_effect=self.bots(generator)), \
                patch.object(service_module, 'load_theme_options', return_value=(THEMES, FALLBACK)), \
                patch.object(service_module, 'load_secondary_candidates', return_value=loaded_candidates), \
                patch.object(MediaThemeClassificationService, 'save_classification',
                             return_value=list(links)) as save, \
                patch.object(service_module, 'queue_vector_theme_sync') as vector_sync:
            outcome = service.run()
        self.vector_sync = vector_sync
        return outcome, invoke, save

    def test_placeholder_description_is_treated_as_empty_summary(self):
        self.assertEqual(_clean_summary('Extracted from report.pdf'), '')
        self.assertEqual(_clean_summary('Real summary.'), 'Real summary.')

    def test_secondary_theme_code_is_derived_from_name(self):
        self.assertEqual(build_theme_code('reading fluency assessment'), 'Reading_Fluency_Assessment')
        self.assertEqual(build_theme_code('FLN  Tracking-Tools'), 'FLN_Tracking_Tools')
        self.assertEqual(build_theme_code('Évaluation Formative'), 'Evaluation_Formative')

    def test_non_latin_theme_codes_are_unique_and_stable(self):
        teacher_training = build_theme_code('शिक्षक प्रशिक्षण')
        child_rights = build_theme_code('बाल अधिकार जागरूकता')

        self.assertRegex(teacher_training, r'^Theme_[0-9a-f]{12}$')
        self.assertNotEqual(teacher_training, child_rights)
        self.assertEqual(teacher_training, build_theme_code('शिक्षक  प्रशिक्षण'))
        self.assertRegex(build_theme_code('शिक्षक Training'), r'^Training_[0-9a-f]{12}$')
        self.assertNotEqual(build_theme_code('शिक्षक Training'), build_theme_code('बाल Training'))

    def test_empty_extractor_output_skips_classification_and_flags_media(self):
        invoke = MagicMock()
        service = MediaThemeClassificationService(self.media, invoke=invoke)
        with patch.object(service_module, 'get_company_bot', side_effect=self.bots()), \
                patch.object(service_module, 'load_theme_options', return_value=(THEMES, FALLBACK)), \
                patch.object(service_module, 'build_document_metadata', return_value=DocumentMetadata()), \
                patch.object(service_module, 'extract_text_from_media_file', return_value=''), \
                patch.object(MediaThemeClassificationService, '_flag_for_review',
                             side_effect=lambda status: SimpleNamespace(status=status)) as flag:
            service.run()

        invoke.assert_not_called()
        flag.assert_called_once_with(ThemeClassificationStatus.SKIPPED_NO_SUMMARY)

    def test_full_match_reuses_existing_themes_without_generation(self):
        _, invoke, save = self.run_service([classify_call(matches=[(13, 0.9), (11, 0.8)])])

        self.assertEqual(invoke.call_count, 1)
        classification, generated, _ = save.call_args.args
        self.assertEqual([theme.theme_id for theme in classification.matched_secondary], [13, 11])
        self.assertEqual(generated, [])

    def test_partial_match_generates_only_the_remaining_slots(self):
        _, invoke, save = self.run_service([
            classify_call(matches=[(13, 0.9)]),
            generate_call(['Reading Fluency Tracking']),
        ])

        self.assertEqual(invoke.call_count, 2)
        self.assertEqual(tool_array_limit(invoke, 'new_secondary_themes'), 1)
        self.assertEqual([theme.name for theme in save.call_args.args[1]], ['Reading Fluency Tracking'])

    def test_first_upload_generates_all_slots(self):
        _, invoke, save = self.run_service(
            [classify_call(matches=[]), generate_call(['Reading Fluency Tracking', 'Peer Reading Circles'])],
            candidates=[],
        )

        self.assertEqual(tool_array_limit(invoke, 'new_secondary_themes'), 2)
        self.assertEqual(len(save.call_args.args[1]), 2)

    def test_existing_only_policy_skips_generation_after_any_match(self):
        bot = load_bot(secondary_partial_match_policy='existing_only')
        _, invoke, save = self.run_service([classify_call(matches=[(13, 0.9)])], classifier_bot=bot)

        self.assertEqual(invoke.call_count, 1)
        self.assertEqual(save.call_args.args[1], [])

    def test_missing_classifier_bot_flags_media_without_reading_the_file_or_calling_the_llm(self):
        invoke = MagicMock()
        service = MediaThemeClassificationService(self.media, invoke=invoke)
        with patch.object(service_module, 'get_company_bot', return_value=None), \
                patch.object(service_module, 'build_document_metadata') as metadata, \
                patch.object(service_module, 'extract_text_from_media_file') as read_file, \
                patch.object(MediaThemeClassificationService, '_flag_for_review',
                             side_effect=lambda status: SimpleNamespace(status=status)) as flag:
            outcome = service.run()

        flag.assert_called_once_with(ThemeClassificationStatus.SKIPPED_NO_BOT)
        self.assertEqual(outcome.status, ThemeClassificationStatus.SKIPPED_NO_BOT)
        metadata.assert_not_called()
        read_file.assert_not_called()
        invoke.assert_not_called()

    def test_missing_primary_themes_flags_media(self):
        service = MediaThemeClassificationService(self.media, invoke=MagicMock())
        with patch.object(service_module, 'get_company_bot', side_effect=self.bots()), \
                patch.object(service_module, 'load_theme_options', return_value=([], None)), \
                patch.object(MediaThemeClassificationService, '_flag_for_review',
                             side_effect=lambda status: SimpleNamespace(status=status)) as flag:
            service.run()

        flag.assert_called_once_with(ThemeClassificationStatus.SKIPPED_NO_THEMES)

    def test_missing_generator_bot_still_saves_matches(self):
        _, invoke, save = self.run_service([classify_call(matches=[(13, 0.9)])], generator=False)

        self.assertEqual(invoke.call_count, 1)
        self.assertEqual(len(save.call_args.args[0].matched_secondary), 1)

    def test_vector_theme_sync_is_queued_when_enabled(self):
        self.run_service([classify_call(matches=[(13, 0.9), (11, 0.8)])],
                         classifier_bot=load_bot(vector_theme_sync_enabled=True))

        self.vector_sync.assert_called_once_with(42)

    def test_vector_theme_sync_is_off_by_default(self):
        bot = load_bot()
        bot.other_params.pop('vector_theme_sync_enabled', None)
        self.run_service([classify_call(matches=[(13, 0.9), (11, 0.8)])], classifier_bot=bot)

        self.vector_sync.assert_not_called()

    def test_vector_theme_sync_can_be_disabled(self):
        self.run_service([classify_call(matches=[(13, 0.9), (11, 0.8)])],
                         classifier_bot=load_bot(vector_theme_sync_enabled='false'))

        self.vector_sync.assert_not_called()

    def test_outcome_reports_reuse_counts(self):
        links = [
            SecondaryThemeLink(
                SimpleNamespace(pk=13, name='Phonics Instruction'), SecondaryThemeMatchType.MATCHED, 0.9, ''
            ),
            SecondaryThemeLink(
                SimpleNamespace(pk=20, name='Reading Fluency Tracking'), SecondaryThemeMatchType.CREATED, 0.8, ''
            ),
        ]
        outcome, _, _ = self.run_service(
            [classify_call(matches=[(13, 0.9)]), generate_call(['Reading Fluency Tracking'])], links=links
        )

        self.assertEqual(outcome.as_dict()['secondary_reuse'], {'matched': 1, 'deduplicated': 0, 'created': 1})
        self.assertEqual(outcome.secondary_themes, ('Phonics Instruction', 'Reading Fluency Tracking'))


class ResolveLinksTests(SimpleTestCase):

    def setUp(self):
        self.service = MediaThemeClassificationService(SimpleNamespace(id=42, name='x'))
        self.phonics = SimpleNamespace(pk=13, name='Phonics Instruction', is_primary=False, status='draft')
        self.teacher = SimpleNamespace(pk=11, name='Teacher Capacity Building', is_primary=False, status='draft')

    def resolve(self, matched, generated, resolved, count=2):
        resource_theme = MagicMock()
        resource_theme.objects.in_bulk.return_value = {self.phonics.pk: self.phonics}
        with patch.object(service_module, 'ResourceTheme', resource_theme), \
                patch.object(service_module, 'acquire_secondary_theme_lock') as lock, \
                patch.object(service_module, 'resolve_generated_theme', side_effect=resolved):
            links = self.service._resolve_links(matched, generated, SecondaryThemeSettings(count=count))
        return links, lock

    def test_generated_name_resolving_to_an_already_linked_theme_is_not_linked_twice(self):
        matched = [ClassifiedTheme(name='Phonics Instruction', confidence=0.9, reasoning='', theme_id=13)]
        generated = [
            ClassifiedTheme(name='Phonics Teaching', confidence=0.8, reasoning=''),
            ClassifiedTheme(name='Teacher Coaching', confidence=0.8, reasoning=''),
        ]

        links, lock = self.resolve(matched, generated, [
            (self.phonics, SecondaryThemeMatchType.DEDUPLICATED, 'similar'),
            (self.teacher, SecondaryThemeMatchType.DEDUPLICATED, 'similar'),
        ])

        lock.assert_called_once()
        self.assertEqual([(link.theme.pk, link.match_type) for link in links],
                         [(13, SecondaryThemeMatchType.MATCHED), (11, SecondaryThemeMatchType.DEDUPLICATED)])

    def test_matches_only_never_take_the_creation_lock(self):
        matched = [ClassifiedTheme(name='Phonics Instruction', confidence=0.9, reasoning='', theme_id=13)]

        links, lock = self.resolve(matched, [], [])

        lock.assert_not_called()
        self.assertEqual(len(links), 1)


class VectorThemeSyncTests(SimpleTestCase):

    def setUp(self):
        self.media = SimpleNamespace(
            id=7, priority='P1', name='Child-Centered Education in Action', description='Pedagogy guide.',
            media_type='application/pdf', organization=SimpleNamespace(slug='shikshalokamstaging'),
            primary_theme_id='Teaching_Learning_Practises',
        )

    def test_retry_rules(self):
        self.assertEqual(decide_theme_sync(200, '{}'), ThemeSyncDecision.DONE)
        self.assertEqual(decide_theme_sync(404, '{"detail": "No documents found with source_id: 7"}'),
                         ThemeSyncDecision.RETRY)
        self.assertEqual(decide_theme_sync(503, 'Connection error'), ThemeSyncDecision.RETRY)
        self.assertEqual(decide_theme_sync(404, '{"detail": "Not Found"}'), ThemeSyncDecision.FAIL)
        self.assertEqual(decide_theme_sync(400, 'bad request'), ThemeSyncDecision.FAIL)

    def test_upsert_sends_theme_code_with_title_and_summary(self):
        response = MagicMock(status_code=201)
        response.json.return_value = {'ok': True}
        with patch('chatbot.utils.database_util.requests.request', return_value=response) as request:
            upsert_single_file('guide.pdf', b'%PDF', {'source': 'file'}, self.media)

        payload = request.call_args.kwargs['data']
        self.assertEqual(payload['theme'], 'Teaching_Learning_Practises')
        self.assertEqual(payload['title'], 'Child-Centered Education in Action')
        self.assertEqual(payload['summary'], 'Pedagogy guide.')

    def test_upsert_omits_theme_until_classified(self):
        self.media.primary_theme_id = None
        response = MagicMock(status_code=201)
        response.json.return_value = {}
        with patch('chatbot.utils.database_util.requests.request', return_value=response) as request:
            upsert_single_file('guide.pdf', b'%PDF', {}, self.media)

        self.assertNotIn('theme', request.call_args.kwargs['data'])

    def test_update_document_theme_request(self):
        with patch('chatbot.utils.database_util.requests.patch',
                   return_value=MagicMock(status_code=200, text='{"updated": 3}')) as request:
            status, _ = update_document_theme(7, 'Teaching_Learning_Practises', 'shikshalokamstaging')

        self.assertEqual(status, 200)
        self.assertTrue(request.call_args.args[0].endswith('/api/documents/7/theme'))
        self.assertEqual(request.call_args.kwargs['data'],
                         {'theme': 'Teaching_Learning_Practises', 'company_id': 'shikshalokamstaging'})

    def test_update_document_theme_connection_error_is_retryable(self):
        with patch('chatbot.utils.database_util.requests.patch',
                   side_effect=requests.exceptions.ConnectionError('refused')):
            status, _ = update_document_theme(7, 'Inclusion')

        self.assertEqual(decide_theme_sync(status, ''), ThemeSyncDecision.RETRY)

    def run_task(self, status, text, media=None):
        media_model = MagicMock()
        media_model.objects.select_related.return_value.filter.return_value.first.return_value = media or self.media
        with patch('chatbot.models.media_models.Media', media_model), \
                patch.object(media_tasks, 'update_document_theme', return_value=(status, text)) as update, \
                patch.object(sync_media_theme_to_vector_db, 'retry', side_effect=RuntimeError('retry scheduled')):
            return sync_media_theme_to_vector_db.run(7), update

    def test_task_syncs_theme_code(self):
        result, update = self.run_task(200, '{"updated": 3}')

        self.assertEqual(result, 200)
        update.assert_called_once_with(7, 'Teaching_Learning_Practises', 'shikshalokamstaging')

    def test_task_retries_when_document_not_indexed_yet(self):
        with self.assertRaisesMessage(RuntimeError, 'retry scheduled'):
            self.run_task(404, '{"detail": "No documents found with source_id: 7"}')

    def test_task_does_not_retry_when_endpoint_missing(self):
        result, _ = self.run_task(404, '{"detail": "Not Found"}')

        self.assertEqual(result, 404)

    def test_task_skips_unclassified_media(self):
        result, update = self.run_task(200, '', media=SimpleNamespace(primary_theme_id=None, organization=None))

        self.assertIsNone(result)
        update.assert_not_called()


class AddMediaThemeClassificationTests(SimpleTestCase):

    def setUp(self):
        from django.contrib import admin as django_admin
        from chatbot.admin.media_admin import MediaAdmin
        from chatbot.models.media_models import Media
        self.admin = MediaAdmin(Media, django_admin.site)

    def form(self, changed=(), parent_id=None):
        instance = SimpleNamespace(pk=5, name='Guide', parent_id=parent_id)
        return SimpleNamespace(instance=instance, changed_data=list(changed))

    def formset(self, model_name, changed):
        from chatbot.models.media_models import KeyValue, MediaImage
        model = {'keyvalue': KeyValue, 'image': MediaImage}[model_name]
        return SimpleNamespace(model=model, has_changed=lambda: changed)

    def test_new_media_is_always_classified(self):
        self.assertTrue(self.admin.needs_theme_classification(self.form(), [], change=False))

    def test_linked_documents_are_never_classified(self):
        self.assertFalse(self.admin.needs_theme_classification(self.form(parent_id=3), [], change=False))

    def test_edits_reclassify_only_when_classification_inputs_change(self):
        needs = self.admin.needs_theme_classification
        self.assertTrue(needs(self.form(changed=['description']), [], change=True))
        self.assertTrue(needs(self.form(changed=['manual_tags']), [], change=True))
        self.assertFalse(needs(self.form(changed=['display_mode', 'priority']), [], change=True))
        self.assertTrue(needs(self.form(), [self.formset('keyvalue', True)], change=True))
        self.assertFalse(needs(self.form(), [self.formset('image', True)], change=True))

    def test_save_queues_classification_with_the_shared_enqueue(self):
        request = SimpleNamespace()
        with patch('django.contrib.admin.ModelAdmin.save_related'), \
                patch('chatbot.admin.media_admin.enqueue_theme_classification', return_value='task-1') as enqueue:
            self.admin.save_related(request, self.form(), [], change=False)

        enqueue.assert_called_once_with(5)
        self.assertEqual(request.theme_classification, ('task-1', 'Guide'))

    def test_successful_save_waits_for_mapping_then_redirects_with_message(self):
        request = SimpleNamespace(theme_classification=('task-1', 'Guide'))
        response = SimpleNamespace(status_code=302)
        outcome = {
            'status': 'classified', 'primary_theme_name': 'Inclusion', 'secondary_themes': ['Sign Language Access'],
        }
        with patch('chatbot.admin.media_admin.wait_for_theme_classification', return_value=outcome) as wait, \
                patch.object(self.admin, 'message_user') as message_user:
            result = self.admin.wait_for_theme_mapping(request, response)

        self.assertIs(result, response)
        wait.assert_called_once()
        self.assertIn('primary Inclusion', message_user.call_args.args[1])

    def test_invalid_form_does_not_wait(self):
        request = SimpleNamespace(theme_classification=('task-1', 'Guide'))
        with patch('chatbot.admin.media_admin.wait_for_theme_classification') as wait:
            self.admin.wait_for_theme_mapping(request, SimpleNamespace(status_code=200))
            self.admin.wait_for_theme_mapping(SimpleNamespace(), SimpleNamespace(status_code=302))

        wait.assert_not_called()


class ThemeWaitAndMessageTests(SimpleTestCase):

    def async_result(self, ready_after, successful=True, result=None):
        polls = {'count': 0}

        def factory(task_id):
            polls['count'] += 1
            return SimpleNamespace(
                ready=lambda: polls['count'] >= ready_after,
                successful=lambda: successful,
                result=result,
            )
        return factory

    def test_returns_task_result_when_ready(self):
        with patch('celery.result.AsyncResult', side_effect=self.async_result(2, result={'status': 'classified'})), \
                patch.object(service_module.time, 'sleep'):
            self.assertEqual(service_module.wait_for_theme_classification('t', 5), {'status': 'classified'})

    def test_failed_task_is_reported_as_failed(self):
        with patch('celery.result.AsyncResult', side_effect=self.async_result(1, successful=False, result='boom')):
            outcome = service_module.wait_for_theme_classification('t', 5)

        self.assertEqual(outcome['status'], 'failed')

    def test_timeout_returns_none(self):
        with patch('celery.result.AsyncResult', side_effect=self.async_result(10 ** 9)), \
                patch.object(service_module.time, 'sleep'):
            self.assertIsNone(service_module.wait_for_theme_classification('t', 0.01))

    def test_messages(self):
        message = service_module.theme_outcome_message
        self.assertEqual(message('Guide', None)[0], 'info')
        needs_review = {'status': 'needs_review', 'primary_theme_name': 'Miscellaneous', 'secondary_themes': []}
        level, text = message('Guide', needs_review)
        self.assertEqual(level, 'warning')
        self.assertIn('flagged for review', text)
        self.assertEqual(message('Guide', {'status': 'skipped_no_summary'})[0], 'warning')
        self.assertEqual(message('Guide', {'status': 'failed'})[0], 'error')

    def test_extracted_text_is_used_when_description_is_empty(self):
        tags = MagicMock()
        tags.order_by.return_value.values_list.return_value = []
        media = SimpleNamespace(name='Guide', description='', extracted_text='Pasted text about phonics.', tags=tags)
        key_value = MagicMock()
        key_value.objects.filter.return_value.values_list.return_value = []
        with patch.object(service_module, 'KeyValue', key_value):
            document = service_module.build_document_metadata(media)

        self.assertEqual(document.summary, 'Pasted text about phonics.')


class FileTextFallbackTests(SimpleTestCase):

    def setUp(self):
        self.media = SimpleNamespace(
            id=991, name='Testing 12', company_bot_id=1,
            company_bot=SimpleNamespace(company=SimpleNamespace(id=1)),
        )

    def test_uses_text_read_from_the_file_when_there_is_no_summary(self):
        invoke = MagicMock(side_effect=[classify_call(matches=[])])
        service = MediaThemeClassificationService(self.media, invoke=invoke)
        bots = {'/theme_classifier': load_bot()}
        file_text = 'Child-centred pedagogy guide.'
        empty_document = DocumentMetadata(title='Testing 12')
        with patch.object(service_module, 'build_document_metadata', return_value=empty_document), \
                patch.object(service_module, 'extract_text_from_media_file', return_value=file_text) as read, \
                patch.object(service_module, 'get_company_bot', side_effect=lambda route, company: bots.get(route)), \
                patch.object(service_module, 'load_theme_options', return_value=(THEMES, FALLBACK)), \
                patch.object(service_module, 'load_secondary_candidates', return_value=([], 0)), \
                patch.object(MediaThemeClassificationService, 'save_classification', return_value=[]), \
                patch.object(service_module, 'queue_vector_theme_sync'):
            outcome = service.run()

        read.assert_called_once_with(self.media)
        self.assertEqual(outcome.status, ThemeClassificationStatus.CLASSIFIED)
        self.assertIn('Child-centred pedagogy guide.', rendered_prompt(invoke, 0))

    def test_flags_media_when_file_has_no_readable_text(self):
        service = MediaThemeClassificationService(self.media, invoke=MagicMock())
        with patch.object(service_module, 'get_company_bot', return_value=load_bot()), \
                patch.object(service_module, 'load_theme_options', return_value=(THEMES, FALLBACK)), \
                patch.object(service_module, 'build_document_metadata', return_value=DocumentMetadata(title='x')), \
                patch.object(service_module, 'extract_text_from_media_file', return_value=''), \
                patch.object(MediaThemeClassificationService, '_flag_for_review',
                             side_effect=lambda status: SimpleNamespace(status=status)) as flag:
            service.run()

        flag.assert_called_once_with(ThemeClassificationStatus.SKIPPED_NO_SUMMARY)

    def media_with_file(self, name):
        handle = MagicMock()
        handle.__enter__.return_value = 'file-handle'
        media_file = SimpleNamespace(name=name, open=MagicMock(return_value=handle))
        return SimpleNamespace(id=991, file=media_file, company_bot_id=1,
                               company_bot=SimpleNamespace(company=SimpleNamespace(id=1)))

    def test_reads_text_with_the_document_extractor(self):
        extractor = MagicMock()
        extractor.return_value.extract_text_from_file.return_value = ('  Guide text  ', [], '', 'pdf')
        with patch('chatbot.utils.knowledge_service.extractor.document_extractor.DocumentExtractor', extractor), \
                patch(EXTRACTOR_CONFIG_PATH, return_value={}), \
                patch.object(service_module, 'get_company_bot', return_value=None):
            text = service_module.extract_text_from_media_file(self.media_with_file('media/guide.PDF'))

        self.assertEqual(text, 'Guide text')
        extractor.return_value.extract_text_from_file.assert_called_once_with('file-handle', 'pdf')

    def test_unreadable_or_missing_files_return_empty_text(self):
        self.assertEqual(service_module.extract_text_from_media_file(SimpleNamespace(id=1, file=None)), '')
        self.assertEqual(service_module.extract_text_from_media_file(self.media_with_file('no_extension')), '')
        extractor = MagicMock(side_effect=RuntimeError('corrupt'))
        with patch('chatbot.utils.knowledge_service.extractor.document_extractor.DocumentExtractor', extractor), \
                patch(EXTRACTOR_CONFIG_PATH, return_value={}), \
                patch.object(service_module, 'get_company_bot', return_value=None):
            self.assertEqual(service_module.extract_text_from_media_file(self.media_with_file('bad.pdf')), '')
