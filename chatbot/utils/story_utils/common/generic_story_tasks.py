import logging
import json
import re
from chatbot.exceptions.story_exceptions import StoryDomainError, StorySaveError, StoryError
from chatbot.models import StoryStatusChoices, Story, Voice, VoiceType, StoryTranslation, Profile
from chatbot.models.geo_models import ProfileAddress
from chatbot.models.story_vernacular_model import StoryVernacular
from chatbot.utils.story_llama_utils import translate_field
from chatbot.utils.story_utils.format_utils import clean_escaped_text, get_formatted_story
from chatbot.utils.transliterate_utils import transliterate_text, get_transliteration_output

logger = logging.getLogger('django')


def is_english_text(text):
    """Check if text contains only English characters (a-z, A-Z, numbers, punctuation, spaces)"""
    if not text or str(text).strip() == '':
        logger.info(f"[ENGLISH CHECK] Received empty or blank text. Treating as English. text='{text}'")
        return True

    original_text = str(text)
    logger.info(f"[ENGLISH CHECK] Starting English validation. text='{original_text}'")

    # Remove common punctuation and numbers
    cleaned_text = re.sub(
        r'[0-9\s\.,\!\?\-\(\)\[\]\{\}\"\'\:\;\@\#\$\%\^\&\*\+\=\_\|\\\/<>~`]',
        '',
        original_text
    )
    logger.info(f"[ENGLISH CHECK] Cleaned text after removing numbers & punctuation: '{cleaned_text}'")

    is_english = bool(re.match(r'^[a-zA-Z]*$', cleaned_text))

    if is_english:
        logger.info(f"[ENGLISH CHECK] Text identified as English. text='{original_text}', cleaned='{cleaned_text}'")
    else:
        logger.info(f"[ENGLISH CHECK] Non-English characters detected. text='{original_text}', cleaned='{cleaned_text}'")

    return is_english


def translate_to_english_if_needed(text, voice_provider, source_language):
    """Translate text to English if it's not already in English"""
    if not text or text.strip() == '':
        logger.info(f"No need to translate. The data {text} is empty.")
        return text

    if is_english_text(text):
        logger.info(f"No need to translate. The data {text} is already in english.")
        return text

    try:
        if voice_provider:
            translated = translate_field(
                voice_provider=voice_provider,
                message_body=text,
                target_language='en',
                source_language=source_language
            )
            logger.info(f"Translated data to english: {translated}.")
            return translated
        else:
            logger.info(f"No voice provider available for translation. Keeping original text: {text}")
            return text
    except Exception as e:
        logger.error(f"Error translating to English: {e}")
        return text


def transliterate_to_english_if_needed(text, voice_provider, source_language):
    """Transliterate text to English if it's not already in English"""
    if not text or text.strip() == '':
        logger.info(f"No need to transliterate. The data {text} is empty.")
        return text

    if is_english_text(text):
        logger.info(f"No need to transliterate. The data {text} is already in english.")
        return text

    try:
        if voice_provider:
            is_sentence = ' ' in text
            transliterated = transliterate_text(
                voice_provider=voice_provider,
                message_body=text,
                target_language='en',
                source_language=source_language,
                is_sentence=is_sentence
            )
            logger.info(f"Transliterated data to english: {transliterated}.")
            return get_transliteration_output(data=transliterated)
        else:
            logger.info(f"No voice provider available for transliteration. Keeping original text: {text}")
            return text
    except Exception as e:
        logger.error(f"Error transliterating to English: {e}")
        return text


def translate_nested_to_english(data, voice_provider, transliteration_voice_provider, source_language, field_path=""):
    if isinstance(data, dict):
        translated_dict = {}
        for key, value in data.items():
            current_path = f"{field_path}.{key}" if field_path else key
            logger.info(f"DEBUG: Processing {key} = '{value}' (type: {type(value)})")

            if isinstance(value, str) and value.strip():
                personal_info_fields = ['name', 'user_name', 'location', 'organization', 'designation', 'district',
                                        'block']
                if key.lower() in personal_info_fields or any(field in key.lower() for field in personal_info_fields):
                    translated_dict[key] = transliterate_to_english_if_needed(value, transliteration_voice_provider,
                                                                              source_language)
                else:
                    translated_dict[key] = translate_to_english_if_needed(value, voice_provider, source_language)
            elif isinstance(value, (dict, list)):
                translated_dict[key] = translate_nested_to_english(value, voice_provider,
                                                                   transliteration_voice_provider, source_language,
                                                                   current_path)
            else:
                translated_dict[key] = value
        return translated_dict
    elif isinstance(data, list):
        translated_list = []
        for i, item in enumerate(data):
            if isinstance(item, str) and item.strip():
                translated_list.append(translate_to_english_if_needed(item, voice_provider, source_language))
            elif isinstance(item, (dict, list)):
                translated_list.append(
                    translate_nested_to_english(item, voice_provider, transliteration_voice_provider, source_language,
                                                f"{field_path}[{i}]"))
            else:
                translated_list.append(item)
        return translated_list
    else:
        return data


def save_generic_story(
        response_json_story, language, voice_provider, profile, session, combined_reason, flow=None, project_id=None,
        company_bot=None, exclude_fields=None
):
    try:
        import copy
        if exclude_fields is None:
            exclude_fields = []
        exclude_fields_set = set(exclude_fields) if exclude_fields else set()

        translation_voice_provider = voice_provider
        transliteration_voice_provider = None

        if company_bot and language != 'en':
            transliteration_voice_provider = Voice.objects.filter(
                company_bot=company_bot, type=VoiceType.Transliterate, language=language
            ).first()

        if isinstance(response_json_story, str):
            try:
                response_json_story = json.loads(response_json_story)
            except json.JSONDecodeError:
                raise StorySaveError()

        if not isinstance(response_json_story, dict):
            raise StorySaveError()

        print("For saving response_json_story: ", response_json_story)

        def parse_json_strings(data):
            if isinstance(data, dict):
                parsed_data = {}
                for key, value in data.items():
                    if isinstance(value, str) and value.strip():
                        stripped_value = value.strip()
                        if ((stripped_value.startswith('[') and stripped_value.endswith(']')) or
                                (stripped_value.startswith('{') and stripped_value.endswith('}'))):
                            try:
                                parsed_data[key] = json.loads(stripped_value)
                            except json.JSONDecodeError:
                                parsed_data[key] = value
                        else:
                            parsed_data[key] = value
                    else:
                        parsed_data[key] = parse_json_strings(value) if isinstance(value, (dict, list)) else value
                return parsed_data
            elif isinstance(data, list):
                return [parse_json_strings(item) for item in data]
            else:
                return data

        response_json_story = parse_json_strings(response_json_story)

        story = Story.objects.filter(session=session).first()

        is_within_domain = response_json_story.get('is_within_domain', True)

        if not is_within_domain:
            raise StoryDomainError()

        if story and story.other_params:
            other_params = copy.deepcopy(story.other_params)
            other_params.pop('_english_snapshot', None)
        else:
            other_params = {}

        previous_english_snapshot = {k: v for k, v in other_params.items()}

        user_name = None
        if isinstance(profile, Profile):
            user_name = profile.first_name if profile and profile.first_name else ''

        elif isinstance(profile, dict):
            user_name = profile.get("first_name", "") if profile and profile.get("first_name") else ''

        fallback_location = ""

        if isinstance(profile, Profile):
            address = ProfileAddress.objects.filter(profile=profile).first()
            if address:
                location_parts = filter(None, [address.block, address.district, address.state])
                fallback_location = ", ".join(location_parts)
        elif isinstance(profile, dict):
            address = profile.get("profile_address", [])
            if len(address) > 0:
                location_parts = filter(None, [address[0].get("block"), address[0].get("district"), address[0].get("state")])
                fallback_location = ", ".join(location_parts)

        other_params['flow'] = flow

        if 'user_name' not in exclude_fields_set:
            other_params['user_name'] = user_name

        STORY_MODEL_FIELDS = {
            'title', 'content', 'tweet', 'objective', 'action_steps',
            'impact', 'micro_improvement', 'blurb', 'language', 'stage',
            'other_params', 'location', 'validation_logs'
        }

        NON_TRANSLATABLE_FIELDS = {'flow', 'id', 'uuid', 'status', 'type', 'mode', 'version'}
        PERSONAL_INFO_FIELDS = {'name', 'user_name', 'location', 'organization', 'designation', 'district', 'block'}

        for key, value in response_json_story.items():
            if key in exclude_fields_set:
                continue
            if key not in STORY_MODEL_FIELDS:
                if isinstance(value, dict) or isinstance(value, list):
                    other_params[key] = translate_nested_to_english(
                        value, translation_voice_provider, transliteration_voice_provider, language, key
                    )
                elif isinstance(value, str) and value.strip():
                    if key.lower() in NON_TRANSLATABLE_FIELDS:
                        other_params[key] = value
                    elif key.lower() in PERSONAL_INFO_FIELDS:
                        other_params[key] = transliterate_to_english_if_needed(value, transliteration_voice_provider,
                                                                               language)
                    else:
                        other_params[key] = translate_to_english_if_needed(value, translation_voice_provider, language)
                else:
                    other_params[key] = value

        print(f"Story other_params before save: {other_params}")

        story_fields_to_update = {}
        english_title=None
        if 'title' not in exclude_fields_set:
            print("Title not in excluded set")
            if 'title' in response_json_story:
                raw_title = response_json_story.get('title', '')
                print("Raw title: ", raw_title)
                english_title = clean_escaped_text(
                    text=translate_to_english_if_needed(raw_title, translation_voice_provider, language)
                )
            print("english_title: ", english_title)
            if not english_title and company_bot:
                print("trying to get from story vernacular")
                try:
                    story_vernacular = StoryVernacular.objects.filter(
                        company_bot=company_bot, language='en'
                    ).first()
                    if story_vernacular and story_vernacular.translation_json:
                        vernacular_title = story_vernacular.translation_json.get('title')
                        if vernacular_title:
                            english_title = vernacular_title
                            logger.info(f"Used StoryVernacular English title")
                except Exception as e:
                    logger.info(f"Could not get title from StoryVernacular: {e}")
            if not english_title or not english_title.strip():
                print("Default title")
                english_title = 'Improvement_story'
                logger.info("Using default title: Improvement_story")

            story_fields_to_update['title'] = english_title

        print("english_title: ", english_title)
        if 'content' in response_json_story and 'content' not in exclude_fields_set:
            raw_content = response_json_story.get('content', '')
            story_fields_to_update['content'] = clean_escaped_text(
                text=translate_to_english_if_needed(raw_content, translation_voice_provider, language)
            )

        if 'objective' in response_json_story and 'objective' not in exclude_fields_set:
            raw_objective = response_json_story.get('objective', '')
            story_fields_to_update['objective'] = clean_escaped_text(
                text=translate_to_english_if_needed(raw_objective, translation_voice_provider, language)
            )

        if 'impact' in response_json_story and 'impact' not in exclude_fields_set:
            raw_impact = response_json_story.get('impact', '')
            story_fields_to_update['impact'] = clean_escaped_text(
                text=translate_to_english_if_needed(raw_impact, translation_voice_provider, language)
            )

        if 'blurb' in response_json_story and 'blurb' not in exclude_fields_set:
            raw_blurb = response_json_story.get('blurb', '')
            story_fields_to_update['blurb'] = clean_escaped_text(
                text=translate_to_english_if_needed(raw_blurb, translation_voice_provider, language)
            )

        if 'tweet' in response_json_story and 'tweet' not in exclude_fields_set:
            story_fields_to_update['tweet'] = response_json_story.get('tweet', '')

        if 'micro_improvement' in response_json_story and 'micro_improvement' not in exclude_fields_set:
            story_fields_to_update['micro_improvement'] = response_json_story.get('micro_improvement', '')

        if 'action_steps' in response_json_story and 'action_steps' not in exclude_fields_set:
            raw_action_steps = response_json_story.get('action_steps', [])
            if isinstance(raw_action_steps, str):
                story_fields_to_update['action_steps'] = translate_to_english_if_needed(raw_action_steps,
                                                                                        translation_voice_provider,
                                                                                        language)
            elif isinstance(raw_action_steps, list):
                story_fields_to_update['action_steps'] = [
                    translate_to_english_if_needed(step, translation_voice_provider, language)
                    for step in raw_action_steps
                ]
            else:
                story_fields_to_update['action_steps'] = raw_action_steps

        if 'location' in response_json_story and 'location' not in exclude_fields_set:
            raw_location = response_json_story.get('location', fallback_location)
            if raw_location and raw_location.strip():
                story_fields_to_update['location'] = transliterate_to_english_if_needed(raw_location,
                                                                                        transliteration_voice_provider,
                                                                                        language)
            else:
                story_fields_to_update['location'] = ""

        story_fields_to_update.update({
            'author': profile if isinstance(profile, Profile) else Profile.objects.filter(id=profile.get("id")).first(),
            'session': session,
            'language': 'en',
            'stage': StoryStatusChoices.COMPLETED,
            'other_params': other_params,
            'validation_logs': combined_reason
        })

        if story:
            for field, value in story_fields_to_update.items():
                if hasattr(story, field):
                    setattr(story, field, value)
        else:
            default_story_fields = {
                'title': 'Improvement_story',
                'content': '',
                'tweet': '',
                'objective': '',
                'action_steps': [],
                'impact': '',
                'micro_improvement': '',
                'blurb': '',
                'location': '',
            }
            default_story_fields.update(story_fields_to_update)
            story = Story(**default_story_fields)

        story.save()
        print(f"Story saved with other_params: {story.other_params}")

        if language != 'en':
            english_data = {}
            for field in ['title', 'content', 'tweet', 'objective', 'action_steps', 'impact', 'micro_improvement', 'blurb']:
                if field in story_fields_to_update:
                    english_data[field] = story_fields_to_update[field]

            create_generic_story_translation(
                story=story,
                language=language,
                english_data=english_data,
                voice_provider=voice_provider,
                flow=flow,
                company_bot=company_bot,
                response_json_story=response_json_story,
                previous_english_snapshot=previous_english_snapshot,
                exclude_fields=exclude_fields_set
            )

        logger.info(f"Successfully saved generic story for flow {flow}, session {session}")

        problem_statement = ""
        if 'problem_statement' in response_json_story and 'problem_statement' not in exclude_fields_set:
            raw_problem_statement = response_json_story.get('problem_statement', '')
            problem_statement = clean_escaped_text(
                text=translate_to_english_if_needed(raw_problem_statement, translation_voice_provider, language)
            )

        return story, problem_statement

    except StoryError:
        raise

    except Exception as e:
        logger.error("Error saving generic story: %s", e, exc_info=True)
        raise StorySaveError()


def create_generic_story_translation(story, language, english_data, voice_provider, flow, company_bot,
                                     response_json_story, previous_english_snapshot, exclude_fields=None):
    try:

        import copy
        if exclude_fields is None:
            exclude_fields = set()

        print(f"Creating translation for language: {language}")
        print(f"Story other_params: {story.other_params}")

        existing_translation = StoryTranslation.objects.filter(
            story=story,
            language=language
        ).first()

        if existing_translation and existing_translation.other_params:
            translated_other_params = copy.deepcopy(existing_translation.other_params)
        else:
            translated_other_params = {}

        logger.info(
            f"[TRANSLATION STATE] "
            f"existing_translation={'YES' if existing_translation else 'NO'} | "
            f"existing_keys={list(translated_other_params.keys())}"
        )

        TRANSLATABLE_FIELDS = ['title', 'content', 'tweet', 'objective', 'impact', 'micro_improvement', 'blurb']

        translated_data = {}

        for field in TRANSLATABLE_FIELDS:
            if field in exclude_fields:
                continue
            should_translate = False
            field_value = None

            if field in english_data and english_data[field]:
                should_translate = True
                field_value = english_data[field]
            elif existing_translation and not getattr(existing_translation, field, None):
                story_value = getattr(story, field, None)
                if story_value:
                    should_translate = True
                    field_value = story_value

            if should_translate and field_value:
                try:
                    translated_data[field] = translate_field(
                        voice_provider=voice_provider,
                        message_body=field_value,
                        target_language=language
                    )
                except Exception as e:
                    logger.info(f"Could not translate field {field}: {e}")
                    translated_data[field] = field_value

        action_steps_to_translate = None
        if 'action_steps' in english_data:
            action_steps_to_translate = english_data['action_steps']
        elif existing_translation and not existing_translation.action_steps:
            if story.action_steps:
                action_steps_to_translate = story.action_steps

        if action_steps_to_translate:
            if isinstance(action_steps_to_translate, str) and action_steps_to_translate.strip():
                try:
                    translated_data['action_steps'] = translate_field(
                        voice_provider=voice_provider,
                        message_body=action_steps_to_translate,
                        target_language=language
                    )
                except Exception as e:
                    logger.info(f"Could not translate action_steps: {e}")
                    translated_data['action_steps'] = action_steps_to_translate
            elif isinstance(action_steps_to_translate, list):
                translated_action_steps = []
                for action_step in action_steps_to_translate:
                    if action_step:
                        try:
                            translated_step = translate_field(
                                voice_provider=voice_provider,
                                message_body=str(action_step),
                                target_language=language
                            )
                            translated_action_steps.append(translated_step)
                        except Exception as e:
                            logger.info(f"Could not translate action step: {e}")
                            translated_action_steps.append(str(action_step))
                translated_data['action_steps'] = translated_action_steps

        print(f"Starting with translated_other_params: {translated_other_params}")

        NON_TRANSLATABLE_FIELDS = {'flow', 'id', 'uuid', 'status', 'type', 'mode', 'version', '_english_snapshot'}

        for key in NON_TRANSLATABLE_FIELDS:
            if key in story.other_params and key != '_english_snapshot':
                translated_other_params[key] = story.other_params[key]

        def is_translatable_text(value, key=""):
            if not isinstance(value, str) or not value.strip():
                return False

            value_str = str(value).strip()

            technical_fields = ['flow', 'id', 'uuid', 'status', 'type', 'mode', 'version']
            if key.lower() in technical_fields:
                return False

            if value_str.isdigit():
                return False

            if (value_str.startswith(('http://', 'https://', 'ftp://', 'mailto:')) or
                    value_str.count('@') == 1 and '.' in value_str.split('@')[1] or
                    value_str.startswith(('.', '/', '\\')) or
                    value_str.lower().endswith(('.jpg', '.png', '.pdf', '.doc', '.xls', '.mp4', '.mp3'))):
                return False

            alpha_count = sum(1 for c in value_str if c.isalpha())
            if alpha_count < len(value_str) * 0.5:
                return False

            return True

        def translate_nested_structure(data, field_path=""):
            if isinstance(data, dict):
                translated_dict = {}
                for key, value in data.items():
                    current_path = f"{field_path}.{key}" if field_path else key

                    if not isinstance(value, (str, dict, list)):
                        translated_dict[key] = value
                    elif isinstance(value, str) and is_translatable_text(value, key):
                        try:
                            translated_value = translate_field(
                                voice_provider=voice_provider,
                                message_body=value,
                                target_language=language
                            )
                            translated_dict[key] = translated_value
                        except Exception as e:
                            logger.info(f"Could not translate {current_path}: {e}")
                            translated_dict[key] = value
                    elif isinstance(value, (dict, list)):
                        translated_dict[key] = translate_nested_structure(value, current_path)
                    else:
                        translated_dict[key] = value
                return translated_dict
            elif isinstance(data, list):
                return [translate_nested_structure(item, field_path) for i, item in enumerate(data)]

            elif isinstance(data, str) and is_translatable_text(data, field_path):
                return translate_field(
                    voice_provider=voice_provider,
                    message_body=data,
                    target_language=language
                )
            else:
                return data

        fields_to_translate = []

        for key, english_value in story.other_params.items():
            if key in NON_TRANSLATABLE_FIELDS:
                continue

            previous_english_value = previous_english_snapshot.get(key)

            english_changed = (english_value != previous_english_value)
            translation_missing = (key not in translated_other_params)

            logger.info(
                f"[FIELD CHECK] key={key} | "
                f"english_changed={english_changed} | "
                f"translation_missing={translation_missing}"
            )

            if english_changed or translation_missing:
                fields_to_translate.append(key)
                logger.info(f"[WILL TRANSLATE] key={key}")
            else:
                logger.info(f"[SKIP - NO CHANGE] key={key}")

        for key in fields_to_translate:
            english_value = story.other_params[key]

            print(f"[TRANSLATING] key={key}, value={english_value}, type={type(english_value)}")

            if isinstance(english_value, (dict, list)):
                print(f"[NESTED] Translating nested structure for {key}")
                translated_other_params[key] = translate_nested_structure(english_value, key)
            elif isinstance(english_value, str) and english_value.strip():
                if is_translatable_text(english_value, key):
                    try:
                        print(f"[API CALL] Calling translate_field for {key}: '{english_value}'")
                        translated_value = translate_field(
                            voice_provider=voice_provider,
                            message_body=english_value,
                            target_language=language
                        )
                        print(f"[SUCCESS] Translated {key}: '{english_value}' -> '{translated_value}'")
                        translated_other_params[key] = translated_value
                    except Exception as e:
                        logger.error(f"[ERROR] Translation failed for {key}: {e}", exc_info=True)
                        print(f"[ERROR] Translation failed for {key}: {e}")
                        translated_other_params[key] = english_value
                else:
                    print(f"[SKIP] {key} failed is_translatable_text check")
                    translated_other_params[key] = english_value
            else:
                print(f"[KEEP] {key} is not a translatable type")
                translated_other_params[key] = english_value

        if 'duration' in story.other_params and 'duration' not in fields_to_translate:
            if 'duration' not in translated_other_params:
                duration_value = story.other_params.get('duration', '')
                if duration_value and ' ' in str(duration_value):
                    try:
                        print(f"[DURATION] Translating duration: {duration_value}")
                        translated_other_params['duration'] = translate_field(
                            voice_provider=voice_provider,
                            message_body=str(duration_value),
                            target_language=language
                        )
                    except Exception as e:
                        logger.info(f"Could not translate duration: {e}")

        if company_bot:
            try:
                voice_transliterate_provider = Voice.objects.filter(
                    company_bot=company_bot, type=VoiceType.Transliterate, language=language
                ).first()

                transliterate_fields = [
                    'user_name', 'location', 'organization', 'designation',
                    'district', 'block', 'village', 'panchayat', 'social_media'
                ]

                for field_name in transliterate_fields:
                    if field_name in fields_to_translate or (
                            field_name in story.other_params and field_name not in translated_other_params):
                        field_value = story.other_params.get(field_name, '')
                        if field_value and str(field_value).strip():
                            try:
                                is_sentence = ' ' in str(field_value)
                                print(f"Transliterating {field_name}: {field_value}")
                                transliterated = transliterate_text(
                                    voice_provider=voice_transliterate_provider,
                                    message_body=str(field_value),
                                    target_language=language,
                                    source_language='en',
                                    is_sentence=is_sentence
                                )
                                translated_other_params[field_name] = get_transliteration_output(data=transliterated)
                                print(f"Transliterated to: {translated_other_params[field_name]}")
                            except Exception as e:
                                logger.info(f"Could not transliterate field {field_name}: {e}")
                                translated_other_params[field_name] = str(field_value)

                if story.location and (
                        'location' in fields_to_translate or 'location' not in translated_other_params):
                    try:
                        transliterated = transliterate_text(
                            voice_provider=voice_transliterate_provider,
                            message_body=story.location,
                            target_language=language,
                            source_language='en',
                            is_sentence=' ' in story.location
                        )
                        translated_other_params['location'] = get_transliteration_output(data=transliterated)
                    except Exception as e:
                        logger.info(f"Could not transliterate location: {e}")

            except Exception as e:
                logger.info(f"Could not set up transliteration: {e}")

        print(f"Final translated_other_params: {translated_other_params}")

        translated_other_params.pop("_english_snapshot", None)

        if existing_translation:
            update_fields = ['other_params']
            translation = existing_translation
            translation.other_params = translated_other_params

            for field in TRANSLATABLE_FIELDS:
                if field in translated_data:
                    setattr(translation, field, translated_data[field])
                    update_fields.append(field)

            if 'action_steps' in translated_data:
                translation.action_steps = translated_data['action_steps']
                update_fields.append('action_steps')

            if story.location and not translation.location:
                if 'location' in translated_other_params:
                    translation.location = translated_other_params['location']
                else:
                    translation.location = story.location
                update_fields.append('location')

            translation.save(update_fields=update_fields)
            created = False
        else:
            defaults = {
                'title': '',
                'content': '',
                'tweet': '',
                'objective': '',
                'action_steps': [],
                'impact': '',
                'micro_improvement': '',
                'blurb': '',
                'location': '',
                'other_params': translated_other_params,
                'formatted_content': ''
            }

            for field in TRANSLATABLE_FIELDS:
                if field in translated_data:
                    defaults[field] = translated_data[field]

            if 'action_steps' in translated_data:
                defaults['action_steps'] = translated_data['action_steps']

            if 'location' in translated_other_params:
                defaults['location'] = translated_other_params['location']

            translation = StoryTranslation.objects.create(
                story=story,
                language=language,
                **defaults
            )
            created = True

        print(f"Translation saved with other_params: {translation.other_params}")

        try:
            formatted_translation_content = get_formatted_story(translation)
            if formatted_translation_content:
                translation.formatted_content = formatted_translation_content
                translation.save(update_fields=['formatted_content'])
        except Exception as e:
            logger.info(f"Could not format translation content: {e}")

        logger.info(f"Created/Updated generic translation for story {story.id} in language {language}")
        return translation

    except Exception as e:
        logger.error(f'Error creating generic translation: %s', e, exc_info=True)
        return None


def get_generic_story_in_language(story, language='en'):
    if language == 'en' or language == story.language:
        return {
            'title': story.title,
            'content': story.content,
            'tweet': story.tweet,
            'objective': story.objective,
            'action_steps': story.action_steps,
            'impact': story.impact,
            'micro_improvement': story.micro_improvement,
            'blurb': story.blurb,
            'location': story.location,
            'other_params': story.other_params,
        }

    try:
        translation = story.translations.get(language=language)
        return {
            'title': translation.title,
            'content': translation.content,
            'tweet': translation.tweet,
            'objective': translation.objective,
            'action_steps': translation.action_steps,
            'impact': translation.impact,
            'micro_improvement': translation.micro_improvement,
            'blurb': translation.blurb,
            'location': translation.location,
            'other_params': translation.other_params,
        }
    except StoryTranslation.DoesNotExist:
        return get_generic_story_in_language(story, 'en')
