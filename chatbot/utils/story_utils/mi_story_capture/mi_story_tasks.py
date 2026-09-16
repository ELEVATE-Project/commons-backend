import traceback
import logging
import re

from chatbot.exceptions.story_exceptions import StoryDomainError, StoryValidationError, StorySaveError, StoryError
from chatbot.models import StoryStatusChoices, Story, SessionFlowName, Voice, VoiceType, StoryTranslation
from chatbot.models.geo_models import ProfileAddress
from chatbot.utils.story_llama_utils import translate_field, create_project
from chatbot.utils.story_utils.format_utils import clean_escaped_text, get_formatted_story
from chatbot.utils.transliterate_utils import transliterate_text, get_transliteration_output
from shikshalokam.models import Project, Task
from shikshalokam.serializer import TaskSerializer

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


def save_story(
        response_json_story, language, voice_provider, profile, session, combined_reason, flow=None, project_id=None,
        company_bot=None
):
    try:
        # Get voice providers for translation/transliteration
        translation_voice_provider = voice_provider
        transliteration_voice_provider = None

        if company_bot and language != 'en':
            transliteration_voice_provider = Voice.objects.filter(
                company_bot=company_bot, type=VoiceType.Transliterate, language=language
            ).first()

        # Extract and translate/transliterate fields to English
        raw_title = response_json_story.get('title', '')
        raw_content = response_json_story.get('content', '')
        raw_objective = response_json_story.get('objective', '')
        raw_impact = response_json_story.get('impact', '')
        raw_problem_statement = response_json_story.get('problem_statement', '')
        raw_blurb = response_json_story.get('blurb', '')

        is_within_domain = response_json_story.get('is_within_domain', True)

        if not is_within_domain:
            raise StoryDomainError()

        # Translate main content fields to English
        english_title = clean_escaped_text(
            text=translate_to_english_if_needed(raw_title, translation_voice_provider, language)
        )
        english_content = clean_escaped_text(
            text=translate_to_english_if_needed(raw_content, translation_voice_provider, language)
        )
        english_objective = clean_escaped_text(
            text=translate_to_english_if_needed(raw_objective, translation_voice_provider, language)
        )
        english_impact = clean_escaped_text(
            text=translate_to_english_if_needed(raw_impact, translation_voice_provider, language)
        )
        english_problem_statement = clean_escaped_text(
            text=translate_to_english_if_needed(raw_problem_statement, translation_voice_provider, language)
        )
        english_blurb = clean_escaped_text(
            text=translate_to_english_if_needed(raw_blurb, translation_voice_provider, language)
        )

        # Handle action_steps (can be string or list)
        raw_action_steps = response_json_story.get('action_steps', [])
        if isinstance(raw_action_steps, str):
            english_action_steps = translate_to_english_if_needed(raw_action_steps, translation_voice_provider,
                                                                  language)
        else:
            english_action_steps = [
                translate_to_english_if_needed(step, translation_voice_provider, language)
                for step in raw_action_steps
            ]

        english_tweet = clean_escaped_text(
            text=translate_to_english_if_needed(response_json_story.get('tweet', ''), translation_voice_provider,
                                                language)
        )
        english_micro_improvement = clean_escaped_text(
            text=translate_to_english_if_needed(response_json_story.get('micro_improvement', ''),
                                                translation_voice_provider, language)
        )
        duration = clean_escaped_text(
            text=translate_to_english_if_needed(response_json_story.get('duration', ''), translation_voice_provider,
                                                language)
        )

        if flow and flow in [SessionFlowName.GuestMiStory] and not project_id:
            # Transliterate personal information fields for guest stories
            raw_user_name = response_json_story.get('user_name', '')
            raw_location = response_json_story.get('location', '')
            raw_organization = response_json_story.get('organization', '')
            raw_designation = response_json_story.get('designation', '')

            user_name = transliterate_to_english_if_needed(raw_user_name, transliteration_voice_provider, language)
            location = transliterate_to_english_if_needed(raw_location, transliteration_voice_provider, language)
            organization = transliterate_to_english_if_needed(raw_organization, transliteration_voice_provider,
                                                              language)
            designation = transliterate_to_english_if_needed(raw_designation, transliteration_voice_provider, language)
        else:
            user_name = profile.first_name if profile and profile.first_name else ''
            organization = response_json_story.get('organization', '')
            designation = response_json_story.get('designation', '')
            location = None
            if profile:
                address = ProfileAddress.objects.filter(profile=profile).first()
                if address:
                    location_parts = filter(None, [address.block, address.district, address.state])
                    location = ", ".join(location_parts)
                else:
                    location = ""

        if (not english_title or not english_objective or not english_action_steps or not
            english_problem_statement or not english_content or not english_blurb
        ):
            raise StoryValidationError()

        if flow in [SessionFlowName.Reflection] and project_id:
            logger.info(f"project_id: %s", project_id)
            project = Project.objects.filter(project_id=project_id).first()
            if project:
                tasks = Task.objects.filter(project=project)
                serialized_tasks = TaskSerializer(tasks, many=True).data
                english_action_steps = [f"{idx + 1}. {task.get('task_name')}" for idx, task in
                                        enumerate(serialized_tasks)]

        other_params = {
            'duration': duration,
            'flow': flow,
            'user_name': user_name,
        }

        if flow and flow in [SessionFlowName.GuestMiStory]:
            other_params['user_name'] = user_name
            other_params['location'] = location
            other_params['organization'] = organization
            other_params['designation'] = designation

        story = Story.objects.filter(session=session).first()
        if story:
            story.title = english_title
            story.content = english_content
            story.tweet = english_tweet
            story.author = profile
            story.objective = english_objective
            story.action_steps = english_action_steps
            story.impact = english_impact
            story.micro_improvement = english_micro_improvement
            story.language = 'en'
            story.stage = StoryStatusChoices.COMPLETED
            story.other_params = other_params
            story.location = location if location else ""
            story.blurb = english_blurb
            story.validation_logs = combined_reason
        else:
            story = Story(
                title=english_title,
                content=english_content,
                tweet=english_tweet,
                author=profile,
                session=session,
                objective=english_objective,
                action_steps=english_action_steps,
                impact=english_impact,
                micro_improvement=english_micro_improvement,
                language='en',
                stage=StoryStatusChoices.COMPLETED,
                other_params=other_params,
                location=location if location else "",
                blurb=english_blurb,
                validation_logs=combined_reason
            )
        story.save()

        if language != 'en':
            create_story_translation(
                story=story,
                language=language,
                english_data={
                    'title': english_title,
                    'content': english_content,
                    'tweet': english_tweet,
                    'objective': english_objective,
                    'action_steps': english_action_steps,
                    'impact': english_impact,
                    'micro_improvement': english_micro_improvement,
                    'blurb': english_blurb
                },
                voice_provider=voice_provider,
                flow=flow,
                company_bot=company_bot,
                other_data={
                    'user_name': user_name,
                    'organization': organization,
                    'designation': designation,
                    'location': location
                }
            )

        create_project(
            response_json=response_json_story, title=english_title, objective=english_objective, story=story,
            profile=profile, problem_statement=english_problem_statement, language=language,
            voice_provider=voice_provider, project_id=project_id, action_steps=english_action_steps
        )

        return story, english_problem_statement

    except StoryError:
        raise

    except Exception as e:
        logger.error('Error Occurred: %s', e, exc_info=True)
        traceback.print_exc()
        raise StorySaveError()


def create_story_translation(story, language, english_data, voice_provider, flow, company_bot, other_data):
    """Create translation for a story"""
    try:
        translated_title = translate_field(
            voice_provider=voice_provider, message_body=english_data['title'], target_language=language
        )
        translated_content = translate_field(
            voice_provider=voice_provider, message_body=english_data['content'], target_language=language
        )
        translated_tweet = translate_field(
            voice_provider=voice_provider, message_body=english_data['tweet'], target_language=language
        )
        translated_objective = translate_field(
            voice_provider=voice_provider, message_body=english_data['objective'], target_language=language
        )
        translated_impact = translate_field(
            voice_provider=voice_provider, message_body=english_data['impact'], target_language=language
        )
        translated_micro_improvement = translate_field(
            voice_provider=voice_provider, message_body=english_data['micro_improvement'], target_language=language
        )
        translated_blurb = translate_field(
            voice_provider=voice_provider, message_body=english_data['blurb'], target_language=language
        )

        # action_steps (can be string or list)
        action_steps = english_data['action_steps']
        if isinstance(action_steps, str):
            translated_action_steps = translate_field(
                voice_provider=voice_provider, message_body=action_steps, target_language=language
            )
        else:
            translated_action_steps = [
                translate_field(
                    voice_provider=voice_provider,
                    message_body=action_step,
                    target_language=language
                )
                for action_step in action_steps
            ]

        import copy
        translated_other_params = copy.deepcopy(story.other_params) if story.other_params else {}

        if translated_other_params.get('duration'):
            duration_value = translated_other_params['duration']
            if ' ' in str(duration_value):
                translated_other_params['duration'] = translate_field(
                    voice_provider=voice_provider,
                    message_body=duration_value,
                    target_language=language
                )

        if flow and flow in [SessionFlowName.GuestMiStory] and company_bot:
            voice_transliterate_provider = Voice.objects.filter(
                company_bot=company_bot, type=VoiceType.Transliterate, language=language
            ).first()
            transliterate_fields = ['user_name', 'organization', 'designation', 'location']

            for field_name in transliterate_fields:
                field_value = other_data.get(field_name, '')
                if field_value and field_value != '':
                    is_sentence = ' ' in field_value
                    transliterated = transliterate_text(
                        voice_provider=voice_transliterate_provider,
                        message_body=field_value,
                        target_language=language,
                        source_language='en',
                        is_sentence=is_sentence
                    )
                    translated_other_params[field_name] = get_transliteration_output(data=transliterated)

        translation, created = StoryTranslation.objects.get_or_create(
            story=story,
            language=language,
            defaults={
                'title': translated_title,
                'content': translated_content,
                'tweet': translated_tweet,
                'objective': translated_objective,
                'action_steps': translated_action_steps,
                'impact': translated_impact,
                'micro_improvement': translated_micro_improvement,
                'blurb': translated_blurb,
                'other_params': translated_other_params,
                'formatted_content': ''
            }
        )

        if not created:
            translation.title = translated_title
            translation.content = translated_content
            translation.tweet = translated_tweet
            translation.objective = translated_objective
            translation.action_steps = translated_action_steps
            translation.impact = translated_impact
            translation.micro_improvement = translated_micro_improvement
            translation.blurb = translated_blurb
            translation.other_params = translated_other_params
            translation.save()

        formatted_translation_content = get_formatted_story(translation)
        if formatted_translation_content:
            translation.formatted_content = formatted_translation_content
            translation.save(update_fields=['formatted_content'])

        logger.info(f"Created/Updated translation for story {story.id} in language {language}")
        return translation

    except Exception as e:
        logger.error(f'Error creating translation: %s', e, exc_info=True)
        return None


def get_story_in_language(story, language='en'):
    """Get story content in specified language"""
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
            'other_params': story.other_params
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
            'other_params': story.other_params,
            'translated_other_params': translation.translated_other_params  # Translated parts
        }
    except StoryTranslation.DoesNotExist:
        return get_story_in_language(story, 'en')
