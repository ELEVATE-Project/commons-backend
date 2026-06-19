from chatbot.models import ChatStatus
from chatbot.models.company_models import CompanyStateMachine
from chatbot.services.response_handlers.base_response_handler import BaseResponseHandler


class GuidedGuestResponseHandler(BaseResponseHandler):
    """Response handler for guided guest bot"""

    def check_early_return(self, chat_session, **kwargs):
        """No early return for guided guest"""
        return None

    def get_messages_for_llm(self, **kwargs):
        """Use temp_messages if available, otherwise original messages"""
        temp_messages = kwargs.get('temp_messages')
        messages=kwargs.get('messages')
        return temp_messages if temp_messages else messages

    def process_response(self, response, chat_session, chunks, **kwargs):
        """Process guided guest response"""
        skip_llm_call = kwargs.get('skip_llm', False)
        
        current_step = chat_session.current_step
        if skip_llm_call:
            is_func_call = True
        else:
            is_func_call = self.is_function_call(response=response)

        company_bot = kwargs['company_bot']
        session_id = kwargs['session_id']
        language = kwargs['language']
        profile_id = kwargs['profile_id']
        channel_name = kwargs['channel_name']
        target_stage=kwargs.get('target_stage', False)
        skip_next_stage=kwargs.get('skip_next_stage', False)

        if is_func_call:
            return self._handle_function_call(
                response=response, chat_session=chat_session, company_bot=company_bot,
                session_id=session_id, channel_name=channel_name, language=language, profile_id=profile_id,
                chunks=chunks, skip_next_stage=skip_next_stage, target_stage=target_stage
            )
        else:
            return self._handle_regular_response(
                response=response, chat_session=chat_session, company_bot=company_bot,
                session_id=session_id, channel_name=channel_name, language=language, profile_id=profile_id,
                chunks=chunks, current_step=current_step
            )

    def _handle_function_call(self, response, chat_session, company_bot,
                              session_id, channel_name, language, profile_id, chunks, skip_next_stage, target_stage):
        """Handle function call for guided guest"""
        if skip_next_stage:
            if target_stage and isinstance(target_stage, int):
                chat_session.current_step = target_stage
            else:
                chat_session.current_step += 2
        else:
            chat_session.current_step += 1
        chat_session.save()

        state_machine = CompanyStateMachine.objects.get(
            company_bot=company_bot, step=chat_session.current_step
        )
        bot_question = state_machine.bot_question
        chat_status = self.get_chat_status(state_machine=state_machine, company_bot=company_bot)

        translated_message = self.translate_message(
            message=bot_question, channel_name=channel_name, step_number=chat_session.current_step,
            language=language, company_bot=company_bot
        )

        self.save_message(
            session_id=session_id, profile_id=profile_id, message=bot_question, chunks=chunks,
            status=chat_status, translated_message=translated_message, stage=state_machine.name
        )

        return response

    def _handle_regular_response(self, response, chat_session, company_bot,
                                 session_id, channel_name, language, profile_id,
                                 chunks, current_step):
        """Handle regular response for guided guest"""
        state_machine = CompanyStateMachine.objects.get(
            company_bot=company_bot, step=chat_session.current_step
        )

        translated_message = self.translate_message(
            message=response, channel_name=channel_name, step_number=current_step,
            language=language, company_bot=company_bot
        )

        self.save_message(
            session_id=session_id, profile_id=profile_id, message=response, chunks=chunks,
            status=ChatStatus.IN_PROGRESS, translated_message=translated_message, stage=state_machine.name
        )

        return response
