from celery import shared_task

from chatbot.services.core.bot_service_factory import BotServiceFactory
from chatbot.services.core.orchestrator import ChatOrchestrator
import logging

logger = logging.getLogger('django')


@shared_task
def get_flow_response(channel_name, session_id, profile_id, route, bot_type, bot_route):
    """Common bot task"""
    print(f"bot_type is {bot_type} and bot_route is {bot_route}")
    bot_strategy = BotServiceFactory.create_bot_service(
        bot_type=bot_type, route=bot_route
    )
    orchestrator = ChatOrchestrator(bot_strategy=bot_strategy)
    return orchestrator.process_chat_request(
        channel_name=channel_name, session_id=session_id, profile_id=profile_id,
        language=route
    )
