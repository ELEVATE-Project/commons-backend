from chatbot.models import ChatStatus, CompanyChat, CompanyBotTypeChoices, LLMProvider, BotVernacular
from chatbot.models.company_models import CompanyStateMachine
from chatbot.services.response_handlers.base_response_handler_new import BaseResponseHandlerNew
from chatbot.utils.shiksha_chaupal.date_utils import handle_date_prompt
from chatbot.celery_tasks.common_chat_tasks import save_in_company_db
from chatbot.celery_tasks.handle_message import translate_and_send_message
import logging
import json
from json_repair import repair_json

logger = logging.getLogger('django')


class CommonResponseHandlerNew(BaseResponseHandlerNew):
    """Common Response handler for bot"""

    def check_early_return(self, chat_session, **kwargs):
        """Check for EVENT state early return"""
        company_bot = kwargs['company_bot']

        try:
            state_machine = CompanyStateMachine.objects.filter(
                company_bot=company_bot, step=chat_session.current_step
            ).first()
            if state_machine and state_machine.name == 'EVENT_DATE':
                print("Here inside")
                return self._handle_event_state(chat_session=chat_session, state_machine=state_machine, **kwargs)
        except Exception as e:
            print("Error: ", e)
            logger.error(f"Error in check_early_return: {e}")

        return None

    def _handle_event_state(self, chat_session, state_machine, **kwargs):
        """Handle EVENT state with date prompt"""
        intro_mssg = kwargs.get('intro_mssg')
        profile = kwargs.get('profile')
        other_info = kwargs.get('other_info')
        channel_name = kwargs['channel_name']
        language = kwargs['language']
        company_bot = kwargs['company_bot']
        session_id = kwargs['session_id']
        profile_id = kwargs['profile_id']
        print("Before date fun")
        company_chats = CompanyChat.objects.filter(session=session_id).order_by('created_at')
        bot_question = handle_date_prompt(
            intro_mssg=intro_mssg,
            profile=profile,
            company_chats=company_chats,
            other_info=other_info
        )
        print("DATE RES: ", bot_question)
        if bot_question is None:
            bot_question = self.default_error_message

        if bot_question == '':
            return {
                "toolUseId": "tooluse_auto_advance",
                "name": "get_state_information",
                "input": {
                    "next_state_name": 'AUTO',
                    "reason": "Date parsed successfully"
                }
            }
        else:
            translated_message = self.translate_message(
                message=bot_question, channel_name=channel_name, step_number=chat_session.current_step,
                language=language, company_bot=company_bot
            )

            stage = state_machine.name if state_machine else None

            self.save_message(
                session_id=session_id, profile_id=profile_id, message=bot_question, chunks=None,
                status=ChatStatus.IN_PROGRESS, translated_message=translated_message, stage=stage
            )

            return bot_question

    def get_messages_for_llm(self, **kwargs):
        """Use temp_messages if available, otherwise original messages"""
        temp_messages = kwargs.get('temp_messages')
        messages = kwargs.get('messages')
        return temp_messages if temp_messages else messages

    def _send_db_question(self, bot_question, chat_session, chunks, **kwargs):
        """Send bot question from database for NON_LLM operations"""
        company_bot = kwargs['company_bot']
        session_id = kwargs['session_id']
        channel_name = kwargs['channel_name']
        language = kwargs['language']
        profile_id = kwargs['profile_id']

        modified_bot_question = kwargs.get('modified_bot_question')
        if modified_bot_question:
            bot_question = modified_bot_question
            logger.info(f"Using modified bot_question from preprocessing: {bot_question[:100]}")

        try:
            state_machine = CompanyStateMachine.objects.get(
                company_bot=company_bot, step=chat_session.current_step
            )
        except CompanyStateMachine.DoesNotExist:
            logger.error(f"State machine not found for step {chat_session.current_step}")
            return self.default_error_message
        
        chat_status = self.get_chat_status(
            state_machine=state_machine, company_bot=company_bot
        )
        
        # Translate and send to WebSocket
        translated_message = self.translate_message(
            message=bot_question,
            channel_name=channel_name,
            step_number=chat_session.current_step,
            language=language,
            company_bot=company_bot
        )
        
        # Save to database with metadata indicating this is a NON_LLM question from DB
        self.save_message(
            session_id=session_id,
            profile_id=profile_id,
            message=bot_question,
            chunks=chunks,
            status=chat_status,
            translated_message=translated_message,
            stage=state_machine.name,
            other_params={
                'message_type': 'question',
                'operation_type': 'non_llm',
                'source': 'database'
            }
        )
        
        logger.info(f"Sent NON_LLM bot question from DB for state: {state_machine.name}")
        return bot_question


    def is_function_call(self, response):
        """Override to handle empty responses as function calls"""
        if super().is_function_call(response):
            return True

        # Check for OpenAI Responses API function call format
        if isinstance(response, dict):
            if response.get('finish_reason') == 'function_call' and 'function_call' in response:
                print("DEBUG: Detected OpenAI Responses API function call format")
                logger.info("Detected OpenAI Responses API function call format")
                return True
            
            if response.get('should_function_call', False):
                print("DEBUG: should_function_call is True, treating as function call")
                logger.info("should_function_call flag is True, treating as function call")
                return True

        try:
            extracted_response, _, meta = self._extract_response_and_reason(response)
            if meta:
                flag = meta.get("should_function_call")
                if isinstance(flag, str):
                    flag = flag.strip().lower() in ("true", "yes", "1")
                if flag is True:
                    print("DEBUG: should_function_call detected via meta in is_function_call")
                    logger.info("should_function_call detected via meta in is_function_call")
                    return True
            if extracted_response == '':
                print(
                    "DEBUG: Empty response detected in is_function_call, treating as function call for postprocessing")
                return True
        except Exception as e:
            print(f"DEBUG: Error in is_function_call extraction: {e}")
            logger.error(f"Error in is_function_call extraction: {e}")

        return False

    def _analyze_response(self, response):
        """
        Analyze response to determine if it's a function call and extract content.
        """
        is_actual_function_call = self.is_function_call(response=response)

        if is_actual_function_call:
            return True, None, None

        extracted_response, reason_text, meta = self._extract_response_and_reason(response)

        if meta:
            flag = meta.get("should_function_call")
            if isinstance(flag, str):
                flag = flag.strip().lower() in ("true", "yes", "1")
            if flag is True:
                print("DEBUG: should_function_call detected via meta in _analyze_response")
                logger.info("should_function_call detected via meta in _analyze_response")
                return True, None, None

        if extracted_response == '':
            print("DEBUG: Empty response detected after extraction, treating as function call for state transition")
            return True, extracted_response, reason_text

        return False, extracted_response, reason_text

    def analyze_response_for_postprocessing(self, response):
        """Override to handle empty responses as function calls for postprocessing"""
        is_function_call, _, _ = self._analyze_response(response)
        return is_function_call

    def process_response(self, response, chat_session, chunks, streaming_completed=False, **kwargs):
        """Process common response with retry logic for short responses"""
        print(f"DEBUG: Starting process_response with response type: {type(response)}")
        print(f"DEBUG: Response preview: {str(response)[:200]}...")
        print(f"DEBUG: kwargs keys: {list(kwargs.keys())}")
        print(f"DEBUG: streaming_completed in kwargs: {'streaming_completed' in kwargs}")
        print(f"DEBUG: streaming_completed value: {kwargs.get('streaming_completed', 'NOT SET')}")

        retry_attempt = kwargs.get('retry_attempt', 0)
        print(f"DEBUG: Current retry attempt: {retry_attempt}")

        skip_llm_call = kwargs.get('skip_llm', False)
        send_bot_question = kwargs.get('send_bot_question', False)
        print(f"DEBUG: skip_llm_call: {skip_llm_call}")

        # Handle NON_LLM operation type - send bot_question directly from database
        if send_bot_question and skip_llm_call:
            bot_question = kwargs.get('bot_question_from_db')
            if bot_question:
                return self._send_db_question(
                    bot_question=bot_question,
                    chat_session=chat_session,
                    chunks=chunks,
                    **kwargs
                )

        current_step = chat_session.current_step

        if skip_llm_call:
            is_function_call = True
            expected_output_response = None
            reason_text = None
            print("DEBUG: Skipping LLM call, treating as function call")
        else:
            is_function_call, expected_output_response, reason_text = self._analyze_response(response)
            print(f"DEBUG: Analysis result - is_function_call: {is_function_call}")
            print(f"DEBUG: expected_output_response: '{expected_output_response}'")
            print(f"DEBUG: reason_text: '{reason_text}'")

            if not is_function_call and retry_attempt < self.max_retry_attempts:
                response_to_check = expected_output_response if expected_output_response is not None else response

                if self._is_response_too_short(response_to_check):
                    logger.info(
                        f"Response too short, retrying LLM call (attempt {retry_attempt + 1}/{self.max_retry_attempts})")
                    print(
                        f"DEBUG: Response too short, retrying LLM call (attempt {retry_attempt + 1}/{self.max_retry_attempts})")

                    kwargs['retry_attempt'] = retry_attempt + 1

                    try:
                        result = self.get_llm_response(**kwargs)

                        if isinstance(result, tuple):
                            new_response, extra_content, finish_reason = result
                        else:
                            new_response = result
                            finish_reason = None

                        if new_response:
                            logger.info("Successfully got new response from LLM on retry")
                            print("DEBUG: Successfully got new response from LLM on retry")

                            return self.process_response(
                                new_response, chat_session, chunks,
                                streaming_completed=streaming_completed,
                                **kwargs
                            )
                        else:
                            logger.info("LLM returned None on retry, will use error message")
                            print("DEBUG: LLM returned None on retry, will use error message")
                            kwargs['use_error_message'] = True

                    except Exception as e:
                        logger.error(f"Error during LLM retry: {e}")
                        print(f"DEBUG: Error during LLM retry: {e}")
                        kwargs['use_error_message'] = True

            if not is_function_call and retry_attempt >= self.max_retry_attempts:
                response_to_check = expected_output_response if expected_output_response is not None else response
                if self._is_response_too_short(response_to_check):
                    logger.info("Exhausted all retries, response still too short, will use error message")
                    print("DEBUG: Exhausted all retries, response still too short, will use error message")
                    kwargs['use_error_message'] = True

        company_bot = kwargs['company_bot']
        language = kwargs['language']

        forward_kwargs = kwargs.copy()

        forward_kwargs['messages'] = self.get_messages_for_llm(**kwargs)
        forward_kwargs['skip_next_stage'] = kwargs.get('skip_next_stage', False)
        forward_kwargs['target_stage'] = kwargs.get('target_stage', False)
        forward_kwargs['skip_next_stage_preprocessing'] = kwargs.get('skip_next_stage_preprocessing', False)

        if kwargs.get('use_error_message', False) and not is_function_call:
            bot_vernacular = BotVernacular.objects.filter(company_bot=company_bot, language=language).first()
            error_message = bot_vernacular.error_message if (
                    bot_vernacular and bot_vernacular.error_message) else "Please try again!"
            logger.info(f"Using error message: {error_message}")
            print(f"DEBUG: Using error message: {error_message}")
            expected_output_response = error_message
            response = error_message

        # Handle function calls for STATE_MACHINE bots
        if is_function_call and company_bot and company_bot.bot_type == CompanyBotTypeChoices.STATE_MACHINE:
            print("DEBUG: Processing as STATE_MACHINE function call")
            return self._handle_function_call(
                response=response, chat_session=chat_session, chunks=chunks, **forward_kwargs
            )
        else:
            print("DEBUG: Processing as regular response")
            final_response = expected_output_response if (
                    expected_output_response is not None and expected_output_response != "") else response
            return self._handle_regular_response(
                response=final_response, chat_session=chat_session, chunks=chunks, current_step=current_step,
                streaming_completed=streaming_completed, reason=reason_text, **kwargs
            )

    def _extract_response_and_reason(self, response):
        """Extract both response and reason from the response"""
        logger.info(f"DEBUG: Extracting response and reason from response type: {type(response)}")
        logger.info(f"DEBUG: Response content preview: {str(response)[:200]}...")

        try:
            if isinstance(response, str):
                logger.info("DEBUG: Response is string")

                stripped = response.strip()
                if not (stripped.startswith('{') and stripped.endswith('}')):
                    if ('"response"' in stripped or '"reason"' in stripped) and ':' in stripped:
                        logger.info("DEBUG: String looks like JSON without outer braces, adding them")
                        response = '{' + stripped + '}'
                        logger.info(f"DEBUG: Fixed JSON string: {response[:200]}...")

                if not (response.strip().startswith('{') and response.strip().endswith('}')):
                    logger.info("DEBUG: String doesn't look like JSON, treating as plain text response")
                    return response, None, None

                logger.info("DEBUG: String looks like JSON, attempting parsing")
                try:
                    parsed_response = json.loads(response)
                    logger.info("DEBUG: Successfully parsed JSON from string")
                except json.JSONDecodeError:
                    try:
                        repaired_json = repair_json(response)
                        parsed_response = json.loads(repaired_json)
                        logger.info("DEBUG: Successfully repaired and parsed JSON")
                    except Exception as repair_error:
                        logger.info(f"DEBUG: JSON repair failed: {repair_error}")
                        return response, None, None

                response = parsed_response

            if isinstance(response, dict):
                logger.info("DEBUG: Processing dict response")
                logger.info(f"DEBUG: Dict keys: {list(response.keys())}")

                response_copy = response.copy()
                extracted_data = None

                if 'toolUseId' in response_copy and 'input' in response_copy:
                    logger.info("DEBUG: Found direct tool use format (toolUseId + input)")
                    extracted_data = response_copy.get('input')

                elif 'name' in response_copy and 'parameters' in response_copy:
                    logger.info("DEBUG: Found simple function call format (name + parameters)")
                    extracted_data = response_copy.get('parameters')

                elif 'parameters' in response_copy:
                    logger.info("DEBUG: Found parameters format")
                    extracted_data = response_copy.get('parameters')

                elif 'input' in response_copy:
                    logger.info("DEBUG: Found input format")
                    extracted_data = response_copy.get('input')

                elif 'output' in response_copy and 'message' in response_copy['output']:
                    logger.info("DEBUG: Found Bedrock nested response format")
                    content = response_copy['output']['message'].get('content', [])
                    for item in content:
                        if 'toolUse' in item:
                            extracted_data = item['toolUse'].get('input', {})
                            break

                elif 'function_call' in response_copy:
                    logger.info("DEBUG: Found OpenAI function_call format")
                    arguments = response_copy['function_call'].get('arguments', {})
                    if isinstance(arguments, str):
                        try:
                            extracted_data = json.loads(arguments)
                        except json.JSONDecodeError:
                            try:
                                repaired_arguments = repair_json(arguments)
                                extracted_data = json.loads(repaired_arguments)
                            except Exception:
                                extracted_data = None
                    else:
                        extracted_data = arguments

                elif 'tool_calls' in response_copy:
                    logger.info("DEBUG: Found OpenAI tool_calls format")
                    tool_calls = response_copy['tool_calls']
                    if tool_calls and len(tool_calls) > 0:
                        tool_call = tool_calls[0]
                        if 'function' in tool_call:
                            arguments = tool_call['function'].get('arguments', {})
                            if isinstance(arguments, str):
                                try:
                                    extracted_data = json.loads(arguments)
                                except json.JSONDecodeError:
                                    try:
                                        repaired_arguments = repair_json(arguments)
                                        extracted_data = json.loads(repaired_arguments)
                                    except Exception:
                                        extracted_data = None
                            else:
                                extracted_data = arguments
                else:
                    logger.info("DEBUG: Checking if response/reason are directly in dict")
                    if 'response' in response_copy or 'reason' in response_copy:
                        extracted_data = response_copy

                logger.info(f"DEBUG: Extracted data type: {type(extracted_data)}")
                if extracted_data:
                    logger.info(
                        f"DEBUG: Extracted data keys: {list(extracted_data.keys()) if isinstance(extracted_data, dict) else 'Not a dict'}")

                meta = extracted_data.copy() if isinstance(extracted_data, dict) else None
                if extracted_data and isinstance(extracted_data, dict):
                    if len(extracted_data) == 0:
                        print(
                            f"DEBUG: Empty extracted_data detected from LLM (input/parameters) - treating as function call")
                        logger.info(
                            f"Empty extracted_data detected from LLM (input/parameters) - treating as function call: {response}")
                        return '', ('LLM returned empty input/parameters - treating as function call to '
                                    'proceed to next state'), meta

                    response_text = extracted_data.get('response', '')
                    reason_text = extracted_data.get('reason', '')
                    logger.info(
                        f"DEBUG: Final extraction - response: '{response_text[:100]}...', "
                        f"reason: '{reason_text[:100]}...'")
                    return response_text, reason_text, meta

                elif extracted_data and isinstance(extracted_data, str):
                    logger.info("DEBUG: Extracted data is string, trying to parse as JSON")
                    try:
                        parsed_data = json.loads(extracted_data)
                    except json.JSONDecodeError:
                        try:
                            repaired_data = repair_json(extracted_data)
                            parsed_data = json.loads(repaired_data)
                            logger.info("DEBUG: Successfully repaired string data")
                        except Exception as e:
                            logger.info(f"DEBUG: Failed to parse string data: {e}")
                            return extracted_data, None, meta

                    if isinstance(parsed_data, dict):
                        response_text = parsed_data.get('response', '')
                        reason_text = parsed_data.get('reason', '')
                        logger.info(
                            f"DEBUG: Parsed string data - response: '{response_text[:100]}...', reason: "
                            f"'{reason_text[:100]}...'")
                        meta = parsed_data.copy()
                        return response_text, reason_text, meta

                logger.info("DEBUG: No specific format matched, checking original dict for response/reason")
                response_text = response_copy.get('response', '')
                reason_text = response_copy.get('reason', '')
                if response_text or reason_text:
                    logger.info(
                        f"DEBUG: Found in original dict - response: '{response_text[:100]}...', reason: "
                        f"'{reason_text[:100]}...'"
                    )
                    return response_text, reason_text, meta

        except Exception as e:
            logger.info(f"DEBUG: Error extracting response and reason: {e}")
            logger.error(f"Error extracting response and reason: {e}")

        logger.info("DEBUG: Fallback - returning original response as string")
        final_response = str(response) if not isinstance(response, str) else response
        return final_response, None, None

    def _extract_expected_output(self, response):
        """Extract expected_output from function call response if it exists and is not empty"""
        print(f"DEBUG: Extracting expected_output from response type: {type(response)}")
        print(f"DEBUG: Response content: {response}")

        def _extract_and_return(expected_output, format_name):
            """Helper to extract and return expected_output if not empty"""
            print(f"DEBUG: Expected output from {format_name}: '{expected_output}'")
            return expected_output if expected_output else None

        def _parse_json_string(json_str):
            """Helper to safely parse JSON string"""
            try:
                import json
                return json.loads(json_str)
            except json.JSONDecodeError:
                return None

        try:
            if isinstance(response, dict):
                if 'name' in response and 'parameters' in response:
                    print("DEBUG: Found simple function call format (NEW)")
                    expected_output = response['parameters'].get('expected_output', '')
                    return _extract_and_return(expected_output, "simple function call")

                elif 'toolUseId' in response and 'input' in response:
                    print("DEBUG: Found direct tool use format (OLD)")
                    expected_output = response['input'].get('expected_output', '')
                    return _extract_and_return(expected_output, "direct tool use")

                elif 'output' in response and 'message' in response['output']:
                    print("DEBUG: Found Bedrock response format")
                    content = response['output']['message'].get('content', [])
                    for item in content:
                        if 'toolUse' in item:
                            expected_output = item['toolUse'].get('input', {}).get('expected_output', '')
                            return _extract_and_return(expected_output, "Bedrock format")

                elif 'function_call' in response or 'tool_calls' in response:
                    print("DEBUG: Found OpenAI-style function call format")

                    if 'tool_calls' in response:
                        for tool_call in response['tool_calls']:
                            if 'function' in tool_call:
                                arguments = tool_call['function'].get('arguments', {})
                                if isinstance(arguments, str):
                                    arguments = _parse_json_string(arguments)
                                if arguments:
                                    expected_output = arguments.get('expected_output', '')
                                    return _extract_and_return(expected_output, "OpenAI tool_calls")

                    elif 'function_call' in response:
                        arguments = response['function_call'].get('arguments', {})
                        if isinstance(arguments, str):
                            arguments = _parse_json_string(arguments)
                        if arguments:
                            expected_output = arguments.get('expected_output', '')
                            return _extract_and_return(expected_output, "OpenAI function_call")

            elif isinstance(response, str):
                print("DEBUG: Found string response, trying to parse JSON")
                if 'get_state_information' in response:
                    import re
                    json_match = re.search(r'\{.*\}', response, re.DOTALL)
                    if json_match:
                        parsed = _parse_json_string(json_match.group())
                        if parsed:
                            expected_output = parsed.get('expected_output', '')
                            return _extract_and_return(expected_output, "string parsing")

        except Exception as e:
            print(f"DEBUG: Error extracting expected_output: {e}")
            logger.error(f"Error extracting expected_output: {e}")

        print("DEBUG: No expected_output found, returning None")
        return None

    def _handle_function_call(self, response, chat_session, chunks, **kwargs):
        """Handle function call for guided guest"""

        company_bot = kwargs['company_bot']
        session_id = kwargs['session_id']
        channel_name = kwargs['channel_name']
        language = kwargs['language']
        profile_id = kwargs['profile_id']
        skip_next_stage = kwargs.get('skip_next_stage', False)
        skip_next_stage_preprocessing = kwargs.get('skip_next_stage_preprocessing', False)
        target_stage = kwargs.get('target_stage')
        modified_bot_question = kwargs.get('modified_bot_question')
        if skip_next_stage:
            if target_stage and isinstance(target_stage, int):
                if skip_next_stage_preprocessing:
                    chat_session.current_step = target_stage + 1
                    logger.info(
                        f"Skipping target stage {target_stage} due to preprocessing, moving to {target_stage + 1}")
                else:
                    chat_session.current_step = target_stage
            else:
                chat_session.current_step += 2

        elif skip_next_stage_preprocessing:
            chat_session.current_step += 2
            logger.info(f"Skipping next stage {chat_session.current_step - 1} due to preprocessing")

        else:
            chat_session.current_step += 1

        total_steps = CompanyStateMachine.objects.filter(
            company_bot=company_bot
        ).count()

        if chat_session.current_step >= total_steps:
            chat_session.session_status = ChatStatus.COMPLETED
        chat_session.save()

        state_machine = CompanyStateMachine.objects.filter(
            company_bot=company_bot, step=chat_session.current_step
        ).first()
        if not state_machine:
            return None

        if modified_bot_question:
            bot_question = modified_bot_question
            logger.info(f"Using modified bot_question from preprocessing: {bot_question[:100]}")
        else:
            bot_question = state_machine.bot_question

        # Check if this is a NON_LLM state - if so, just use bot_question from DB
        is_non_llm = False
        if hasattr(state_machine, 'operation_type'):
            from chatbot.models.enums import OperationTypeChoices
            if state_machine.operation_type == OperationTypeChoices.NON_LLM:
                is_non_llm = True
                logger.info(f"State {state_machine.name} is NON_LLM, using bot_question from DB")

        chat_status = self.get_chat_status(state_machine=state_machine, company_bot=company_bot)

        print("sending bot_question: ", bot_question)
        translated_message = self.translate_message(
            message=bot_question, channel_name=channel_name, step_number=chat_session.current_step,
            language=language, company_bot=company_bot
        )

        other_params = {'function_call_response': response}
        if is_non_llm:
            other_params.update({
                'message_type': 'question',
                'operation_type': 'non_llm',
                'source': 'database'
            })
        print(f"DEBUG: Saving function call response in other_params: {response}")
        stage = state_machine.name if state_machine else None
        self.save_message(
            session_id=session_id, profile_id=profile_id, message=bot_question, chunks=chunks,
            status=chat_status, translated_message=translated_message, stage=stage,
            other_params=other_params
        )

        return response

    def _handle_regular_response(self, response, chat_session, company_bot,
                                 session_id, channel_name, language, profile_id,
                                 chunks, current_step, reason=None,
                                 streaming_completed=False, **kwargs):
        """Handle regular response for guided guest"""
        state_machine = CompanyStateMachine.objects.filter(
            company_bot=company_bot, step=chat_session.current_step
        ).first()
        extra_content = None

        print("[_handle_regular_response] Response: ", response)

        response, extra_content = self._handle_response_extra_content(
            response=response, company_bot=company_bot
        )

        if streaming_completed:
            print("Streaming already completed - skipping duplicate processing")
            logger.info("Streaming already completed - skipping duplicate processing")
            return None

        translated_message = self.translate_message(
            message=response, channel_name=channel_name, step_number=current_step,
            language=language, company_bot=company_bot, extra_content=extra_content
        )

        other_params = {}
        if reason:
            other_params['reason'] = reason
            print(f"DEBUG: Adding reason to other_params: {reason}")

        stage = state_machine.name if state_machine else None
        if response and str(response).strip():
            message_to_save = response
        elif extra_content and extra_content.get("query") and str(extra_content.get("query")).strip():
            message_to_save = extra_content["query"]
        else:
            message_to_save = "Understood."

        self.save_message(
            session_id=session_id, profile_id=profile_id, message=message_to_save, chunks=chunks,
            status=ChatStatus.IN_PROGRESS, translated_message=translated_message, stage=stage,
            other_params=other_params if other_params else None
        )

        return response

    def _handle_response_extra_content(self, response, company_bot):
        extra_content = None
        if company_bot.bot_type == CompanyBotTypeChoices.SIMPLE:
            if company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
                if response and isinstance(response, dict):
                    extracted_data = response.pop("parameters", response.pop("input", None))
                    if extracted_data and isinstance(extracted_data, dict):
                        response.clear()
                        response.update(extracted_data)

        print("Updated response post clean: ", response)
        logger.info(f"Updated response post clean: {response}")
        if response and isinstance(response, dict):
            query = response.get("query", "")

            extra_content = {
                "query": query,
                "should_move_forward": response.get("should_move_forward", 'no'),
                "validation": response.get("validation", "")
            }
            import json_repair
            tag_context = company_bot.tag_context
            if tag_context:
                tag_context = json_repair.repair_json(tag_context, return_objects=True)

            message = response.get("message", "")
            validation = response.get("validation")

            if response.get("should_move_forward") == 'yes':
                message = ''
            elif tag_context and validation:
                message = tag_context.get(validation, message)

            response = message

        return response, extra_content
