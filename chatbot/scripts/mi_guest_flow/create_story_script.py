from chatbot.models import Story, ChatSession, CompanyBot, ChatStatus, SessionFlowName
from chatbot.models.company_models import CompanyStateMachine
import logging
from django.utils.timezone import make_aware
from datetime import datetime
from chatbot.utils.story_utils.story_utils import create_story_object

logger = logging.getLogger('django')

###Steps To Follow:
    #First step is to call get_session_count() for given bots (Adjust the date as needed)
    #Second step is to call create_specific_stories() and pass the valid session data we collected in First Step to
    #create missing stories


def get_session_count():
    start_time = make_aware(datetime(2025, 6, 1, 0, 0))
    end_time = make_aware(datetime(2025, 7, 10, 23, 59, 59))

    bots = CompanyBot.objects.filter(route__in=["/oneshot_guest", "/guided_guest"])

    bot_steps_map = {
        bot.id: CompanyStateMachine.objects.filter(company_bot=bot).count()
        for bot in bots
    }

    print("bot_steps_map: ", bot_steps_map)

    sessions = ChatSession.objects.filter(
        created_at__range=(start_time, end_time),
        company_bot__in=bots
    ).exclude(
        session_status=ChatStatus.COMPLETED
    ).order_by('created_at').select_related('profile')

    valid_sessions = [
        session for session in sessions
        if (
            session.current_step is not None
            and bot_steps_map.get(session.company_bot_id) is not None
            and session.current_step >= bot_steps_map[session.company_bot_id]
            and not Story.objects.filter(session=session.session).exists()
        )
    ]

    if valid_sessions:
        print("First valid session:", valid_sessions[0].session)
        print("Last valid session:", valid_sessions[-1].session)
    else:
        print("No valid sessions found.")

    return valid_sessions


def create_specific_stories(sessions, access_token):
    """
    For each valid ChatSession:
    - Pick profile_id, session string, and other context
    - Create story
    - Fix metadata
    - Collect success and failure lists
    """
    succeeded_sessions = []
    failed_sessions = []

    for session in sessions:
        try:
            profile_id = session.profile.id if session.profile else None
            session_str = session.session
            print(f"session.language: {session.language}")
            language = session.language if session.language else "en"
            flow = session.session_type
            existing_story = Story.objects.filter(session=session_str).first()
            if existing_story and existing_story.other_params and existing_story.other_params.get('flow'):
                flow = existing_story.other_params.get('flow')

            valid_flows = [choice[0] for choice in SessionFlowName.choices]
            if flow not in valid_flows:
                print(f"❌ Invalid flow '{flow}' for session {session_str}, failing session")
                failed_sessions.append(session_str)
                continue

            print(f"Passing, profile_id: {profile_id} & session_str: {session_str} & access_token: {access_token} & "
                  f"flow: {flow} & language: {language}")
            story_id, content, error_msg = create_story_object(
                profile_id=profile_id,
                session=session_str,
                access_token=access_token,
                flow=flow,
                language=language
            )

            if story_id:
                print(f"✅ Story created for session {session_str}: ID = {story_id}")
                succeeded_sessions.append(session_str)
            else:
                print(f"❌ Failed to create story for session {session_str}: {error_msg}")
                failed_sessions.append(session_str)

        except Exception as e:
            print(f"🔥 Exception for session {session.session}: {str(e)}")
            failed_sessions.append(session.session)

    print(f"\n✅ Succeeded sessions: {succeeded_sessions}")
    print(f"❌ Failed sessions: {failed_sessions}")

    return succeeded_sessions, failed_sessions

