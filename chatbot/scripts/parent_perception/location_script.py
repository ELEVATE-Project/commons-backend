import json
import os
import sys
import django

# Setup Django if running directly (not in Django shell)
if __name__ == "__main__":
    try:
        # Check if Django is already configured (running in shell)
        django.apps.apps.check_apps_ready()
    except Exception:
        # Add project root to path
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        except NameError:
            # If __file__ is not defined (pasted in shell), use current directory
            project_root = os.getcwd()
        
        sys.path.insert(0, project_root)
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'shikshalokam_mohini.settings')
        django.setup()

from chatbot.models import ChatSession, ChatType, CompanyChat


def get_target_sessions(session_id=None):
    qs = ChatSession.objects.filter(
        session_type=ChatType.ParentPerceptionSurvey
    )

    if not session_id:
        return qs

    if isinstance(session_id, list):
        return qs.filter(session__in=session_id)

    return qs.filter(session=session_id)


def get_chat_text(chat):
    if chat.translated_message:
        return chat.translated_message.strip()

    if chat.message:
        return chat.message.strip()

    return ""


def extract_location_from_chats(chat_session):
    chats = CompanyChat.objects.filter(
        session=chat_session.session,
        receiver=1
    ).order_by("created_at")[:2]

    state = ""
    district = ""

    for chat in chats:
        text = get_chat_text(chat)
        if not text:
            continue

        if not state:
            state = text.lower()
            continue

        if not district:
            district = text.lower()

    if state and district:
        return f"{state} {district}"

    return ""


def extract_ip_location(chat_session):
    other_params = chat_session.other_params or {}
    ip_data = other_params.get("ip_address", {})

    ip_city = ip_data.get("ipCity", "")
    ip_state = ip_data.get("ipState", "")

    parts = [p for p in [ip_state, ip_city] if p]
    return " ".join(parts)


def build_location_response(chat_session):
    return {
        "session_id": chat_session.session,
        "user_chat_location": extract_location_from_chats(chat_session),
        "ip_location": extract_ip_location(chat_session),
    }


def get_parent_perception_location_metadata(session_id=None):
    sessions = get_target_sessions(session_id)

    results = []
    for chat_session in sessions:
        results.append(build_location_response(chat_session))

    return results


def save_to_json_file(session_id=None):
    """
    Save location metadata to a static JSON file in current directory
    """
    results = get_parent_perception_location_metadata(session_id)
    
    # Use static filename in current directory
    file_path = "parent_perception_locations.json"
    
    # Save to file
    with open(file_path, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"✓ Saved {len(results)} location records to: {os.path.abspath(file_path)}")
    return os.path.abspath(file_path)


def run():
    """
    Run the script - prints to terminal and saves to parent_perception_locations.json
    """
    results = get_parent_perception_location_metadata()
    
    # Print to terminal
    print("\n" + "="*60)
    print("PARENT PERCEPTION LOCATION METADATA")
    print("="*60)
    print(json.dumps(results, indent=2))
    print("="*60)
    print(f"Total records: {len(results)}\n")
    
    # Save to file
    file_path = save_to_json_file()
    
    return {
        "results": results,
        "file_path": file_path
    }


# Allow running directly
if __name__ == "__main__":
    run()

