from celery import shared_task
from chatbot.services.core.bot_service_factory import BotServiceFactory
from chatbot.services.core.orchestrator import ChatOrchestrator
import logging


logger = logging.getLogger('django')


@shared_task
def get_guided_guest_response(channel_name, session_id, profile_id, route):
    """Guided guest bot task"""
    bot_strategy = BotServiceFactory.create_bot_service(
        bot_type='guided_guest', route='/guided_guest'
    )
    orchestrator = ChatOrchestrator(bot_strategy=bot_strategy)
    return orchestrator.process_chat_request(
        channel_name=channel_name, session_id=session_id, profile_id=profile_id,
        language=route
    )
