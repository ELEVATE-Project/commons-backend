import csv
import io
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

from chatbot.models import LLMProvider, SecondaryThemeMatchType
from chatbot.utils.database_util import is_document_indexed, update_single_file, upsert_single_file
from chatbot.utils.knowledge_service import theme_classification_service as service_module
from chatbot.constants.constants import SECONDARY_DESCRIPTION_MAX_CHARS
from chatbot.utils.knowledge_service.processor.theme_classifier import (
    ClassifiedTheme, DocumentMetadata, PartialMatchPolicy, SecondaryCandidate, SecondaryMatchValidator,
    SecondaryThemeGenerator, SecondaryThemeSettings, ThemeClassifier, ThemeOption, ThemeRules, describe_theme,
    is_token_variant
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
    SecondaryCandidate(code='Teacher_Capacity_Building', name='Teacher Capacity Building',
                       description='Training and coaching for teachers.'),
    SecondaryCandidate(code='Inclusive_Classroom_Practices', name='Inclusive Classroom Practices'),
    SecondaryCandidate(code='Phonics_Instruction', name='Phonics Instruction',
                       description='Teaching letter-sound relationships.'),
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
            {'code': code, 'confidence': confidence, 'reason': 'Shown in the summary.'}
            for code, confidence in (matches or [])
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

    def test_secondary_descriptions_keep_a_full_definition_and_are_capped(self):
        definition = ('Sign language use in classrooms so deaf and hard-of-hearing children can take part. ' * 7).strip()
        raw = [
            {'name': 'Sign Language Access', 'confidence': 0.8, 'description': definition[:600]},
            {'name': 'Hearing Support Devices', 'confidence': 0.8, 'description': definition + ' ' + definition},
        ]

        themes = self.rules.validate_new_secondary(raw, needed=2).themes

        self.assertEqual(themes[0].description, definition[:600].strip())
        self.assertEqual(len(themes[1].description), SECONDARY_DESCRIPTION_MAX_CHARS)
        self.assertTrue(themes[1].description.endswith('...'))

    def test_generator_bot_asks_for_a_definition_within_the_stored_limit(self):
        config = json.loads((SETUP_DIR / 'SecondaryThemeGeneratorBot.json').read_text())[0]
        schema = json.loads(config['tool_context'])['toolConfig']['tools'][0]['toolSpec']['inputSchema']['json']
        description = schema['properties']['new_secondary_themes']['items']['properties']['description']

        self.assertEqual(description['maxLength'], SECONDARY_DESCRIPTION_MAX_CHARS)
        self.assertIn('"Includes:"', config['context'])
        self.assertNotIn('"description": "<one sentence>"', config['end_context'])

    def test_token_variants(self):
        self.assertTrue(is_token_variant('Formative Assessment', 'Formative Assessment Strategies'))
        self.assertFalse(is_token_variant('Teacher Capacity Building', 'Teacher Capacity Development'))

    def test_logged_themes_show_their_code_or_name_until_one_exists(self):
        matched = ClassifiedTheme(name='Phonics Instruction', code='Phonics_Instruction', confidence=0.9, reasoning='')
        generated = ClassifiedTheme(name='Peer Learning Circles', confidence=0.8, reasoning='')

        self.assertEqual(describe_theme(matched), "'Phonics_Instruction'@0.90")
        self.assertEqual(describe_theme(generated), "'Peer Learning Circles'@0.80")


class SecondaryMatchValidatorTests(SimpleTestCase):

    def validate(self, raw, **settings):
        return SecondaryMatchValidator(CANDIDATES, SecondaryThemeSettings(**settings)).validate(raw)

    def test_codes_echoed_with_brackets_quotes_or_other_case_map_to_stored_themes(self):
        result = self.validate([
            {'code': 'Phonics_Instruction', 'confidence': 0.9, 'reason': 'Phonics drills.'},
            {'code': ' [teacher_capacity_building] ', 'confidence': 0.8, 'reason': 'Teacher trackers.'},
            {'code': ['Inclusive_Classroom_Practices'], 'confidence': 0.75, 'reason': 'Inclusion tips.'},
        ], count=3)

        self.assertTrue(result.is_valid)
        self.assertEqual([(theme.code, theme.name) for theme in result.themes],
                         [('Phonics_Instruction', 'Phonics Instruction'),
                          ('Teacher_Capacity_Building', 'Teacher Capacity Building'),
                          ('Inclusive_Classroom_Practices', 'Inclusive Classroom Practices')])

    def test_unknown_duplicate_and_low_confidence_codes_are_dropped_without_error(self):
        result = self.validate([
            {'code': 'Invented_Theme', 'confidence': 0.9},
            {'code': 'Phonics Instruction', 'confidence': 0.9},
            {'code': 13, 'confidence': 0.9},
            {'id': 'Phonics_Instruction', 'confidence': 0.9},
            {'code': 'Phonics_Instruction', 'confidence': 0.9},
            {'code': '"phonics_instruction"', 'confidence': 0.95},
            {'code': 'Inclusive_Classroom_Practices', 'confidence': 0.5},
        ])

        self.assertTrue(result.is_valid)
        self.assertEqual([theme.code for theme in result.themes], ['Phonics_Instruction'])
        self.assertEqual(len(result.rejected), 6)

    def test_matches_are_capped_by_count_keeping_highest_confidence(self):
        result = self.validate([
            {'code': 'Teacher_Capacity_Building', 'confidence': 0.75},
            {'code': 'Inclusive_Classroom_Practices', 'confidence': 0.95},
            {'code': 'Phonics_Instruction', 'confidence': 0.85},
        ], count=2)

        self.assertEqual([theme.code for theme in result.themes], ['Inclusive_Classroom_Practices', 'Phonics_Instruction'])

    def test_missing_field_means_no_match_and_wrong_type_is_an_error(self):
        self.assertTrue(self.validate(None).is_valid)
        self.assertFalse(self.validate('Phonics_Instruction, Teacher_Capacity_Building').is_valid)

    def test_no_candidates_ignores_any_codes(self):
        result = SecondaryMatchValidator([], SecondaryThemeSettings()).validate(
            [{'code': 'Teacher_Capacity_Building', 'confidence': 0.9}]
        )

        self.assertEqual(result.themes, [])
        self.assertTrue(result.is_valid)


class ThemeClassifierTests(SimpleTestCase):

    def build(self, responses, candidates=CANDIDATES, **overrides):
        invoke = MagicMock(side_effect=responses)
        bot = load_bot(**overrides)
        settings = SecondaryThemeSettings.from_params(bot.other_params)
        return ThemeClassifier(bot, THEMES, FALLBACK, invoke=invoke, candidates=candidates, settings=settings), invoke

    def test_primary_and_existing_secondary_matches_in_one_call(self):
        classifier, invoke = self.build([classify_call(matches=[('Phonics_Instruction', 0.9), ('Teacher_Capacity_Building', 0.8)])])

        result = classifier.classify(DOCUMENT)

        self.assertEqual(invoke.call_count, 1)
        self.assertEqual(result.primary.code, 'Foundational_Learning')
        self.assertEqual([theme.code for theme in result.matched_secondary], ['Phonics_Instruction', 'Teacher_Capacity_Building'])
        prompt = rendered_prompt(invoke)
        self.assertIn('[Teacher_Capacity_Building] Teacher Capacity Building - Training and coaching for teachers.',
                      prompt)
        self.assertIn('select by code only', prompt)
        self.assertIn('at most 2', prompt)
        self.assertEqual(tool_array_limit(invoke, 'matched_secondary_themes'), 2)

    def test_secondary_count_is_configurable(self):
        classifier, invoke = self.build([classify_call(matches=[('Phonics_Instruction', 0.9)])], secondary_theme_count=5)

        classifier.classify(DOCUMENT)

        self.assertIn('at most 5', rendered_prompt(invoke))
        self.assertEqual(tool_array_limit(invoke, 'matched_secondary_themes'), 5)

    def test_first_upload_without_candidates_tells_the_model_none_exist(self):
        classifier, invoke = self.build([classify_call(matches=[('Phonics_Instruction', 0.9)])], candidates=[])

        result = classifier.classify(DOCUMENT)

        self.assertIn('EXISTING SECONDARY THEMES: none', rendered_prompt(invoke))
        self.assertEqual(result.matched_secondary, [])

    def test_malformed_matches_are_retried_once(self):
        classifier, invoke = self.build([
            classify_call(raw_matches='13, 11'),
            classify_call(matches=[('Phonics_Instruction', 0.9)]),
        ])

        result = classifier.classify(DOCUMENT)

        self.assertEqual(invoke.call_count, 2)
        self.assertIn('must be a list', rendered_prompt(invoke))
        self.assertEqual([theme.code for theme in result.matched_secondary], ['Phonics_Instruction'])
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
            classify_call(primary='Unknown', matches=[('Phonics_Instruction', 0.9)]),
            classify_call(primary='Unknown', matches=[('Phonics_Instruction', 0.9)]),
        ])

        result = classifier.classify(DOCUMENT)

        self.assertEqual(invoke.call_count, 3)
        self.assertFalse(result.needs_review)
        self.assertEqual(result.primary.code, 'Foundational_Learning')
        self.assertEqual([theme.code for theme in result.matched_secondary], ['Phonics_Instruction'])

    def test_unknown_primary_is_retried_with_feedback(self):
        classifier, invoke = self.build([
            classify_call(primary='Teacher Wellbeing', matches=[('Phonics_Instruction', 0.9)]),
            classify_call(matches=[('Phonics_Instruction', 0.9)]),
        ])

        result = classifier.classify(DOCUMENT)

        self.assertEqual(invoke.call_count, 2)
        self.assertIn('Teacher Wellbeing', rendered_prompt(invoke))
        self.assertFalse(result.needs_review)

    def test_primary_failures_fall_back_to_miscellaneous_and_keep_valid_matches(self):
        classifier, _ = self.build([
            classify_call(primary='Unknown', matches=[('Phonics_Instruction', 0.9)]), None, RuntimeError('throttled'),
        ])

        result = classifier.classify(DOCUMENT)

        self.assertTrue(result.needs_review)
        self.assertEqual(result.primary.code, 'Miscellaneous')
        self.assertEqual([theme.code for theme in result.matched_secondary], ['Phonics_Instruction'])

    def test_llama_typed_value_wrappers_are_unwrapped(self):
        wrapped = {'input': {
            'primary_theme': {'type': 'object', 'value': {'name': 'Inclusion', 'confidence': 0.8, 'reasoning': 'x'}},
            'matched_secondary_themes': {'type': 'array', 'value': [{'code': 'Inclusive_Classroom_Practices', 'confidence': 0.9, 'reason': 'y'}]},
        }}
        classifier, _ = self.build([wrapped])

        result = classifier.classify(DOCUMENT)

        self.assertEqual(result.primary.code, 'Inclusion')
        self.assertEqual([theme.code for theme in result.matched_secondary], ['Inclusive_Classroom_Practices'])


class SecondaryThemeGeneratorTests(SimpleTestCase):

    PRIMARY = ClassifiedTheme(name='Foundational Learning', code='Foundational_Learning', confidence=0.9, reasoning='')
    MATCHED = [ClassifiedTheme(name='Phonics Instruction', confidence=0.9, reasoning='', code='Phonics_Instruction')]

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
        _, invoke, save = self.run_service([classify_call(matches=[('Phonics_Instruction', 0.9), ('Teacher_Capacity_Building', 0.8)])])

        self.assertEqual(invoke.call_count, 1)
        classification, generated, _ = save.call_args.args
        self.assertEqual([theme.code for theme in classification.matched_secondary], ['Phonics_Instruction', 'Teacher_Capacity_Building'])
        self.assertEqual(generated, [])

    def test_partial_match_generates_only_the_remaining_slots(self):
        _, invoke, save = self.run_service([
            classify_call(matches=[('Phonics_Instruction', 0.9)]),
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
        _, invoke, save = self.run_service([classify_call(matches=[('Phonics_Instruction', 0.9)])], classifier_bot=bot)

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
        _, invoke, save = self.run_service([classify_call(matches=[('Phonics_Instruction', 0.9)])], generator=False)

        self.assertEqual(invoke.call_count, 1)
        self.assertEqual(len(save.call_args.args[0].matched_secondary), 1)

    def test_vector_theme_sync_is_queued_when_enabled(self):
        self.run_service([classify_call(matches=[('Phonics_Instruction', 0.9), ('Teacher_Capacity_Building', 0.8)])],
                         classifier_bot=load_bot(vector_theme_sync_enabled=True))

        self.vector_sync.assert_called_once_with(42)

    def test_vector_theme_sync_is_on_by_default(self):
        bot = load_bot()
        bot.other_params.pop('vector_theme_sync_enabled', None)
        self.run_service([classify_call(matches=[('Phonics_Instruction', 0.9), ('Teacher_Capacity_Building', 0.8)])], classifier_bot=bot)

        self.vector_sync.assert_called_once_with(42)

    def test_bot_config_enables_vector_sync(self):
        self.run_service([classify_call(matches=[('Phonics_Instruction', 0.9)])])

        self.vector_sync.assert_called_once_with(42)

    def test_vector_theme_sync_can_be_disabled(self):
        self.run_service([classify_call(matches=[('Phonics_Instruction', 0.9), ('Teacher_Capacity_Building', 0.8)])],
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
            [classify_call(matches=[('Phonics_Instruction', 0.9)]), generate_call(['Reading Fluency Tracking'])], links=links
        )

        self.assertEqual(outcome.as_dict()['secondary_reuse'], {'matched': 1, 'deduplicated': 0, 'created': 1})
        self.assertEqual(outcome.secondary_themes, ('Phonics Instruction', 'Reading Fluency Tracking'))


class PrimaryThemeNameTests(SimpleTestCase):

    def test_classification_saves_the_primary_theme_name_with_its_code(self):
        media = SimpleNamespace(pk=42, id=42)
        media_model = MagicMock()
        media_model.objects.select_for_update.return_value.get.return_value = media
        classification = SimpleNamespace(
            primary=ClassifiedTheme(name='System Thinking', code='System_Thinking', confidence=0.9, reasoning='Why.'),
            matched_secondary=[], needs_review=False,
        )
        service = MediaThemeClassificationService(SimpleNamespace(id=42, pk=42, name='x'))
        with patch.object(service_module, 'transaction'), \
                patch.object(service_module, 'Media', media_model), \
                patch.object(service_module, 'MediaSecondaryTheme'), \
                patch.object(service_module, 'bulk_update_with_history') as bulk_update, \
                patch.object(MediaThemeClassificationService, '_resolve_links', return_value=[]):
            service.save_classification(classification, [], SecondaryThemeSettings())

        self.assertEqual((media.primary_theme_id, media.primary_theme_name), ('System_Thinking', 'System Thinking'))
        self.assertIn('primary_theme_name', bulk_update.call_args.args[2])

    def media_rows(self):
        media_model = MagicMock()
        return media_model, patch('chatbot.models.media_models.Media', media_model)

    def test_renaming_a_primary_theme_updates_its_media(self):
        from chatbot.models.theme_models import sync_media_primary_theme_name
        media_model, patched = self.media_rows()
        with patched:
            sync_media_primary_theme_name(None, SimpleNamespace(pk='System_Thinking', name='Systems Thinking',
                                                                is_primary=True))
            sync_media_primary_theme_name(None, SimpleNamespace(pk='Peer_Learning', name='Peer', is_primary=False))

        media_model.objects.filter.assert_called_once_with(primary_theme_id='System_Thinking')
        rows = media_model.objects.filter.return_value
        rows.exclude.assert_called_once_with(primary_theme_name='Systems Thinking')
        rows.exclude.return_value.update.assert_called_once_with(primary_theme_name='Systems Thinking')

    def test_deleting_a_theme_clears_the_name_on_its_media(self):
        from chatbot.models.theme_models import clear_media_primary_theme_name
        media_model, patched = self.media_rows()
        with patched:
            clear_media_primary_theme_name(None, SimpleNamespace(pk='Movement'))

        media_model.objects.filter.assert_called_once_with(primary_theme_id='Movement')
        media_model.objects.filter.return_value.update.assert_called_once_with(primary_theme_name=None)


class ResolveLinksTests(SimpleTestCase):

    def setUp(self):
        self.service = MediaThemeClassificationService(SimpleNamespace(id=42, name='x'))
        self.phonics = SimpleNamespace(pk='Phonics_Instruction', name='Phonics Instruction', is_primary=False,
                                       status='draft')
        self.teacher = SimpleNamespace(pk='Teacher_Capacity_Building', name='Teacher Capacity Building',
                                       is_primary=False, status='draft')

    def resolve(self, matched, generated, resolved, count=2):
        resource_theme = MagicMock()
        resource_theme.objects.in_bulk.return_value = {self.phonics.pk: self.phonics}
        with patch.object(service_module, 'ResourceTheme', resource_theme), \
                patch.object(service_module, 'acquire_secondary_theme_lock') as lock, \
                patch.object(service_module, 'resolve_generated_theme', side_effect=resolved):
            links = self.service._resolve_links(matched, generated, SecondaryThemeSettings(count=count))
        return links, lock

    def test_generated_name_resolving_to_an_already_linked_theme_is_not_linked_twice(self):
        matched = [ClassifiedTheme(name='Phonics Instruction', confidence=0.9, reasoning='',
                                   code='Phonics_Instruction')]
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
                         [('Phonics_Instruction', SecondaryThemeMatchType.MATCHED),
                          ('Teacher_Capacity_Building', SecondaryThemeMatchType.DEDUPLICATED)])

    def test_matches_only_never_take_the_creation_lock(self):
        matched = [ClassifiedTheme(name='Phonics Instruction', confidence=0.9, reasoning='',
                                   code='Phonics_Instruction')]

        links, lock = self.resolve(matched, [], [])

        lock.assert_not_called()
        self.assertEqual(len(links), 1)

    def test_matched_themes_are_looked_up_by_code(self):
        matched = [ClassifiedTheme(name='Phonics Instruction', confidence=0.9, reasoning='', code='Phonics_Instruction')]
        resource_theme = MagicMock()
        resource_theme.objects.in_bulk.return_value = {self.phonics.pk: self.phonics}
        with patch.object(service_module, 'ResourceTheme', resource_theme):
            links = self.service._resolve_links(matched, [], SecondaryThemeSettings(count=2))

        resource_theme.objects.in_bulk.assert_called_once_with(['Phonics_Instruction'])
        self.assertEqual([link.theme.pk for link in links], ['Phonics_Instruction'])

    def test_candidates_carry_their_code(self):
        rows = [SimpleNamespace(code='Peer_Learning_Circles', name='Peer Learning Circles', description='Peers.'),
                SimpleNamespace(code='Phonics_Instruction', name='Phonics Instruction', description='')]
        resource_theme = MagicMock()
        queryset = resource_theme.objects.filter.return_value.only.return_value
        queryset.count.return_value = len(rows)
        queryset.order_by.return_value = rows
        with patch.object(service_module, 'ResourceTheme', resource_theme):
            candidates, total = service_module.load_secondary_candidates(DOCUMENT, SecondaryThemeSettings())

        resource_theme.objects.filter.return_value.only.assert_called_once_with('code', 'name', 'description')
        self.assertEqual(total, 2)
        self.assertEqual([candidate.code for candidate in candidates], ['Peer_Learning_Circles', 'Phonics_Instruction'])


class VectorThemeSyncTests(SimpleTestCase):

    def setUp(self):
        self.media = SimpleNamespace(
            id=7, priority='P1', name='Child-Centered Education in Action', description='Pedagogy guide.',
            media_type='application/pdf', organization=SimpleNamespace(slug='shikshalokamstaging'),
            primary_theme_id='Teaching_Learning_Practises', company_bot=SimpleNamespace(provider='bedrock/converse'),
        )

    def test_retry_rules(self):
        self.assertEqual(decide_theme_sync(200), ThemeSyncDecision.DONE)
        self.assertEqual(decide_theme_sync(503), ThemeSyncDecision.RETRY)
        self.assertEqual(decide_theme_sync(429), ThemeSyncDecision.RETRY)
        self.assertEqual(decide_theme_sync(404), ThemeSyncDecision.FAIL)
        self.assertEqual(decide_theme_sync(400), ThemeSyncDecision.FAIL)

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

    def test_update_replaces_the_document_with_every_field(self):
        response = MagicMock(status_code=200, text='{"created_count": 18}')
        with patch('chatbot.utils.database_util.requests.request', return_value=response) as request:
            status, _ = update_single_file(7, 'guide.pdf', b'%PDF', {'source': 'file'}, self.media)

        self.assertEqual(status, 200)
        method, url = request.call_args.args
        self.assertEqual(method, 'PUT')
        self.assertTrue(url.endswith('/api/documents/7'))
        payload = request.call_args.kwargs['data']
        self.assertEqual(
            {key: payload[key] for key in ('title', 'summary', 'theme', 'priority', 'company_id')},
            {'title': 'Child-Centered Education in Action', 'summary': 'Pedagogy guide.',
             'theme': 'Teaching_Learning_Practises', 'priority': 'P1', 'company_id': 'shikshalokamstaging'},
        )
        self.assertEqual(request.call_args.kwargs['files'][0][1][:2], ('guide.pdf', b'%PDF'))
        self.assertIn('timeout', request.call_args.kwargs)

    def test_update_failures_are_reported_not_raised(self):
        with patch('chatbot.utils.database_util.requests.request',
                   side_effect=requests.exceptions.ConnectionError('refused')):
            status, _ = update_single_file(7, 'guide.pdf', b'%PDF', {}, self.media)
        self.assertEqual(decide_theme_sync(status), ThemeSyncDecision.RETRY)

        html = MagicMock(status_code=502, text='<html>Bad Gateway</html>')
        html.json.side_effect = ValueError('not json')
        with patch('chatbot.utils.database_util.requests.request', return_value=html):
            self.assertEqual(update_single_file(7, 'guide.pdf', b'%PDF', {}, self.media)[0], 502)

    def test_document_indexed_check(self):
        def verify(found, error=None):
            response = MagicMock()
            response.json.return_value = {'found': found}
            with patch('chatbot.utils.database_util.requests.post', return_value=response, side_effect=error):
                return is_document_indexed(7)

        self.assertTrue(verify(['7']))
        self.assertFalse(verify([]))
        self.assertIsNone(verify([], error=requests.exceptions.ConnectionError('refused')))

    def run_task(self, status=200, media=None, indexed=True, retries=0, error=None):
        media = media or self.media
        media_model = MagicMock()
        media_model.objects.select_related.return_value.filter.return_value.first.return_value = media
        sync_media_theme_to_vector_db.push_request(retries=retries)
        try:
            with patch('chatbot.models.media_models.Media', media_model), \
                    patch.object(media_tasks, 'is_document_indexed', return_value=indexed), \
                    patch.object(media_tasks, 'update_in_vector_db', return_value=status, side_effect=error) as update, \
                    patch.object(sync_media_theme_to_vector_db, 'retry', side_effect=RuntimeError('retry scheduled')):
                return sync_media_theme_to_vector_db.run(7), update
        finally:
            sync_media_theme_to_vector_db.pop_request()

    def test_task_updates_the_whole_document_with_update_in_vector_db(self):
        result, update = self.run_task(200)

        self.assertEqual(result, 200)
        update.assert_called_once_with(7, 'shikshalokamstaging')

    def test_task_waits_for_the_first_indexing_of_a_new_upload(self):
        with self.assertRaisesMessage(RuntimeError, 'retry scheduled'):
            self.run_task(indexed=False)

    def test_task_skips_a_document_still_missing_after_all_retries(self):
        result, update = self.run_task(indexed=False, retries=sync_media_theme_to_vector_db.max_retries)

        self.assertIsNone(result)
        update.assert_not_called()

    def test_task_updates_when_the_index_cannot_be_checked(self):
        result, update = self.run_task(200, indexed=None)

        self.assertEqual(result, 200)
        update.assert_called_once()

    def test_task_retries_server_errors_but_not_client_errors(self):
        with self.assertRaisesMessage(RuntimeError, 'retry scheduled'):
            self.run_task(503)
        self.assertEqual(self.run_task(400)[0], 400)

    def test_task_logs_and_stops_when_the_document_cannot_be_prepared(self):
        result, _ = self.run_task(error=AttributeError("'NoneType' object has no attribute 'slug'"))

        self.assertIsNone(result)

    def test_task_skips_media_indexed_in_openai(self):
        media = SimpleNamespace(**{**vars(self.media), 'company_bot': SimpleNamespace(provider=LLMProvider.OPENAI)})
        result, update = self.run_task(200, media=media)

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
        self.assertTrue(needs(self.form(changed=['file']), [], change=True))
        self.assertFalse(needs(self.form(changed=['primary_theme', 'file', 'description']), [], change=True))
        self.assertFalse(needs(self.form(changed=['display_mode', 'priority']), [], change=True))
        self.assertTrue(needs(self.form(), [self.formset('keyvalue', True)], change=True))
        self.assertFalse(needs(self.form(), [self.formset('image', True)], change=True))

    def test_save_queues_classification_with_the_shared_enqueue(self):
        request = SimpleNamespace()
        with patch('django.contrib.admin.ModelAdmin.save_related'), \
                patch('chatbot.admin.media_admin.enqueue_theme_classification', return_value='task-1') as enqueue:
            self.admin.save_related(request, self.form(), [], change=False)

        enqueue.assert_called_once_with(5, use_file_text=False)
        self.assertEqual(request.theme_classification, ('task-1', 'Guide'))

    def test_replaced_file_is_classified_from_its_own_text_unless_the_summary_was_edited(self):
        def use_file_text(changed, change=True):
            with patch('django.contrib.admin.ModelAdmin.save_related'), \
                    patch('chatbot.admin.media_admin.enqueue_theme_classification', return_value='t') as enqueue:
                self.admin.save_related(SimpleNamespace(), self.form(changed=changed), [], change=change)
            return enqueue.call_args.kwargs['use_file_text']

        self.assertTrue(use_file_text(['file']))
        self.assertTrue(use_file_text(['file', 'name', 'manual_tags']))
        self.assertFalse(use_file_text(['file', 'description']))
        self.assertFalse(use_file_text(['file', 'extracted_text']))
        self.assertFalse(use_file_text(['description']))
        self.assertFalse(use_file_text(['file'], change=False))

    def fieldset_fields(self, obj):
        with patch('chatbot.admin.media_admin.get_user_profile', return_value=None):
            fieldsets = self.admin.get_fieldsets(SimpleNamespace(user=None), obj)
        return [field for _, options in fieldsets for field in options['fields']]

    def test_primary_theme_is_editable_only_on_edit_of_top_level_media(self):
        def media(parent_id=None):
            tags = MagicMock()
            tags.filter.return_value.exists.return_value = False
            return SimpleNamespace(pk=5, parent_id=parent_id, tags=tags)

        self.assertIn('primary_theme', self.fieldset_fields(media()))
        self.assertNotIn('primary_theme', self.fieldset_fields(None))
        self.assertNotIn('primary_theme', self.fieldset_fields(media(parent_id=3)))

    def test_manual_primary_theme_replaces_the_classifier_verdict(self):
        def save(primary_theme_id, changed):
            obj = SimpleNamespace(
                primary_theme_id=primary_theme_id,
                primary_theme=SimpleNamespace(name='School Governance') if primary_theme_id else None,
                primary_theme_name='Teaching and Learning Practises', primary_theme_reasoning='Classifier reasoning.',
                needs_review=True, tags=MagicMock(),
            )
            with patch('simple_history.admin.SimpleHistoryAdmin.save_model') as save_model:
                self.admin.save_model(SimpleNamespace(), obj, self.form(changed=changed), change=True)
            save_model.assert_called_once()
            return obj

        manual = save('School_Governance', ['primary_theme'])
        self.assertEqual(manual.primary_theme_name, 'School Governance')
        self.assertIsNone(manual.primary_theme_reasoning)
        self.assertFalse(manual.needs_review)
        cleared = save(None, ['primary_theme'])
        self.assertIsNone(cleared.primary_theme_name)
        self.assertTrue(cleared.needs_review)

        untouched = save('School_Governance', ['description'])
        self.assertEqual(untouched.primary_theme_name, 'Teaching and Learning Practises')
        self.assertEqual(untouched.primary_theme_reasoning, 'Classifier reasoning.')
        self.assertTrue(untouched.needs_review)

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


class ResourceThemeAdminTests(SimpleTestCase):

    def setUp(self):
        from django.contrib import admin as django_admin
        from chatbot.admin.theme_admin import ResourceThemeAdmin
        from chatbot.models import ResourceTheme
        self.theme_admin = ResourceThemeAdmin(ResourceTheme, django_admin.site)

    def test_theme_type_filter_lists_primary_secondary_or_all(self):
        from chatbot.admin.theme_admin import ResourceThemeTypeFilter
        from chatbot.models import ResourceTheme

        def filtered(value):
            params = {'theme_type': [value]} if value else {}
            queryset = MagicMock()
            ResourceThemeTypeFilter(None, params, ResourceTheme, self.theme_admin).queryset(None, queryset)
            return queryset.filter

        filtered('primary').assert_called_once_with(is_primary=True)
        filtered('secondary').assert_called_once_with(is_primary=False)
        filtered('all').assert_not_called()
        filtered(None).assert_not_called()

    def test_export_requires_view_permission(self):
        from django.core.exceptions import PermissionDenied
        with patch.object(self.theme_admin, 'has_view_permission', return_value=False), \
                self.assertRaises(PermissionDenied):
            self.theme_admin.export_csv_view(SimpleNamespace(GET={}))

    def export_mapping(self, user, links):
        changelist_queryset = MagicMock()
        link_queryset = MagicMock()
        ordered = link_queryset.select_related.return_value.prefetch_related.return_value.order_by.return_value
        ordered.__iter__.side_effect = lambda: iter(links)
        ordered.filter.return_value.__iter__.side_effect = lambda: iter(links)
        ordered.none.return_value.__iter__.side_effect = lambda: iter([])
        secondary_theme = MagicMock()
        secondary_theme.objects.filter.return_value = link_queryset
        with patch.object(self.theme_admin, 'has_view_permission', return_value=True), \
                patch.object(self.theme_admin, 'get_changelist_instance',
                             return_value=SimpleNamespace(queryset=changelist_queryset)), \
                patch('chatbot.admin.theme_admin.MediaSecondaryTheme', secondary_theme), \
                patch('chatbot.admin.theme_admin.get_user_company', return_value=getattr(user, 'company', None)):
            response = self.theme_admin.export_csv_view(SimpleNamespace(GET={}, user=user))
        content = response.content.decode('utf-8')
        self.assertTrue(content.startswith('﻿'))
        changelist_queryset.filter.assert_called_once_with(is_primary=False)
        return response, list(csv.reader(io.StringIO(content[1:]))), ordered

    def mapping_link(self, media, theme_name, confidence):
        return SimpleNamespace(media=media, theme=SimpleNamespace(name=theme_name), confidence=confidence)

    def test_secondary_mapping_export_has_one_row_per_media_with_comma_separated_themes(self):
        guide = SimpleNamespace(id=990, name='testing11.pdf', title_values=[SimpleNamespace(value='Testing 11')],
                                primary_theme=SimpleNamespace(name='Foundational Learning'))
        untitled = SimpleNamespace(id=1012, name='=cmd', title_values=[], primary_theme=None)
        links = [self.mapping_link(guide, 'Playful Learning Environments', 0.8),
                 self.mapping_link(guide, 'Child Centred Approach', 0.7),
                 self.mapping_link(untitled, 'Peer Learning Circles', None)]
        superuser = SimpleNamespace(is_superuser=True, has_perm=lambda perm: True)

        response, rows, _ = self.export_mapping(superuser, links)

        self.assertRegex(response['Content-Disposition'], r'filename="secondary_theme_mapping_\d{8}\.csv"')
        self.assertEqual(rows, [
            ['Resource', 'Assigned Primary Theme', 'AI-Recommended Secondary Themes', 'AI Confidence Scores'],
            ['Testing 11', 'Foundational Learning', 'Playful Learning Environments, Child Centred Approach', '0.80, 0.70'],
            ["'=cmd", '', 'Peer Learning Circles', '-'],
        ])

    def test_secondary_mapping_export_is_limited_to_the_users_organization(self):
        company = SimpleNamespace(id=7)
        moderator = SimpleNamespace(is_superuser=False, has_perm=lambda perm: True, company=company)
        _, _, ordered = self.export_mapping(moderator, [])
        ordered.filter.assert_called_once_with(media__organization=company)

        no_company = SimpleNamespace(is_superuser=False, has_perm=lambda perm: True)
        _, rows, ordered = self.export_mapping(no_company, [])
        ordered.none.assert_called_once()
        self.assertEqual(rows, [['Resource', 'Assigned Primary Theme', 'AI-Recommended Secondary Themes',
                                 'AI Confidence Scores']])

    def test_secondary_mapping_export_requires_media_view_permission(self):
        from django.core.exceptions import PermissionDenied
        user = SimpleNamespace(is_superuser=False, has_perm=lambda perm: perm != 'chatbot.view_media')
        with patch.object(self.theme_admin, 'has_view_permission', return_value=True), \
                self.assertRaises(PermissionDenied):
            self.theme_admin.export_csv_view(SimpleNamespace(GET={}, user=user))

    def test_themes_cannot_be_added_from_the_admin(self):
        self.assertFalse(self.theme_admin.has_add_permission(SimpleNamespace(user=SimpleNamespace(is_superuser=True))))

    def test_code_and_description_are_read_only_on_edit_but_editable_on_add(self):
        theme_admin = self.theme_admin

        edit_fields = theme_admin.get_readonly_fields(None, SimpleNamespace(pk=4))
        self.assertIn('code', edit_fields)
        self.assertIn('description', edit_fields)
        self.assertNotIn('name', edit_fields)
        self.assertEqual(theme_admin.get_readonly_fields(None), ('created_at', 'updated_at'))


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

    def test_replaced_file_text_overrides_the_stale_description(self):
        invoke = MagicMock(side_effect=[classify_call(matches=[])])
        service = MediaThemeClassificationService(self.media, invoke=invoke, use_file_text=True)
        bots = {'/theme_classifier': load_bot()}
        with patch.object(service_module, 'build_document_metadata', return_value=DOCUMENT), \
                patch.object(service_module, 'extract_text_from_media_file',
                             return_value='School leadership and SMC planning handbook.') as read, \
                patch.object(service_module, 'get_company_bot', side_effect=lambda route, company: bots.get(route)), \
                patch.object(service_module, 'load_theme_options', return_value=(THEMES, FALLBACK)), \
                patch.object(service_module, 'load_secondary_candidates', return_value=([], 0)), \
                patch.object(MediaThemeClassificationService, 'save_classification', return_value=[]), \
                patch.object(service_module, 'queue_vector_theme_sync'):
            service.run()

        read.assert_called_once_with(self.media)
        prompt = rendered_prompt(invoke, 0)
        self.assertIn('School leadership and SMC planning handbook.', prompt)
        self.assertNotIn(DOCUMENT.summary, prompt)

    def test_file_replacement_flag_reaches_the_celery_task_and_service(self):
        from chatbot.celery_tasks.knowledge_service import theme_tasks
        from chatbot.models import Media
        with patch.object(service_module.transaction, 'on_commit', side_effect=lambda callback: callback()), \
                patch.object(theme_tasks.classify_media_themes, 'apply_async') as apply_async:
            task_id = service_module.enqueue_theme_classification(5, use_file_text=True)
        apply_async.assert_called_once_with(args=(5,), task_id=task_id, kwargs={'use_file_text': True})

        with patch.object(Media, 'objects') as objects, \
                patch.object(service_module, 'MediaThemeClassificationService') as service_class:
            objects.select_related.return_value.filter.return_value.first.return_value = self.media
            theme_tasks.classify_media_themes(5, use_file_text=True)
        service_class.assert_called_once_with(self.media, use_file_text=True)

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
