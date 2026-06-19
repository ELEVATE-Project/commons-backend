import re
from chatbot.models import Story, SessionFlowName, ChatSession

# English letters (Hinglish allowed)
ENGLISH_LETTER_REGEX = re.compile(r'[A-Za-z]')

# Any alphabetic letter (Latin + Devanagari)
ANY_LETTER_REGEX = re.compile(r'[A-Za-z\u00C0-\u024F\u0900-\u097F]')

# Text fields in Story model
TEXT_FIELDS = [
    "title",
    "content",
    "blurb",
    "tweet",
    "objective",
    "action_steps",
    "impact",
    "micro_improvement",
    "location",
    "district",
    "state",
    "block",
    "formatted_content",
    "summary",
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


def contains_non_english_in_json(obj):
    """
    Recursively scan JSON (dict / list / str) for non-English text.
    """
    if isinstance(obj, str):
        return has_non_english_letters(obj)

    if isinstance(obj, dict):
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
        other_params__flow=SessionFlowName.GuestDiscussion
    )

    total_stories = stories.count()

    non_english_story_ids = []
    non_english_but_session_en_ids = []

    for story in stories:
        found_non_english = False

        # 1. Check Story fields
        for field in TEXT_FIELDS:
            value = getattr(story, field, None)
            if has_non_english_letters(value):
                found_non_english = True
                break

        # 2. Check other_params JSON
        if not found_non_english and story.other_params:
            if contains_non_english_in_json(story.other_params):
                found_non_english = True

        if found_non_english:
            non_english_story_ids.append(story.id)

            # 🔹 NEW METRIC: ChatSession.language == 'en'
            chat_session = ChatSession.objects.filter(
                session=story.session
            ).only("language").first()

            if chat_session and chat_session.language == "en":
                non_english_but_session_en_ids.append(story.id)

    # ---------- STATS ----------
    non_english_count = len(non_english_story_ids)
    non_english_but_en_count = len(non_english_but_session_en_ids)

    print("====================================")
    print("Flow:", SessionFlowName.GuestDiscussion)
    print("Total stories:", total_stories)

    print("\n--- Non-English Content ---")
    print("Count:", non_english_count)
    percentage = round((non_english_count / total_stories) * 100, 2) if total_stories else 0
    print("Percentage:", f"{percentage}%")
    print("Story IDs:", non_english_story_ids)

    print("\n--- Non-English BUT ChatSession.language = 'en' ---")
    print("Count:", non_english_but_en_count)
    percentage_en = round((non_english_but_en_count / total_stories) * 100, 2) if total_stories else 0
    print("Percentage:", f"{percentage_en}%")
    print("Story IDs:", non_english_but_session_en_ids)

    print("====================================")


# Run
count_non_english_stories()
