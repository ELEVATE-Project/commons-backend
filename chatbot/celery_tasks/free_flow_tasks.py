from celery import shared_task
from chatbot.services.free_flow.free_flow_service import FreeFlowService
import logging

logger = logging.getLogger('django')


@shared_task
def get_free_flow_response(channel_name, session_id, profile_id, route, bot_route):
    """
    Celery task for free-flow responses.
    """
    logger.info(f"Free flow task started for session {session_id}, channel {channel_name}")
    
    service = FreeFlowService()
    service.process_and_stream(
        channel_name=channel_name,
        session_id=session_id,
        profile_id=profile_id,
        route=route,
        bot_route=bot_route
    )
    
    logger.info(f"Free flow task completed for session {session_id}")
    return "Free flow response completed"
