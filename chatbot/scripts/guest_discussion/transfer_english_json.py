import logging
from django.utils.timezone import make_aware
from datetime import datetime
from chatbot.models import Story, ChatSession, ChatType, StoryTranslation, Voice, VoiceType, CompanyBot
from chatbot.utils.audio_provider_utils import text_translate_provider
from chatbot.utils.transliterate_utils import get_transliteration_output

logger = logging.getLogger('django')


def translate_to_english(voice_provider, message_body, source_language="auto"):
    """Translate any text to English"""
    if not message_body or message_body == '':
        return message_body

    try:
        response = text_translate_provider(
            voice_provider=voice_provider,
            message_body=message_body,
            target_language="en",
            source_language=source_language
        )
        if response.get('status') == 200:
            return response.get('content')
        else:
            logger.warning(f"Translation failed, using original text: {message_body}")
            return message_body
    except Exception as e:
        logger.error(f"Error translating text '{message_body}': {str(e)}")
        return message_body


def transliterate_field(voice_provider, message_body, target_language, source_language="en"):
    """For transliteration (used for location names, districts, villages)"""
    if not message_body or message_body == '':
        return message_body

    try:
        from chatbot.utils.transliterate_utils import transliterate_text
        is_sentence = ' ' in message_body
        response = transliterate_text(
            voice_provider=voice_provider,
            message_body=message_body,
            target_language=target_language,
            source_language=source_language,
            is_sentence=is_sentence
        )
        if response.get('status') == 200:
            data = get_transliteration_output(response.get('content'))
            return data if data else response.get('content')
        else:
            logger.warning(f"Transliteration failed, using original text: {message_body}")
            return message_body
    except Exception as e:
        logger.error(f"Error transliterating text '{message_body}': {str(e)}")
        return message_body


def migrate_story_data(story):
    """Migrate non-English story to English format"""
    try:
        if not story.other_params or 'english_json' not in story.other_params:
            return f"Story ID {story.id} skipped (no english_json found)"

        english_json = story.other_params['english_json']
        original_language = story.language

        # Get company bot for voice providers
        company_bot = CompanyBot.objects.filter(route='/guest-story').first()
        if not company_bot:
            return f"❌ No company bot found for Story ID {story.id}"

        # Get translation and transliteration providers
        translate_provider = Voice.objects.filter(
            company_bot=company_bot, type=VoiceType.TextToText
        ).first()

        transliterate_provider = Voice.objects.filter(
            company_bot=company_bot, type=VoiceType.Transliterate
        ).first()

        # Store original story data in translation before migration
        if story.language != 'en':
            create_story_translation_from_original(story, company_bot, transliterate_provider, translate_provider)

        # Handle location, district, and village - use transliteration to get English versions
        english_location = english_json.get('location', '')
        english_district = english_json.get('district', '')
        english_village = english_json.get('village', '')

        # If english_json doesn't have location/district, transliterate from original
        if not english_location and story.other_params.get('location'):
            english_location = transliterate_field(
                voice_provider=transliterate_provider,
                message_body=story.other_params['location'],
                target_language="en",
                source_language=original_language
            )

        if not english_district and story.other_params.get('district'):
            english_district = transliterate_field(
                voice_provider=transliterate_provider,
                message_body=story.other_params['district'],
                target_language="en",
                source_language=original_language
            )

        if not english_village and story.other_params.get('village') and story.other_params['village'] != 'others':
            english_village = transliterate_field(
                voice_provider=transliterate_provider,
                message_body=story.other_params['village'],
                target_language="en",
                source_language=original_language
            )

        # Handle title translation to English
        english_title = english_json.get('title', '')
        if not english_title and story.title:
            # If no English title in english_json, translate the original title
            english_title = translate_to_english(
                voice_provider=translate_provider,
                message_body=story.title,
                source_language=original_language
            )
        elif not english_title:
            # Fallback to original title if no translation available
            english_title = story.title

        # Create new other_params with English data
        new_other_params = {
            'flow': english_json.get('flow', story.other_params.get('flow', '')),
            'village': english_village or english_json.get('village', story.other_params.get('village', '')),
            'district': english_district or english_json.get('district', story.other_params.get('district', '')),
            'location': english_location or english_json.get('location', story.other_params.get('location', '')),
            'user_name': english_json.get('user_name', ''),
            'organization': english_json.get('organization', ''),
            'discussion_date': english_json.get('discussion_date', story.other_params.get('discussion_date', '')),
            'challenges_faced': english_json.get('challenges_faced', []),
            'participants_count': english_json.get('participants_count',
                                                   story.other_params.get('participants_count', '')),
            'solutions_discussed': english_json.get('solutions_discussed', [])
        }

        # Update story fields
        story.title = english_title
        story.other_params = new_other_params
        story.location = english_location or english_json.get('location', story.other_params.get('location', ''))
        story.language = 'en'

        story.save(update_fields=['title', 'other_params', 'location', 'language'])

        logger.info(f"✅ Migrated Story ID {story.id} to English")
        return f"✅ Migrated Story ID {story.id} to English"

    except Exception as e:
        logger.error(f"❌ Error migrating Story ID {story.id}: {str(e)}")
        return f"❌ Error migrating Story ID {story.id}: {str(e)}"


def create_story_translation_from_original(story, company_bot, transliterate_provider, translate_provider):
    """Create translation record from original story data before migration"""
    try:
        original_language = story.language

        # Check if translation already exists
        existing_translation = StoryTranslation.objects.filter(
            story=story,
            language=original_language
        ).first()

        if existing_translation:
            logger.info(f"Translation already exists for Story ID {story.id}, language: {original_language}")
            return existing_translation

        # Prepare translation data - start with original story data
        translation_other_params = story.other_params.copy() if story.other_params else {}

        # Handle English fields that need transliteration to original language
        english_json = translation_other_params.get('english_json', {})

        # Transliterate English location/district/village names to original language
        location_fields_to_transliterate = ['location', 'district', 'village']

        for field in location_fields_to_transliterate:
            # Check if we have English version in english_json
            english_value = english_json.get(field, '')
            original_value = translation_other_params.get(field, '')

            # If we have English value but original is missing or seems like English
            if english_value and (not original_value or is_likely_english(original_value)):
                if field == 'village' and english_value.lower() in ['others', 'other']:
                    # Keep 'others' as is
                    translation_other_params[field] = english_value
                else:
                    # Transliterate from English to original language
                    transliterated_value = transliterate_field(
                        voice_provider=transliterate_provider,
                        message_body=english_value,
                        target_language=original_language,
                        source_language="en"
                    )
                    translation_other_params[field] = transliterated_value
                    logger.info(
                        f"Transliterated {field} '{english_value}' to '{transliterated_value}' for Story ID {story.id}")

        # Handle title for translation - ensure it's in the original language
        translation_title = story.title

        # Check if current title is in English and needs translation to original language
        if is_likely_english(story.title) and original_language != 'en':
            # Check if we have a non-English title in english_json (might be mislabeled)
            if english_json.get('title') and not is_likely_english(english_json.get('title')):
                translation_title = english_json.get('title')
            else:
                # Translate English title to original language
                translation_title = text_translate_provider(
                    voice_provider=translate_provider,
                    message_body=story.title,
                    target_language=original_language,
                    source_language="en"
                ).get('content', story.title)
                logger.info(f"Translated title from '{story.title}' to '{translation_title}' for Story ID {story.id}")

        # Remove english_json from translation other_params
        if 'english_json' in translation_other_params:
            del translation_other_params['english_json']

        # Create translation with original story data
        translation = StoryTranslation.objects.create(
            story=story,
            language=original_language,
            title=translation_title,
            content=story.content or '',
            blurb=story.blurb or '',
            tweet=story.tweet or '',
            objective=story.objective or '',
            action_steps=story.action_steps or '',
            impact=story.impact or '',
            micro_improvement=story.micro_improvement or '',
            formatted_content=story.formatted_content or '',
            other_params=translation_other_params
        )

        logger.info(f"✅ Created translation for Story ID {story.id}, language: {original_language}")
        return translation

    except Exception as e:
        logger.error(f"❌ Error creating translation for Story ID {story.id}: {str(e)}")
        return None


def is_likely_english(text):
    """Simple check if text is likely in English (basic heuristic)"""
    if not text:
        return False

    # Simple heuristic: if text contains mostly ASCII characters, it's likely English
    ascii_count = sum(1 for char in text if ord(char) < 128)
    total_chars = len(text)

    if total_chars == 0:
        return False

    # If more than 80% of characters are ASCII, consider it English
    return (ascii_count / total_chars) > 0.8


def get_migration_story_count(start_time=None, end_time=None):
    """Get stories that need migration (non-English with english_json)"""
    try:
        if not start_time:
            start_time = make_aware(datetime(2025, 5, 1, 0, 0))
        if not end_time:
            end_time = make_aware(datetime(2025, 8, 28, 23, 59, 59))

        # Get shikshaChaupal sessions
        session_ids = list(
            ChatSession.objects.filter(
                session_type=ChatType.shikshaChaupal,
                created_at__gt=start_time,
                created_at__lt=end_time
            )
            .order_by('created_at')
            .values_list('session', flat=True)
        )

        if not session_ids:
            logger.info("No shikshaChaupal sessions found")
            return []

        # Get stories that are not in English but have english_json
        story_ids = list(
            Story.objects.filter(
                session__in=session_ids,
                other_params__has_key='english_json'  # Has english_json
            )
            .exclude(language='en')  # Not already in English
            .exclude(other_params=None)
            .order_by('-id')
            .values_list('id', flat=True)
        )

        logger.info(f"Found {len(story_ids)} stories needing migration")
        if story_ids:
            logger.info(f"First story ID: {story_ids[0]}, Last story ID: {story_ids[-1]}")

        return story_ids

    except Exception as e:
        logger.error(f"Error getting migration story count: {str(e)}")
        return []


def migrate_specific_stories(story_ids):
    """Migrate specific stories by their IDs"""
    try:
        stories = Story.objects.filter(id__in=story_ids)

        logger.info(f"Migrating {stories.count()} stories...")
        print(f"Migrating {stories.count()} stories...")

        migrated_count = 0
        failed_count = 0

        for story in stories:
            result = migrate_story_data(story)
            print(result)

            if "✅" in result:
                migrated_count += 1
            else:
                failed_count += 1

        summary = f"Migration completed: {migrated_count} successful, {failed_count} failed"
        logger.info(summary)
        print(summary)

        return summary

    except Exception as e:
        logger.error(f"Error in migrate_specific_stories: {str(e)}")
        return f"Error in migration: {str(e)}"


def validate_migration_data(story_ids=None):
    """Validate that migration was successful"""
    try:
        if story_ids:
            stories = Story.objects.filter(id__in=story_ids)
        else:
            # Get recent shikshaChaupal stories
            session_ids = list(
                ChatSession.objects.filter(session_type=ChatType.shikshaChaupal)
                .values_list('session', flat=True)
            )
            stories = Story.objects.filter(session__in=session_ids, language='en')

        validation_results = {
            'total_checked': stories.count(),
            'english_stories': 0,
            'stories_with_translations': 0,
            'stories_without_english_json': 0,
            'issues': []
        }

        for story in stories:
            if story.language == 'en':
                validation_results['english_stories'] += 1

            if story.translations.exists():
                validation_results['stories_with_translations'] += 1

            if not story.other_params or 'english_json' in story.other_params:
                validation_results['stories_without_english_json'] += 1
                validation_results['issues'].append(f"Story {story.id} still has english_json")

        logger.info(f"Validation results: {validation_results}")
        return validation_results

    except Exception as e:
        logger.error(f"Error in validation: {str(e)}")
        return None


def clean_english_json_from_migrated_stories(story_ids):
    """Remove english_json from migrated stories' other_params"""
    try:
        stories = Story.objects.filter(
            id__in=story_ids,
            language='en',
            other_params__has_key='english_json'
        )

        cleaned_count = 0
        for story in stories:
            if 'english_json' in story.other_params:
                del story.other_params['english_json']
                story.save(update_fields=['other_params'])
                cleaned_count += 1

        logger.info(f"Cleaned english_json from {cleaned_count} stories")
        return cleaned_count

    except Exception as e:
        logger.error(f"Error cleaning english_json: {str(e)}")
        return 0


# Usage functions for easy execution
def run_migration_for_date_range(start_time=None, end_time=None):
    """Complete migration process for a date range"""
    try:
        logger.info("🚀 Starting story migration process...")

        # Step 1: Get stories that need migration
        story_ids = get_migration_story_count(start_time=start_time, end_time=end_time)

        if not story_ids:
            logger.info("No stories found for migration")
            return "No stories found for migration"

        # Step 2: Migrate the stories
        result = migrate_specific_stories(story_ids)

        # Step 3: Clean up english_json from migrated stories
        cleaned_count = clean_english_json_from_migrated_stories(story_ids)

        # Step 4: Validate migration
        validation = validate_migration_data(story_ids)

        final_result = f"{result} | Cleaned english_json from {cleaned_count} stories | Validation: {validation}"
        logger.info(f"Migration process completed: {final_result}")

        return final_result

    except Exception as e:
        logger.error(f"Error in migration process: {str(e)}")
        return f"Error in migration process: {str(e)}"