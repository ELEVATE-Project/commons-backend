import json
import traceback
import logging
import re
from chatbot.exceptions.story_exceptions import StoryDomainError, StoryValidationError, StoryError, StorySaveError
from chatbot.models import StoryStatusChoices, Story, Voice, VoiceType, StoryTranslation
from chatbot.models.geo_models import ProfileAddress
from chatbot.utils.story_llama_utils import translate_field
from chatbot.utils.story_utils.challenges_utils import handle_challenges_solutions
from chatbot.utils.story_utils.format_utils import clean_escaped_text
from chatbot.utils.transliterate_utils import transliterate_text, get_transliteration_output
import json_repair

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


def normalize_list_field(value):
    if isinstance(value, str):
        value = value.strip()
        if value in ("[]", ""):
            return []
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            return [value]
    return value


def save_chaupal_report(
        response_json_story, language, company_bot, voice_provider, profile, session, combined_reason, flow=None,
        messages=[]
):
    try:
        # Get voice providers for translation/transliteration
        translation_voice_provider = voice_provider
        transliteration_voice_provider = None

        if company_bot and language != 'en':
            transliteration_voice_provider = Voice.objects.filter(
                company_bot=company_bot, type=VoiceType.Transliterate, language=language
            ).first()

        is_within_domain = response_json_story.get('is_within_domain', True)

        if not is_within_domain:
            raise StoryDomainError()

        # Extract and translate fields to English
        raw_title = response_json_story.get('title', '')
        english_title = clean_escaped_text(
            text=translate_to_english_if_needed(raw_title, translation_voice_provider, language)
        )

        # Handle challenges and solutions (can be arrays)
        raw_challenges_faced = response_json_story.get('challenges_faced', [])
        raw_solutions_discussed = response_json_story.get('solutions_discussed', [])

        raw_challenges_faced = normalize_list_field(raw_challenges_faced)
        raw_solutions_discussed = normalize_list_field(raw_solutions_discussed)

        # Translate challenges and solutions
        if isinstance(raw_challenges_faced, list):
            english_challenges_faced = [
                translate_to_english_if_needed(challenge, translation_voice_provider, language)
                for challenge in raw_challenges_faced
            ]
        else:
            english_challenges_faced = translate_to_english_if_needed(raw_challenges_faced, translation_voice_provider,
                                                                      language)

        if isinstance(raw_solutions_discussed, list):
            english_solutions_discussed = [
                translate_to_english_if_needed(solution, translation_voice_provider, language)
                for solution in raw_solutions_discussed
            ]
        else:
            english_solutions_discussed = translate_to_english_if_needed(raw_solutions_discussed,
                                                                         translation_voice_provider, language)

        # Transliterate personal information fields
        raw_user_name = response_json_story.get('user_name', '')
        raw_user_location = response_json_story.get('location', '')
        raw_organization = response_json_story.get('organization', '')
        raw_remarks = response_json_story.get('remarks', '')

        user_name = transliterate_to_english_if_needed(raw_user_name, transliteration_voice_provider, language)
        user_location = transliterate_to_english_if_needed(raw_user_location, transliteration_voice_provider, language)
        organization = transliterate_to_english_if_needed(raw_organization, transliteration_voice_provider, language)
        remarks = translate_to_english_if_needed(raw_remarks, translation_voice_provider, language)

        participants_count = response_json_story.get('participants_count', {})
        if isinstance(participants_count, str):
            try:
                participants_count = json.loads(participants_count)
            except Exception:
                participants_count = {
                    'total': participants_count,
                    'women': '',
                    'men': '',
                    'children': ''
                }

        # --- Override total participant count if possible ---
        try:
            def safe_int(value):
                """Convert to int if value contains digits, else return 0"""
                if isinstance(value, (int, float)):
                    return int(value)
                if isinstance(value, str):
                    match = re.search(r'\d+', value)
                    if match:
                        return int(match.group())
                return 0

            men = safe_int(participants_count.get('men'))
            women = safe_int(participants_count.get('women'))
            children = safe_int(participants_count.get('children'))

            total = men + women + children
            # Only override if total is greater than 0
            if total > 0:
                participants_count['total'] = total
        except Exception as e:
            logger.warning(f"Error overriding total participants count: {e}")

        discussion_date = response_json_story.get('discussion_date', '')

        # Handle nested objects with transliteration
        raw_pri_member = response_json_story.get('pri_member', {'name': '', 'designation': ''})
        pri_member = {
            'name': transliterate_to_english_if_needed(raw_pri_member.get('name', ''), transliteration_voice_provider,
                                                       language),
            'designation': transliterate_to_english_if_needed(raw_pri_member.get('designation', ''),
                                                              transliteration_voice_provider, language)
        }

        raw_school_representative = response_json_story.get('school_representative', {'name': '', 'designation': ''})
        school_representative = {
            'name': transliterate_to_english_if_needed(raw_school_representative.get('name', ''),
                                                       transliteration_voice_provider, language),
            'designation': transliterate_to_english_if_needed(raw_school_representative.get('designation', ''),
                                                              transliteration_voice_provider, language)
        }

        if english_solutions_discussed and len(english_solutions_discussed) > 0 and english_challenges_faced and len(
                english_challenges_faced) > 0:
            english_challenges_faced, english_solutions_discussed = handle_challenges_solutions(
                challenges_faced=english_challenges_faced, solutions_discussed=english_solutions_discussed,
                profile=profile, messages=messages
            )

        if profile:
            address = ProfileAddress.objects.filter(profile=profile).first()
            if address:
                location_parts = filter(None, [address.block, address.district, address.state])
                location = ", ".join(location_parts)
            else:
                location = user_location
        else:
            location = user_location

        if isinstance(english_challenges_faced, str):
            english_challenges_faced = [english_challenges_faced]

        if not isinstance(english_challenges_faced, list) or not english_challenges_faced:
            raise StoryValidationError()


        other_params = {
            'challenges_faced': list(english_challenges_faced) if isinstance(
                english_challenges_faced, list) else english_challenges_faced,
            'solutions_discussed': list(english_solutions_discussed) if isinstance(
                english_solutions_discussed, list) else english_solutions_discussed,
            'user_name': user_name,
            'location': location,
            'organization': organization,
            'participants_count': dict(participants_count) if isinstance(
                participants_count, dict) else participants_count,
            'discussion_date': discussion_date,
            'pri_member': dict(pri_member) if isinstance(pri_member, dict) else pri_member,
            'school_representative': dict(school_representative) if isinstance(
                school_representative, dict) else school_representative,
            'remarks': remarks,
            'flow': flow
        }

        story = Story.objects.filter(session=session).first()
        if story:
            story.title = english_title
            story.other_params = other_params
            story.stage = StoryStatusChoices.COMPLETED
            story.location = location
            story.validation_logs = combined_reason
            story.language = 'en'
        else:
            story = Story(
                title=english_title,
                author=profile,
                session=session,
                stage=StoryStatusChoices.COMPLETED,
                location=location,
                validation_logs=combined_reason,
                language='en',
                other_params=other_params
            )
        story.save()
        story.refresh_from_db()

        if language != 'en':
            create_chaupal_translation(
                story=story,
                language=language,
                english_title=english_title,
                english_challenges_faced=english_challenges_faced,
                english_solutions_discussed=english_solutions_discussed,
                voice_provider=voice_provider,
                company_bot=company_bot,
                other_data={
                    'user_name': user_name,
                    'organization': organization,
                    'location': location,
                    'participants_count': participants_count,
                    'pri_member': pri_member,
                    'school_representative': school_representative,
                    'remarks': remarks
                }
            )

        return story, None

    except StoryError:
        raise

    except Exception as e:
        logger.error('Error Occurred: %s', e, exc_info=True)
        traceback.print_exc()
        raise StorySaveError()


def create_chaupal_translation(story, language, english_title, english_challenges_faced, english_solutions_discussed,
                               voice_provider, company_bot, other_data):
    """Create translation for chaupal report"""
    try:
        translated_title = translate_field(
            voice_provider=voice_provider, message_body=english_title, target_language=language
        )

        remarks = other_data.get('remarks', '')
        translated_remarks = ''
        if remarks and remarks.strip():
            translated_remarks = translate_field(
                voice_provider=voice_provider, message_body=remarks, target_language=language
            )

        if isinstance(english_challenges_faced, str):
            english_challenges_faced = json_repair.repair_json(english_challenges_faced, return_objects=True)

        translated_challenges_faced = [
            translate_field(
                voice_provider=voice_provider,
                message_body=challenge,
                target_language=language
            )
            for challenge in english_challenges_faced
        ]

        if isinstance(english_solutions_discussed, str):
            english_solutions_discussed = json_repair.repair_json(english_solutions_discussed, return_objects=True)

        translated_solutions_discussed = [
            translate_field(
                voice_provider=voice_provider,
                message_body=solution,
                target_language=language
            )
            for solution in english_solutions_discussed
        ]

        import copy
        translated_other_params = copy.deepcopy(story.other_params) if story.other_params else {}
        translated_other_params.update({
            'challenges_faced': translated_challenges_faced,
            'solutions_discussed': translated_solutions_discussed,
            'remarks': translated_remarks
        })

        voice_transliterate_provider = Voice.objects.filter(
            company_bot=company_bot, type=VoiceType.Transliterate, language=language
        ).first()

        for field_name in ['user_name', 'organization', 'location']:
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

        participants_count = other_data.get('participants_count', {})
        if participants_count:
            translated_other_params['participants_count'] = participants_count

        pri_member = other_data.get('pri_member', {'name': '', 'designation': ''})
        if pri_member:
            translated_pri_member = {}
            for field_name in ['name', 'designation']:
                field_value = pri_member.get(field_name, '')
                if field_value and field_value != '':
                    is_sentence = ' ' in field_value
                    transliterated = transliterate_text(
                        voice_provider=voice_transliterate_provider,
                        message_body=field_value,
                        target_language=language,
                        source_language='en',
                        is_sentence=is_sentence
                    )
                    translated_pri_member[field_name] = get_transliteration_output(data=transliterated)
                else:
                    translated_pri_member[field_name] = field_value
            translated_other_params['pri_member'] = translated_pri_member

        school_representative = other_data.get('school_representative', {'name': '', 'designation': ''})
        if school_representative:
            translated_school_representative = {}
            for field_name in ['name', 'designation']:
                field_value = school_representative.get(field_name, '')
                if field_value and field_value != '':
                    is_sentence = ' ' in field_value
                    transliterated = transliterate_text(
                        voice_provider=voice_transliterate_provider,
                        message_body=field_value,
                        target_language=language,
                        source_language='en',
                        is_sentence=is_sentence
                    )
                    translated_school_representative[field_name] = get_transliteration_output(data=transliterated)
                else:
                    translated_school_representative[field_name] = field_value
            translated_other_params['school_representative'] = translated_school_representative

        discussion_date = other_data.get('discussion_date', '')
        if discussion_date:
            translated_other_params['discussion_date'] = discussion_date

        translation, created = StoryTranslation.objects.get_or_create(
            story=story,
            language=language,
            defaults={
                'title': translated_title,
                'content': '',
                'other_params': translated_other_params
            }
        )

        if not created:
            translation.title = translated_title
            translation.other_params = translated_other_params
            translation.save()

        logger.info(f"Created/Updated chaupal translation for story {story.id} in language {language}")
        return translation

    except Exception as e:
        logger.error(f'Error creating chaupal translation: %s', e, exc_info=True)
        return None
