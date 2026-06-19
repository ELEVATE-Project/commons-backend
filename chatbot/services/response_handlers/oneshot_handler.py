from chatbot.models import ChatStatus
from chatbot.models.company_models import CompanyStateMachine
from chatbot.services.response_handlers.base_response_handler import BaseResponseHandler


class OneShotResponseHandler(BaseResponseHandler):
    """Response handler for oneshot bot"""

    def check_early_return(self, chat_session, **kwargs):
        """Check if should return initial bot question"""
        messages = kwargs['messages']
        intro_mssg = kwargs.get('intro_mssg')
        remaining_stages = kwargs['remaining_stages']

        # Early return condition for oneshot
        if ((intro_mssg is None and len(messages) < 2) or
                (intro_mssg is not None and len(messages) <= 3)):
            return self._handle_initial_question(
                chat_session=chat_session, remaining_stages=remaining_stages, session_id=kwargs['session_id'],
                channel_name=kwargs['channel_name'], language=kwargs['language'], profile_id=kwargs['profile_id'],
                company_bot=kwargs['company_bot']
            )
        return None

    def get_messages_for_llm(self, **kwargs):
        """Use temp_messages if available, otherwise original messages"""
        temp_messages = kwargs.get('temp_messages')
        messages=kwargs.get('messages')
        return temp_messages if temp_messages else messages

    def process_response(self, response, chat_session, chunks, **kwargs):
        """Process oneshot response"""
        skip_llm_call = kwargs.get('skip_llm', False)
        
        remaining_stages = kwargs['remaining_stages']
        channel_name = kwargs['channel_name']
        company_bot = kwargs['company_bot']
        session_id = kwargs['session_id']
        language = kwargs['language']
        profile_id = kwargs['profile_id']

        current_step = chat_session.current_step
        if skip_llm_call:
            is_func_call = True
        else:
            is_func_call = self.is_function_call(response=response)

        if is_func_call and remaining_stages:
            return self._handle_function_call(
                response=response, chat_session=chat_session, company_bot=company_bot,
                session_id=session_id, channel_name=channel_name, language=language, profile_id=profile_id,
                chunks=chunks, remaining_stages=remaining_stages
            )
        else:
            return self._handle_regular_response(
                response=response, chat_session=chat_session, company_bot=company_bot,
                session_id=session_id, channel_name=channel_name, language=language, profile_id=profile_id,
                chunks=chunks, current_step=current_step
            )

    def _handle_initial_question(self, chat_session, remaining_stages, session_id,
                                 channel_name, language, profile_id, company_bot):
        """Handle initial bot question for oneshot"""
        current_stage_name = remaining_stages[0]
        state_machine = CompanyStateMachine.objects.get(
            company_bot=company_bot, name=current_stage_name
        )
        bot_question = state_machine.bot_question

        translated_message = self.translate_message(
            message=bot_question, channel_name=channel_name, step_number=chat_session.current_step,
            language=language, company_bot=company_bot
        )

        self.save_message(
            session_id=session_id, profile_id=profile_id, message=bot_question, chunks=[],
            status=ChatStatus.IN_PROGRESS, translated_message=translated_message, stage=state_machine.name
        )

        return bot_question

    def _handle_function_call(self, response, chat_session, company_bot,
                              session_id, channel_name, language, profile_id,
                              chunks, remaining_stages):
        """Handle function call for oneshot"""
        remaining_stages.pop(0)
        current_stage_name = remaining_stages[0]

        state_machine = CompanyStateMachine.objects.get(
            company_bot=company_bot, name=current_stage_name
        )

        # Update session
        chat_session.session_context['remaining_stages'] = remaining_stages
        chat_session.current_step = state_machine.step
        chat_session.save()

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
        """Handle regular response for oneshot"""
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
