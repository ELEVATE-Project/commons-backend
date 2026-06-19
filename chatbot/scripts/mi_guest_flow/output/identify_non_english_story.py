import re
from chatbot.models import Story, SessionFlowName, ChatSession

# English letters (Hinglish allowed)
ENGLISH_LETTER_REGEX = re.compile(r'[A-Za-z]')

# Any alphabetic letter (Latin + Devanagari + other scripts)
ANY_LETTER_REGEX = re.compile(r'[A-Za-z\u00C0-\u024F\u0900-\u097F]')

# Text fields in Story model for GuestMiStory
TEXT_FIELDS = [
    "title",
    "content",
    "blurb",
    "tweet",
    "objective",
    "action_steps",  # Can be string or list
    "impact",
    "micro_improvement",
    "location",
    "district",
    "state",
    "block",
    "formatted_content",
    "summary",
]

# Other_params fields specific to GuestMiStory
OTHER_PARAMS_FIELDS = [
    "user_name",
    "location",
    "organization",
    "designation",
    "duration"
]


def has_non_english_letters(text):
    """
    Returns True ONLY if:
    - text contains alphabetic letters
    - AND contains NO English letters (A-Z)
    """
    if not text or not isinstance(text, str):
        return False

    # Ignore numbers, dates, symbols
    if not ANY_LETTER_REGEX.search(text):
        return False

    # Letters exist but none are English → non-English
    return not ENGLISH_LETTER_REGEX.search(text)


def check_list_for_non_english(lst):
    """Check if any item in list contains non-English text"""
    if not isinstance(lst, list):
        return False

    for item in lst:
        if isinstance(item, str) and has_non_english_letters(item):
            return True
    return False


def contains_non_english_in_json(obj, specific_fields=None):
    """
    Recursively scan JSON (dict / list / str) for non-English text.
    If specific_fields provided, only check those fields in dict.
    """
    if isinstance(obj, str):
        return has_non_english_letters(obj)

    if isinstance(obj, dict):
        if specific_fields:
            # Only check specific fields
            for field in specific_fields:
                value = obj.get(field)
                if value and contains_non_english_in_json(value):
                    return True
        else:
            # Check all fields
            for key, value in obj.items():
                if contains_non_english_in_json(key):
                    return True
                if contains_non_english_in_json(value):
                    return True

    if isinstance(obj, list):
        for item in obj:
            if contains_non_english_in_json(item):
                return True

    return False


def count_non_english_stories():
    stories = Story.objects.filter(
        other_params__flow=SessionFlowName.GuestMiStory
    )

    total_stories = stories.count()

    non_english_story_ids = []
    non_english_but_session_en_ids = []
    field_statistics = {}  # Track which fields have non-English content

    for story in stories:
        found_non_english = False
        non_english_fields = []

        # 1. Check Story fields
        for field in TEXT_FIELDS:
            value = getattr(story, field, None)

            # Special handling for action_steps (can be string or list)
            if field == "action_steps":
                if isinstance(value, str):
                    if has_non_english_letters(value):
                        found_non_english = True
                        non_english_fields.append(field)
                elif isinstance(value, list):
                    if check_list_for_non_english(value):
                        found_non_english = True
                        non_english_fields.append(field)
            else:
                if has_non_english_letters(value):
                    found_non_english = True
                    non_english_fields.append(field)

        # 2. Check specific other_params fields for GuestMiStory
        if story.other_params:
            for param_field in OTHER_PARAMS_FIELDS:
                value = story.other_params.get(param_field)
                if value and has_non_english_letters(value):
                    found_non_english = True
                    non_english_fields.append(f"other_params.{param_field}")

        if found_non_english:
            non_english_story_ids.append(story.id)

            # Track field statistics
            for field in non_english_fields:
                if field not in field_statistics:
                    field_statistics[field] = 0
                field_statistics[field] += 1

            # Check ChatSession.language == 'en'
            chat_session = ChatSession.objects.filter(
                session=story.session
            ).only("language").first()

            if chat_session and chat_session.language == "en":
                non_english_but_session_en_ids.append(story.id)

    # ---------- STATS ----------
    non_english_count = len(non_english_story_ids)
    non_english_but_en_count = len(non_english_but_session_en_ids)

    print("=" * 70)
    print("GUEST MI STORY - NON-ENGLISH CONTENT ANALYSIS")
    print("=" * 70)
    print("Flow:", SessionFlowName.GuestMiStory)
    print("Total stories:", total_stories)

    print("\n--- Non-English Content ---")
    print("Count:", non_english_count)
    percentage = round((non_english_count / total_stories) * 100, 2) if total_stories else 0
    print("Percentage:", f"{percentage}%")

    # Show sample IDs if too many
    if len(non_english_story_ids) > 20:
        print("Sample Story IDs (first 20):", non_english_story_ids[:20])
        print(f"... and {len(non_english_story_ids) - 20} more")
    else:
        print("Story IDs:", non_english_story_ids)

    print("\n--- Field-wise Statistics ---")
    if field_statistics:
        sorted_fields = sorted(field_statistics.items(), key=lambda x: x[1], reverse=True)
        for field, count in sorted_fields:
            field_percentage = round((count / non_english_count) * 100, 2) if non_english_count else 0
            print(f"  {field}: {count} stories ({field_percentage}%)")

    print("\n--- Non-English BUT ChatSession.language = 'en' ---")
    print("Count:", non_english_but_en_count)
    percentage_en = round((non_english_but_en_count / total_stories) * 100, 2) if total_stories else 0
    print("Percentage:", f"{percentage_en}%")

    if len(non_english_but_session_en_ids) > 20:
        print("Sample Story IDs (first 20):", non_english_but_session_en_ids[:20])
        print(f"... and {len(non_english_but_session_en_ids) - 20} more")
    else:
        print("Story IDs:", non_english_but_session_en_ids)

    print("=" * 70)

    return {
        "total": total_stories,
        "non_english_count": non_english_count,
        "non_english_percentage": percentage,
        "non_english_but_en_count": non_english_but_en_count,
        "non_english_but_en_percentage": percentage_en,
        "field_statistics": field_statistics
    }


# Run
if __name__ == "__main__":
    count_non_english_stories()
