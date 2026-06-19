import json
import os
from chatbot.models import Story, ChatSession, CompanyChat, CompanyBot, Voice, VoiceType, ChatType, BotVernacular, \
    StoryTranslation
from chatbot.utils.audio_provider_utils import text_translate_provider
import json_repair
import logging
from django.utils.timezone import make_aware
from datetime import datetime
from retrying import retry
from chatbot.utils.llm import LLM
from chatbot.models.enums import LLMProvider
from chatbot.llm_models.llm_script import handle_bedrock_model

from chatbot.utils.chat_utils import format_message_as_per_bedrock_format
from chatbot.utils.transliterate_utils import get_transliteration_output

logger = logging.getLogger('django')
llm_retry_number = int(os.getenv('LLM_RETRY_NUMBER', 3))

# Constants for field categorization
TRANSLITERATE_FIELDS = ["user_name", "organization", "location", "district", "village", "block"]
NESTED_TRANSLITERATE_FIELDS = ["pri_member", "school_representative"]
TRANSLATE_FIELDS = ["title", "challenges_faced", "solutions_discussed", "remarks"]
PASSTHROUGH_FIELDS = ["participants_count", "discussion_date", "flow"]


def translate_field(voice_provider, message_body, target_language, source_language="en"):
    """For regular translation (used for title and other text content)"""
    if not message_body or message_body == '' or source_language == target_language:
        return message_body

    try:
        response = text_translate_provider(
            voice_provider=voice_provider,
            message_body=message_body,
            target_language=target_language,
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
    """For transliteration (used for location names, districts, villages, names)"""
    if not message_body or message_body == '' or source_language == target_language:
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


def process_field_value(field_name, value, target_language, source_language, translate_provider,
                        transliterate_provider):
    """Process a field value based on its type - DRY approach"""
    if not value or value == '':
        return value

    # Special handling for 'others' village
    if field_name in ['village', 'district', 'block'] and str(value).lower() in ['others', 'other']:
        return value

    # Transliterate names and location fields
    if field_name in TRANSLITERATE_FIELDS:
        if transliterate_provider:
            return transliterate_field(
                voice_provider=transliterate_provider,
                message_body=str(value),
                target_language=target_language,
                source_language=source_language
            )

    # Translate text content fields
    elif field_name in TRANSLATE_FIELDS:
        if translate_provider:
            # Handle lists (like challenges_faced, solutions_discussed)
            if isinstance(value, list):
                return [translate_field(
                    voice_provider=translate_provider,
                    message_body=str(item),
                    target_language=target_language,
                    source_language=source_language
                ) for item in value if item]
            else:
                return translate_field(
                    voice_provider=translate_provider,
                    message_body=str(value),
                    target_language=target_language,
                    source_language=source_language
                )
    elif field_name in NESTED_TRANSLITERATE_FIELDS:
        return process_nested_transliterate_field(
            field_value=value,
            target_language=target_language,
            source_language=source_language,
            transliterate_provider=transliterate_provider
        )

    # Passthrough fields (no translation/transliteration needed)
    return value


def process_nested_transliterate_field(field_value, target_language, source_language, transliterate_provider):
    """Process nested objects like pri_member and school_representative"""
    if not field_value or not isinstance(field_value, dict):
        return field_value

    processed_field = {}
    for sub_field_name in ['name', 'designation']:
        sub_field_value = field_value.get(sub_field_name, '')
        if sub_field_value and sub_field_value != '':
            if transliterate_provider:
                processed_field[sub_field_name] = transliterate_field(
                    voice_provider=transliterate_provider,
                    message_body=str(sub_field_value),
                    target_language=target_language,
                    source_language=source_language
                )
            else:
                processed_field[sub_field_name] = sub_field_value
        else:
            processed_field[sub_field_name] = sub_field_value

    return processed_field

def get_voice_providers(company_bot, language=None):
    """Get voice providers for translation and transliteration - DRY approach"""
    providers = {}

    # Try to get language-specific providers first
    if language:
        providers['translate'] = Voice.objects.filter(
            company_bot=company_bot,
            type=VoiceType.TextToText,
            language=language
        ).first()

        providers['transliterate'] = Voice.objects.filter(
            company_bot=company_bot,
            type=VoiceType.Transliterate,
            language=language
        ).first()

    # Fall back to default providers if language-specific not found
    if not providers.get('translate'):
        providers['translate'] = Voice.objects.filter(
            company_bot=company_bot,
            type=VoiceType.TextToText
        ).first()

    if not providers.get('transliterate'):
        providers['transliterate'] = Voice.objects.filter(
            company_bot=company_bot,
            type=VoiceType.Transliterate
        ).first()

    return providers


def update_or_create_story_translation(story, company_bot):
    """Create or update translation based on ChatSession language - processes ALL fields"""
    try:
        # Get the language from ChatSession
        chat_session = ChatSession.objects.filter(session=story.session).first()
        if not chat_session or not chat_session.language:
            logger.info(f"No ChatSession or language found for Story ID {story.id}")
            return

        session_language = chat_session.language

        # Skip if the session language is English (main story should be in English)
        if session_language == 'en':
            logger.info(f"Session language is English for Story ID {story.id}, skipping translation")
            return

        # Get voice providers
        providers = get_voice_providers(company_bot, session_language)
        translate_provider = providers['translate']
        transliterate_provider = providers['transliterate']

        # Prepare translated other_params - process ALL fields from story.other_params
        translated_other_params = {}

        # Process ALL fields in other_params, not just updated ones
        if story.other_params:
            for field, value in story.other_params.items():
                translated_value = process_field_value(
                    field_name=field,
                    value=value,
                    target_language=session_language,
                    source_language="en",
                    translate_provider=translate_provider,
                    transliterate_provider=transliterate_provider
                )
                translated_other_params[field] = translated_value
                logger.debug(f"Translated field '{field}': {value} -> {translated_value}")

        # Translate title from English to session language
        translated_title = story.title
        if translate_provider and story.title:
            translated_title = translate_field(
                voice_provider=translate_provider,
                message_body=story.title,
                target_language=session_language,
                source_language="en"
            )
            logger.info(
                f"Translated title from '{story.title}' to '{translated_title}' for language {session_language}")

        # Get or create the translation
        translation, created = StoryTranslation.objects.get_or_create(
            story=story,
            language=session_language,
            defaults={
                'title': translated_title,
                'content': story.content if story.content else '',
                'blurb': story.blurb if story.blurb else '',
                'tweet': story.tweet if story.tweet else '',
                'objective': story.objective if story.objective else '',
                'action_steps': story.action_steps if story.action_steps else '',
                'impact': story.impact if story.impact else '',
                'micro_improvement': story.micro_improvement if story.micro_improvement else '',
                'formatted_content': story.formatted_content if story.formatted_content else '',
                'other_params': translated_other_params  # All fields translated
            }
        )

        if not created:
            # Update existing translation with ALL fields
            translation.other_params = translated_other_params  # Replace entirely with all fields
            translation.title = translated_title
            translation.save(update_fields=["other_params", "title"])
            logger.info(f"✅ Updated existing translation for Story ID {story.id}, language: {session_language}")
            logger.info(f"Translation other_params now has {len(translated_other_params)} fields")
        else:
            logger.info(f"✅ Created new translation for Story ID {story.id}, language: {session_language}")
            logger.info(f"Translation other_params has {len(translated_other_params)} fields")

    except Exception as e:
        logger.error(f"❌ Error updating/creating translation for Story ID {story.id}: {str(e)}")


def correct_metadata_for_story(story):
    """Main function to correct metadata and ensure English story with proper translations"""
    try:
        if not story.other_params:
            return f"Story ID {story.id} skipped (no other_params)"

        company_bot = CompanyBot.objects.get(route='/chaupal-story-script')

        prompt = get_prompt_from_company_bot(company_bot)
        if not prompt:
            logger.error(f"No prompt found in company_bot context for {company_bot.id}")
            return f"❌ No prompt found in company_bot context for Story ID {story.id}"

        # Get chat history
        company_chats = CompanyChat.objects.filter(session=story.session).order_by('created_at')

        flow_company_bot = CompanyBot.objects.get(route='/guided_guest')
        bot_vernacular = BotVernacular.objects.filter(company_bot=flow_company_bot).first()
        intro_to_pass = None
        if bot_vernacular:
            if story.author.first_name == '' or not story.author.first_name:
                intro_to_pass = bot_vernacular.alt_introductory_message
            else:
                intro_to_pass = bot_vernacular.introductory_message

        messages = format_message_as_per_bedrock_format(chats=company_chats, intro=intro_to_pass)

        # Get voice providers
        providers = get_voice_providers(company_bot)
        translate_provider = providers['translate']
        transliterate_provider = providers['transliterate']

        formatted_prompt = [{"text": prompt}]

        tools = get_tools_from_company_bot(company_bot)
        if not tools:
            logger.error(f"No tools found in company_bot tool_context for {company_bot.id}")
            return f"❌ No tools found in company_bot tool_context for Story ID {story.id}"

        # Get metadata from LLM
        response = handle_bedrock_model(
            system_prompt=formatted_prompt,
            messages=messages,
            model_name=company_bot.llm_model,
            temperature=company_bot.bot_temperature,
            max_token=company_bot.max_token,
            company_bot=company_bot,
            tools=tools
        )

        logger.info(f"LLM response: {response}")
        result = get_clean_output(response=response)
        logger.info(f"Cleaned result: {result}")

        if result and isinstance(result, str):
            result = json_repair.repair_json(result, return_objects=True)

        updated = False

        # Get the session language to determine if we need to translate to English
        chat_session = ChatSession.objects.filter(session=story.session).first()
        session_language = chat_session.language if chat_session else 'en'

        # Title should be in English for main story
        english_title = story.title
        if session_language != 'en' and translate_provider:
            # If session is not in English, translate title to English
            english_title = translate_field(
                voice_provider=translate_provider,
                message_body=english_title,
                target_language="en",
                source_language=session_language
            )
        story.title = english_title
        updated = True

        # Process all metadata fields
        all_fields = ["user_name", "location", "district", "village", "block", "organization",
                      "participants_count", "discussion_date", "challenges_faced", "solutions_discussed",
                      "pri_member", "school_representative", "remarks", "flow"]

        # Check if we need to translate existing TRANSLATE_FIELDS to English
        if session_language != 'en' and translate_provider:
            # Translate existing non-English content in TRANSLATE_FIELDS to English
            for field in TRANSLATE_FIELDS:
                if field in story.other_params and field != 'title':  # title handled separately
                    current_value = story.other_params[field]
                    if current_value:
                        # Check if it's already in English or needs translation
                        if isinstance(current_value, list):
                            # For lists, check if any item contains non-ASCII characters (likely non-English)
                            if any(not all(ord(c) < 128 for c in str(item)) for item in current_value):
                                english_value = [translate_field(
                                    voice_provider=translate_provider,
                                    message_body=str(item),
                                    target_language="en",
                                    source_language=session_language
                                ) for item in current_value if item]
                                story.other_params[field] = english_value
                                updated = True
                                logger.info(f"Translated {field} to English in main story")
                        else:
                            # For strings, check if it contains non-ASCII characters
                            if not all(ord(c) < 128 for c in str(current_value)):
                                english_value = translate_field(
                                    voice_provider=translate_provider,
                                    message_body=str(current_value),
                                    target_language="en",
                                    source_language=session_language
                                )
                                story.other_params[field] = english_value
                                updated = True
                                logger.info(f"Translated {field} to English in main story")

        # Check if we need to transliterate existing TRANSLITERATE_FIELDS to English
        if session_language != 'en' and transliterate_provider:
            # Handle regular transliterate fields
            for field in TRANSLITERATE_FIELDS:
                if field in story.other_params and story.other_params[field]:
                    current_value = story.other_params[field]
                    # Check if it contains non-ASCII characters (likely non-English)
                    if not all(ord(c) < 128 for c in str(current_value)):
                        english_value = transliterate_field(
                            voice_provider=transliterate_provider,
                            message_body=str(current_value),
                            target_language="en",
                            source_language=session_language
                        )
                        story.other_params[field] = english_value
                        updated = True
                        logger.info(f"Transliterated {field} to English in main story")

            # Handle nested transliterate fields
            for field in NESTED_TRANSLITERATE_FIELDS:
                if field in story.other_params and story.other_params[field]:
                    current_value = story.other_params[field]
                    if isinstance(current_value, dict):
                        needs_update = False
                        updated_nested = {}
                        for sub_field in ['name', 'designation']:
                            sub_value = current_value.get(sub_field, '')
                            if sub_value and not all(ord(c) < 128 for c in str(sub_value)):
                                # Contains non-ASCII, needs transliteration
                                english_sub_value = transliterate_field(
                                    voice_provider=transliterate_provider,
                                    message_body=str(sub_value),
                                    target_language="en",
                                    source_language=session_language
                                )
                                updated_nested[sub_field] = english_sub_value
                                needs_update = True
                            else:
                                updated_nested[sub_field] = sub_value

                        if needs_update:
                            story.other_params[field] = updated_nested
                            updated = True
                            logger.info(f"Transliterated {field} to English in main story")

        # Process new fields from LLM result
        for key in all_fields:
            if value := result.get(key):
                # Process to English (main story should be in English)
                processed_value = process_field_value(
                    field_name=key,
                    value=value,
                    target_language="en",  # Main story in English
                    source_language=session_language if session_language != 'en' else "en",
                    translate_provider=translate_provider,
                    transliterate_provider=transliterate_provider
                )

                story.other_params[key] = processed_value
                updated = True
            else:
                # Handle missing fields
                if key in ["organization", "pri_member", "school_representative",
                           "remarks", 'block'] and key not in story.other_params:
                    if key in ["pri_member", "school_representative"]:
                        story.other_params[key] = {"name": "", "designation": ""}
                    else:
                        story.other_params[key] = ""
                    updated = True
                elif key not in story.other_params:
                    logger.info(f"🔸 {key} missing in Story ID {story.id}")

        if "participants_count" in story.other_params:
            participants_count = story.other_params["participants_count"]
            if isinstance(participants_count, str):
                story.other_params["participants_count"] = {
                    "total": participants_count,
                    "women": "",
                    "men": "",
                    "children": ""
                }
                updated = True
                logger.info(f"Converted participants_count to new format for Story ID {story.id}")

        # Ensure story language is set to English
        if story.language != 'en':
            story.language = 'en'
            updated = True

        if updated:
            fields_to_update = ["other_params", "language"]
            if hasattr(story, 'title'):
                fields_to_update.append("title")

            story.save(update_fields=fields_to_update)
            logger.info(f"✅ Updated Story ID {story.id} to English")
            logger.info(f"Story other_params now has {len(story.other_params)} fields")

            # Create/update translation with ALL fields, not just updated ones
            logger.info(f"🔄 Updating/creating translation for Story ID {story.id}")
            update_or_create_story_translation(story, company_bot)

            return f"✅ Updated Story ID {story.id} and its translation"
        else:
            # Even if no updates to main story, ensure translation has all fields
            logger.info(f"🔄 Ensuring translation completeness for Story ID {story.id}")
            update_or_create_story_translation(story, company_bot)
            return f"✅ Ensured complete translation for Story ID {story.id}"

    except Exception as e:
        logger.error(f"❌ Error in Story ID {story.id}: {str(e)}")
        return f"❌ Error in Story ID {story.id}: {str(e)}"


def get_prompt_from_company_bot(company_bot):
    """Get prompt from company bot context field"""
    return company_bot.context if company_bot.context else ""


def get_tools_from_company_bot(company_bot):
    """Get tools from company bot tool_context field"""
    if not company_bot.tool_context:
        return None

    try:
        tools = json.loads(company_bot.tool_context)
        return tools
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Error parsing tool_context for company_bot {company_bot.id}: {e}")
        return None


def clean_all_stories(start=0, end=100):
    """Clean all stories in a range"""
    session_ids = list(
        ChatSession.objects.filter(session_type=ChatType.shikshaChaupal)
        .values_list('session', flat=True)
    )

    stories = Story.objects.filter(session__in=session_ids) \
                  .exclude(other_params=None) \
                  .order_by('-id')[start:end]

    print(f"Cleaning stories from {start} to {end}... Total: {stories.count()}")
    logger.info(f"Cleaning stories from {start} to {end}... Total: {stories.count()}")

    results = {
        'success': 0,
        'no_changes': 0,
        'failed': 0
    }

    for story in stories:
        result = correct_metadata_for_story(story)
        print(result)

        if "✅" in result:
            results['success'] += 1
        elif "🟡" in result:
            results['no_changes'] += 1
        else:
            results['failed'] += 1

    summary = f"Cleaning completed: {results['success']} successful, {results['no_changes']} no changes, {results['failed']} failed"
    print(summary)
    logger.info(summary)
    return summary


def get_story_count(start_time=None, end_time=None):
    """Get story IDs for a specific time range"""
    if not start_time:
        start_time = make_aware(datetime(2025, 5, 1, 0, 0))
    if not end_time:
        end_time = make_aware(datetime(2025, 8, 28, 23, 59, 59))
    print(f"start_time: {start_time} and end time {end_time}")
    session_ids = list(
        ChatSession.objects.filter(
            session_type=ChatType.shikshaChaupal,
            created_at__gt=start_time,
            created_at__lt=end_time
        )
        .order_by('created_at')
        .values_list('session', flat=True)
    )

    if session_ids:
        logger.info(f"Found {len(session_ids)} sessions")
        logger.info(f"First session ID: {session_ids[0]}, Last session ID: {session_ids[-1]}")
        print(f"First session id: {session_ids[0]}")
        print(f"Last session id: {session_ids[-1]}")
    else:
        print("No sessions found.")
        return []
    print(f"Total session: {len(session_ids)}")
    story_ids = list(
        Story.objects.filter(session__in=session_ids)
        .exclude(other_params=None)
        .order_by('-id')
        .values_list('id', flat=True)
    )

    logger.info(f"Total stories: {len(story_ids)}")
    print(f"Total stories: {len(story_ids)}")
    return story_ids


def clean_specific_stories(story_ids):
    """Clean specific stories by their IDs"""
    stories = Story.objects.filter(id__in=story_ids)

    print(f"Cleaning {stories.count()} stories...")
    logger.info(f"Cleaning {stories.count()} stories...")

    results = {
        'success': 0,
        'no_changes': 0,
        'failed': 0
    }

    for story in stories:
        result = correct_metadata_for_story(story)
        print(result)

        if "✅" in result:
            results['success'] += 1
        elif "🟡" in result:
            results['no_changes'] += 1
        else:
            results['failed'] += 1

    summary = f"Cleaning completed: {results['success']} successful, {results['no_changes']} no changes, {results['failed']} failed"
    print(summary)
    logger.info(summary)
    return summary


def retry_if_result_none(result):
    return result is None


def get_clean_output(response):
    """Clean and format the LLM response"""
    if response and isinstance(response, dict):
        extracted_data = response.pop("parameters", response.pop("input", None))
        if extracted_data and isinstance(extracted_data, dict):
            response.clear()
            response.update(extracted_data)

    response_json_content = response
    if response_json_content and isinstance(response_json_content, str):
        response_json_content = json_repair.repair_json(response_json_content, return_objects=True)

    if isinstance(response_json_content, dict) and response_json_content.get("type"):
        if "value" in response_json_content:
            value = response_json_content.get("value")
        elif "parameters" in response_json_content:
            value = response_json_content.get("parameters")
        else:
            value = None
        if value and isinstance(value, str) and value.strip():
            value = json_repair.repair_json(value, return_objects=True)
            response_json_content = value
        else:
            response_json_content = {}

    return response_json_content

# Usage instructions:
# Step 1: Get story IDs for a date range
# story_ids = get_story_count(start_time,end_time)
#
# Step 2: Clean the specific stories
# clean_specific_stories(story_ids)
#
# Or clean all stories in a range:
# clean_all_stories(start=0, end=100)
