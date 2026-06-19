from chatbot.llm_models.llm_script import handle_bedrock_model
from chatbot.models import CompanyBot, Story, StoryTranslation, ChatSession
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.db import transaction
from tqdm import tqdm
from typing import List, Dict, Any
import json
import json_repair
import logging
import os

# -------------- CONFIG ------------------
MASTER_VILLAGES_FILE = 'chatbot/scripts/guest_discussion/master_villages.json'
MAX_WORKERS = 4
BATCH_SIZE = 20
llm_retry_number = int(os.getenv('LLM_RETRY_NUMBER', 3))
AWS_KEY = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')

logger = logging.getLogger('django')


# -------------- LLM CALL ------------------

def build_prompt(location: str, master_villages: Dict[str, List[str]]) -> List[Dict[str, Any]]:
    """Build prompt for village name mapping"""

    # Format the master villages data for the prompt
    villages_text = ""
    for district, villages in master_villages.items():
        villages_list = ", ".join(villages)
        villages_text += f"\n{district.upper()} district: {villages_list}"

    message = f"""
    MASTER VILLAGES LIST (by district):
    {villages_text}

    LOCATION TO MAP: "{location}"
    """

    return [{"role": "user", "content": [{"text": message.strip()}]}]


def chunk_data(data: List[Any], batch_size: int) -> List[List[Any]]:
    """Split data into chunks for parallel processing"""
    return [data[i:i + batch_size] for i in range(0, len(data), batch_size)]


def load_master_villages() -> Dict[str, List[str]]:
    """Load master villages JSON file"""
    try:
        with open(MASTER_VILLAGES_FILE, "r", encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ Master villages file not found: {MASTER_VILLAGES_FILE}")
        return {}
    except json.JSONDecodeError:
        print(f"❌ Invalid JSON in master villages file: {MASTER_VILLAGES_FILE}")
        return {}


def process_stories_parallel(stories: List[Story], master_villages: Dict[str, List[str]]) -> Dict[str, List[int]]:
    """Process stories in parallel batches"""

    if not master_villages:
        print("❌ No master villages data available")
        return {"skipped_no_location": [], "failed_village_mapping": []}

    # Filter stories and track skipped ones
    stories_to_process = []
    skipped_no_location = []

    for story in stories:
        if story.other_params:
            # Only check location from other_params, NOT from english_json
            location = story.other_params.get('location')

            if not location:
                skipped_no_location.append(story.id)
                continue

            # Check if village mapping already exists
            if 'village' not in story.other_params:
                stories_to_process.append(story)

    print(f"📊 Summary:")
    print(f"   - Total stories: {len(stories)}")
    print(f"   - Skipped (no location): {len(skipped_no_location)}")
    print(f"   - To process: {len(stories_to_process)}")

    if not stories_to_process:
        print("✅ No stories need village mapping")
        return {
            "skipped_no_location": skipped_no_location,
            "failed_village_mapping": []
        }

    story_batches = chunk_data(stories_to_process, BATCH_SIZE)

    print(
        f"🔧 Processing {len(stories_to_process)} stories in {len(story_batches)} batches with {MAX_WORKERS} workers (batch size = {BATCH_SIZE})...")

    def process_one_batch(batch: List[Story]) -> Dict[str, List]:
        batch_results = []
        batch_failed = []
        for story in batch:
            result = call_llm_for_village_mapping(story, master_villages)
            if result:
                batch_results.append(result)
            else:
                batch_failed.append(story.id)
        return {"successful": batch_results, "failed": batch_failed}

    all_updates = []
    failed_village_mapping = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_one_batch, batch) for batch in story_batches]

        for future in tqdm(as_completed(futures), total=len(futures), desc="Processing Story Batches"):
            batch_output = future.result()
            all_updates.extend(batch_output["successful"])
            failed_village_mapping.extend(batch_output["failed"])

    # Bulk update stories
    update_stories_in_db(all_updates)

    # Final summary
    print(f"\n📋 FINAL SUMMARY:")
    print(f"   ✅ Successfully processed: {len(all_updates)} stories")
    print(f"   ⚠️  Skipped (no location): {len(skipped_no_location)} stories")
    print(f"   ❌ Failed village mapping: {len(failed_village_mapping)} stories")

    return {
        "skipped_no_location": skipped_no_location,
        "failed_village_mapping": failed_village_mapping
    }


def call_llm_for_village_mapping(story: Story, master_villages: Dict[str, List[str]]) -> Dict[str, Any]:
    """Call LLM to map story location to village name"""

    try:
        # Get location ONLY from other_params, NOT from english_json
        location = ''
        if story.other_params:
            location = story.other_params.get('location', '')

        if not location:
            print(f"⚠️  Story {story.id}: No location found in other_params")
            return None

        messages = build_prompt(location, master_villages)
        company_bot = CompanyBot.objects.filter(route='/script_village_mapping').first()

        if not company_bot:
            print("❌ No bot found for route '/script_village_mapping'")
            return None

        tools = company_bot.tool_context
        if tools and isinstance(tools, str):
            tools = json_repair.repair_json(tools, return_objects=True)

        formatted_prompt = [{"text": company_bot.context}]
        response = handle_bedrock_model(
            system_prompt=formatted_prompt,
            messages=messages,
            model_name=company_bot.llm_model,
            temperature=company_bot.bot_temperature,
            max_token=company_bot.max_token,
            company_bot=company_bot,
            tools=tools
        )
        print("----------------------------------")
        print("response: ", response)
        cleaned_response = get_clean_output(response=response)
        print("cleaned_response: ", cleaned_response)
        print("----------------------------------")

        if cleaned_response and isinstance(cleaned_response, dict):
            village_name = cleaned_response.get('village', 'others')
            district_name = cleaned_response.get('district', 'others')

            mapped_key = ''
            for key, villages in master_villages.items():
                if village_name in villages:
                    mapped_key = key
                    break

            return {
                'story_id': story.id,
                'village': mapped_key,
                'district': mapped_key,
                'original_location': location
            }

        print(f"❌ Story {story.id}: Failed to get valid response from LLM")
        return None

    except Exception as e:
        print(f"❌ Error processing story {story.id}: {e}")
        return None


def get_story_language_from_session(story_id: int) -> str:
    """Get the language from the story's chat session"""
    try:
        story = Story.objects.get(id=story_id)

        if hasattr(story, 'session'):
            chat_session = ChatSession.objects.filter(session=story.session).first()
            if chat_session and hasattr(chat_session, 'language'):
                return chat_session.language

        # Default to story's language if no session found
        return story.language
    except Exception as e:
        print(f"Error getting language from session for story {story_id}: {e}")
        return 'en'  # Default to English


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
            from chatbot.utils.transliterate_utils import get_transliteration_output
            data = get_transliteration_output(response.get('content'))
            return data if data else response.get('content')
        else:
            print(f"Transliteration failed, using original text: {message_body}")
            return message_body
    except Exception as e:
        print(f"Error transliterating text '{message_body}': {str(e)}")
        return message_body


def update_story_translations(story_id: int, village: str, district: str, voice_provider: str = "google") -> None:
    """Update StoryTranslation with transliterated village and district names"""
    try:
        story = Story.objects.get(id=story_id)

        # Get language from chat session
        session_language = get_story_language_from_session(story_id)

        # Get all existing translations for this story
        translations = StoryTranslation.objects.filter(story=story)

        for translation in translations:
            # Transliterate village and district names
            if village and str(village).lower() not in ['others', 'other']:
                transliterated_village = transliterate_field(
                    voice_provider=voice_provider,
                    message_body=village,
                    target_language=translation.language,
                    source_language=session_language
                )
            else:
                transliterated_village = village

            if district and str(district).lower() not in ['others', 'other']:
                transliterated_district = transliterate_field(
                    voice_provider=voice_provider,
                    message_body=district,
                    target_language=translation.language,
                    source_language=session_language
                )
            else:
                transliterated_district = district

            # Update translation's other_params (get_or_update, don't create)
            if not translation.other_params:
                translation.other_params = {}

            translation.other_params['village'] = transliterated_village
            translation.other_params['district'] = transliterated_district

            translation.save(update_fields=['other_params'])

            print(f"✅ Updated translation for story {story_id} in {translation.language}: "
                  f"{village} -> {transliterated_village}, {district} -> {transliterated_district}")

    except Story.DoesNotExist:
        print(f"❌ Story {story_id} not found for translation update")
    except Exception as e:
        print(f"❌ Error updating translations for story {story_id}: {e}")


def update_stories_in_db(updates: List[Dict[str, Any]]) -> None:
    """Bulk update stories in database"""

    try:
        with transaction.atomic():
            for update in updates:
                story_id = update['story_id']
                village = update['village']
                district = update['district']

                try:
                    story = Story.objects.get(id=story_id)
                    if not story.other_params:
                        story.other_params = {}

                    # Update ONLY in other_params, NOT in english_json
                    story.other_params['village'] = village
                    story.other_params['district'] = district

                    story.save(update_fields=['other_params'])

                    print(f"✅ Updated story {story_id}: {update['original_location']} -> {village}, {district}")

                    # Update translations with transliterated values
                    update_story_translations(story_id, village, district)

                except Story.DoesNotExist:
                    print(f"❌ Story {story_id} not found")
                except Exception as e:
                    print(f"❌ Error updating story {story_id}: {e}")

    except Exception as e:
        print(f"❌ Database transaction error: {e}")


# -------------- MAIN ------------------

def run_village_mapper(story_queryset=None, master_villages=None) -> Dict[str, List[int]]:
    """Main function to run village mapping"""

    # Use passed master_villages, fallback to loading from file
    if master_villages is None:
        master_villages = load_master_villages()

    if not master_villages:
        return {"skipped_no_location": [], "failed_village_mapping": []}

    # Get stories to process
    if story_queryset is None:
        stories = Story.objects.filter(
            other_params__isnull=False
        ).exclude(
            other_params__village__isnull=False
        )
    else:
        stories = story_queryset

    stories_list = list(stories)
    print(f"🚀 Found {len(stories_list)} stories to analyze")

    if not stories_list:
        print("✅ No stories found to process")
        return {"skipped_no_location": [], "failed_village_mapping": []}

    return process_stories_parallel(stories_list, master_villages)


# -------------- UTILITY FUNCTIONS ------------------

def retry_if_result_none(result):
    return result is None


def get_clean_output(response):
    """Clean and extract output from LLM response"""
    print("Type of response: ", type(response))
    if response and isinstance(response, dict):
        extracted_data = response.pop("parameters", response.pop("input", None))
        print("extracted_data: ", extracted_data, " & type: ", type(extracted_data))
        if extracted_data and isinstance(extracted_data, dict):
            response.clear()
            response.update(extracted_data)

    response_json_content = response
    if response_json_content and isinstance(response_json_content, str) and "{" in response_json_content:
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


# -------------- ANALYSIS FUNCTIONS ------------------

def analyze_skipped_stories(story_ids: List[int]) -> None:
    """Analyze stories that were skipped due to missing location"""
    if not story_ids:
        print("✅ No stories were skipped")
        return

    stories = Story.objects.filter(id__in=story_ids)

    print(f"\n🔍 ANALYSIS OF SKIPPED STORIES ({len(story_ids)} total):")
    print("=" * 50)

    for story in stories[:10]:  # Show first 10 as sample
        location = story.other_params.get('location', 'N/A') if story.other_params else 'N/A'
        print(f"Story ID: {story.id}")
        print(f"  Location: {location}")
        print("-" * 30)

    if len(stories) > 10:
        print(f"... and {len(stories) - 10} more stories")


def analyze_failed_stories(story_ids: List[int]) -> None:
    """Analyze stories that failed village mapping"""
    if not story_ids:
        print("✅ No stories failed village mapping")
        return

    stories = Story.objects.filter(id__in=story_ids)

    print(f"\n🔍 ANALYSIS OF FAILED STORIES ({len(story_ids)} total):")
    print("=" * 50)

    for story in stories[:10]:  # Show first 10 as sample
        location = story.other_params.get('location', 'N/A') if story.other_params else 'N/A'
        print(f"Story ID: {story.id}")
        print(f"  Location: {location}")
        print("-" * 30)

    if len(stories) > 10:
        print(f"... and {len(stories) - 10} more stories")


def get_village_mapping_stats() -> Dict[str, Any]:
    """Get statistics about village mappings"""
    total_stories = Story.objects.filter(other_params__isnull=False).count()

    stories_with_village = Story.objects.filter(
        other_params__village__isnull=False
    ).count()

    # Get village distribution
    village_distribution = {}
    stories_with_villages = Story.objects.filter(
        other_params__village__isnull=False
    ).values_list('other_params', flat=True)

    for other_params in stories_with_villages:
        village = other_params.get('village', 'unknown')
        village_distribution[village] = village_distribution.get(village, 0) + 1

    # Get translation stats
    translations_with_village = StoryTranslation.objects.filter(
        other_params__village__isnull=False
    ).count()

    stats = {
        'total_stories_with_other_params': total_stories,
        'stories_with_village_mapping': stories_with_village,
        'translations_with_village': translations_with_village,
        'village_distribution': village_distribution,
        'most_common_villages': sorted(village_distribution.items(), key=lambda x: x[1], reverse=True)[:10]
    }

    print(f"\n📊 VILLAGE MAPPING STATISTICS:")
    print("=" * 40)
    print(f"Total stories with other_params: {stats['total_stories_with_other_params']}")
    print(f"Stories with village mapping: {stats['stories_with_village_mapping']}")
    print(f"Translations with village mapping: {stats['translations_with_village']}")
    print(f"Unique villages mapped: {len(village_distribution)}")
    print(f"\nTop 10 villages:")
    for village, count in stats['most_common_villages']:
        print(f"  {village}: {count} stories")

    return stats


# -------------- USAGE EXAMPLES ------------------

def run_for_specific_stories(story_ids: List[int], master_villages=None) -> Dict[str, List[int]]:
    """Run village mapping for specific story IDs"""
    if master_villages is None:
        master_villages = load_master_villages()
    
    if not master_villages:
        return {"skipped_no_location": [], "failed_village_mapping": []}

    stories = Story.objects.filter(id__in=story_ids)
    summary = run_village_mapper(story_queryset=stories, master_villages = master_villages)

    # Analyze results
    analyze_skipped_stories(summary['skipped_no_location'])
    analyze_failed_stories(summary['failed_village_mapping'])

    return summary


def run_for_date_range(start_date, end_date) -> Dict[str, List[int]]:
    """Run village mapping for stories in date range"""
    stories = Story.objects.filter(
        created_at__gte=start_date,
        created_at__lte=end_date,
        other_params__isnull=False
    ).exclude(
        other_params__village__isnull=False
    )
    summary = run_village_mapper(story_queryset=stories)

    # Analyze results
    analyze_skipped_stories(summary['skipped_no_location'])
    analyze_failed_stories(summary['failed_village_mapping'])

    return summary