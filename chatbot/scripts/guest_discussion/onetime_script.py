import json
import os
import re
from chatbot.models import Story, ChatSession, CompanyChat, CompanyBot, Voice, VoiceType, ChatType, BotVernacular, \
    StoryTranslation
import json_repair
import logging
from django.utils.timezone import make_aware
from datetime import datetime
from retrying import retry
from chatbot.utils.llm import LLM
from chatbot.models.enums import LLMProvider
from chatbot.llm_models.llm_script import handle_bedrock_model

from chatbot.utils.chat_utils import format_message_as_per_bedrock_format

logger = logging.getLogger('django')
llm_retry_number = int(os.getenv('LLM_RETRY_NUMBER', 3))
AWS_KEY = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')


def safe_int(value):
    """Convert to int if value contains digits, else return 0"""
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        match = re.search(r'\d+', value)
        if match:
            return int(match.group())
    return 0


def process_participants_count(participants_count):
    """Process participant count to ensure it's a dictionary with proper structure"""
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

    # Ensure it's a dictionary with required fields
    if not isinstance(participants_count, dict):
        participants_count = {
            'total': str(participants_count),
            'women': '',
            'men': '',
            'children': ''
        }

    # Override total participant count if possible
    try:
        men = safe_int(participants_count.get('men'))
        women = safe_int(participants_count.get('women'))
        children = safe_int(participants_count.get('children'))

        total = men + women + children
        # Only override if total is greater than 0
        if total > 0:
            participants_count['total'] = total
    except Exception as e:
        logger.info(f"Error overriding total participants count: {e}")

    return participants_count


def update_or_create_story_translation(story, company_bot):
    """Create or update translation - only processes participant_count without translation"""
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

        # Process participant count if it exists
        translated_other_params = {}

        if story.other_params and 'participants_count' in story.other_params:
            participant_count_value = story.other_params.get('participants_count')
            if participant_count_value:
                # Process participant count to ensure proper structure
                processed_count = process_participants_count(participant_count_value)
                translated_other_params['participants_count'] = processed_count

        # Get or create StoryTranslation
        story_translation, created = StoryTranslation.objects.get_or_create(
            story=story,
            language=session_language,
            defaults={'other_params': translated_other_params}
        )

        # Update if already exists and there are changes
        if not created:
            # Only update participant_count if it exists
            if 'participants_count' in translated_other_params:
                if not story_translation.other_params:
                    story_translation.other_params = {}
                story_translation.other_params['participants_count'] = translated_other_params['participants_count']
                story_translation.save()
                logger.info(f"Updated participant_count for StoryTranslation ID {story_translation.id}")
        else:
            logger.info(f"Created new StoryTranslation ID {story_translation.id} with participant_count")

    except Exception as e:
        logger.error(f"Error creating/updating translation for Story ID {story.id}: {str(e)}")


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


def correct_metadata_for_story(story):
    """Get participant count from LLM and update story"""
    try:
        if not story.other_params:
            return f"🟡 Story ID {story.id}: No other_params"

        company_bot = CompanyBot.objects.get(route='/chaupal-onetime-script')

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

        # Extract participants_count from LLM response
        if result and isinstance(result, dict):
            participants_count_from_llm = result.get('participants_count')

            if participants_count_from_llm:
                # Process the participant count from LLM
                processed_count = process_participants_count(participants_count_from_llm)

                # Update story's other_params
                story.other_params['participants_count'] = processed_count
                updated = True
                logger.info(f"Updated participants_count for Story ID {story.id}: {processed_count}")

        if updated:
            story.save(update_fields=['other_params'])
            logger.info(f"✅ Updated Story ID {story.id} with new participant count")

            # Update translation
            update_or_create_story_translation(story, company_bot)

            return f"✅ Updated Story ID {story.id} with participant count from LLM"
        else:
            return f"🟡 Story ID {story.id}: No participant count found in LLM response"

    except Exception as e:
        logger.error(f"❌ Error in Story ID {story.id}: {str(e)}")
        return f"❌ Error in Story ID {story.id}: {str(e)}"


def clean_all_stories(start=0, end=100):
    """Clean stories in a specific range"""
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
        start_time = make_aware(datetime(2025, 9, 16, 0, 0))
    if not end_time:
        end_time = make_aware(datetime(2025, 9, 30, 23, 59, 59))
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


def get_pricing_from_company_bot(company_bot, model_id):
    """Extract pricing from company_bot.other_params"""
    try:
        if not company_bot.other_params:
            return None

        # Parse other_params
        if isinstance(company_bot.other_params, str):
            other_params = json.loads(company_bot.other_params)
        else:
            other_params = company_bot.other_params

        # Check if pricing data exists
        pricing_data = other_params.get('model_pricing')
        if not pricing_data:
            logger.info(f"❌ No pricing_data key found in company bot other params.")
            return None

        logger.info(f"🔍 Searching for model_id: '{model_id}'")
        logger.info(f"🔍 Available pricing keys: {list(pricing_data.keys())}")

        # Get pricing for current model
        model_pricing = pricing_data.get(model_id)
        if not model_pricing:
            logger.info(f"❌ No exact match found for: '{model_id}'")
            model_pricing = pricing_data.get('llama3-3-70b')

        if model_pricing and 'input_cost_per_1k' in model_pricing and 'output_cost_per_1k' in model_pricing:
            return {
                'input': float(model_pricing['input_cost_per_1k']),
                'output': float(model_pricing['output_cost_per_1k'])
            }

        return None

    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
        logger.error(f"Error parsing pricing from company_bot.other_params: {e}")
        return None

def get_clean_output(response):
    """
    Clean and format LLM response, recursively unwrapping 'type':'object' -> 'value' structures.

    Handles:
    - Top-level response being a type-object.
    - Nested fields like participants_count.total, participants_count.women, etc.
    - Lists and dicts with any level of nesting.
    """
    if response and isinstance(response, dict):
        # Extract 'parameters' or 'input' if present (LLM function response)
        extracted_data = response.pop("parameters", response.pop("input", None))
        if extracted_data and isinstance(extracted_data, dict):
            response.clear()
            response.update(extracted_data)

    response_json_content = response

    # If response is a string, try to repair JSON
    if response_json_content and isinstance(response_json_content, str):
        response_json_content = json_repair.repair_json(response_json_content, return_objects=True)

    # Recursive unwrapping function
    def unwrap_type_object(obj):
        if isinstance(obj, dict):
            # Unwrap if the dict itself is a type-object
            while obj.get('type') == 'object' and 'value' in obj:
                obj = obj['value'] if obj['value'] is not None else {}
            # Recursively unwrap all dict values
            for k, v in obj.items():
                obj[k] = unwrap_type_object(v)
            return obj
        elif isinstance(obj, list):
            return [unwrap_type_object(item) for item in obj]
        else:
            return obj

    response_json_content = unwrap_type_object(response_json_content)

    return response_json_content

# Usage instructions:
# Step 1: Get story IDs for a date range
# story_ids = get_story_count(start_time, end_time)
#
# Step 2: Clean the specific stories
# clean_specific_stories(story_ids)
#
# Or clean all stories in a range:
# clean_all_stories(start=0, end=100)