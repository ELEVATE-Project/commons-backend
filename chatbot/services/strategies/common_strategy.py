from chatbot.services.strategies.base_strategy import BotStrategy


class CommonBotStrategy(BotStrategy):
    """Common Strategy for bot functionality"""

    def get_default_route(self):
        return ''

    def get_handler_type(self):
        return 'common'

    def process_session(self, session_data, **kwargs):
        """Handle common session processing"""
        chat_session = session_data['chat_session']
        company_bot = session_data['company_bot']

        try:
            from chatbot.models.company_models import CompanyStateMachine
            state_machine = CompanyStateMachine.objects.filter(
                company_bot=company_bot, step=chat_session.current_step
            ).first()
            return {'state_machine': state_machine}
        except Exception as e:
            return {'error': f"State machine error: {e}"}

    def get_response(self, **kwargs):
        """Get guided guest bot response using handler"""
        return self.response_handler.handle_response(**kwargs)
