from celery import shared_task
from chatbot.utils.story_utils.story_utils import create_story_object


@shared_task
def create_ptm_report(profile_id, session, flow, language):
    id, content, error_msg = create_story_object(
        profile_id=profile_id,
        session=session,
        access_token=None,
        flow=flow,
        language=language
    )
    return {"id": id, "error_msg": error_msg}
