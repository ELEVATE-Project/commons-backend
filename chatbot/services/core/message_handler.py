from chatbot.models import CompanyChat
from chatbot.utils.chat_utils import get_guided_chat


class MessageHandler:
    """Handle message preparation and filtering"""

    @staticmethod
    def prepare_messages(company_bot, company_chats, intro_mssg, other_info=None):
        """Prepare messages for processing"""
        return get_guided_chat(
            company_bot=company_bot,
            company_chats=company_chats,
            intro=intro_mssg,
            other_info=other_info
        )

    @staticmethod
    def get_filtered_chats(session_id, state_machine, company_chats):
        """Get appropriate chats based on state machine settings"""
        if state_machine and state_machine.use_stage_chats:
            return CompanyChat.objects.filter(
                session=session_id,
                stage=state_machine.name
            ).order_by('created_at')
        return company_chats
