from abc import ABC, abstractmethod
import logging

logger = logging.getLogger('django')


class BasePostprocessor(ABC):
    """Base class for postprocessing operations"""

    @abstractmethod
    def postprocess(self, state_machine, llm_response, **kwargs):
        """Execute postprocessing logic"""
        pass


class SimplePostprocessor(BasePostprocessor):
    """Handles simple prompt-based postprocessing"""

    def postprocess(self, state_machine, llm_response, **kwargs):
        """Execute simple postprocessing using postprocess_prompt"""
        if not state_machine.postprocess_prompt:
            logger.warning(f"No postprocess_prompt defined for state {state_machine.name}")
            return None

        # Get LLM handler
        from chatbot.llm_models.llm_script import handle_bedrock_model, handle_openai_model
        from chatbot.models import LLMProvider

        company_bot = kwargs.get('company_bot')
        messages = kwargs.get('messages', [])

        # Add the LLM response to messages for context
        enhanced_messages = messages.copy()
        if llm_response:
            enhanced_messages.append({
                'role': 'assistant',
                'content': str(llm_response)
            })

        # Build simple prompt with LLM response context
        simple_prompt = self._build_simple_prompt(
            state_machine.postprocess_prompt, company_bot, llm_response
        )

        try:
            if company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
                response = handle_bedrock_model(
                    system_prompt=simple_prompt,
                    messages=enhanced_messages,
                    model_name=company_bot.llm_model,
                    temperature=company_bot.bot_temperature,
                    max_token=company_bot.max_token,
                    company_bot=company_bot
                )
            elif company_bot.provider == LLMProvider.OPENAI:
                response = handle_openai_model(
                    system_prompt=simple_prompt,
                    messages=enhanced_messages,
                    model_name=company_bot.llm_model,
                    temperature=company_bot.bot_temperature,
                    max_token=company_bot.max_token,
                    tools=None,
                    tool_choice='auto',
                    is_json_response=False
                )
            else:
                response = None

            logger.info(f"Simple postprocessing response for {state_machine.name}: {response}")
            return response

        except Exception as e:
            logger.error(f"Error in simple postprocessing: {e}")
            return None

    def _build_simple_prompt(self, postprocess_prompt, company_bot, llm_response):
        """Build prompt for simple postprocessing"""
        enhanced_prompt = f"{postprocess_prompt}\n\nLLM Response to analyze: {llm_response}"

        from chatbot.models import LLMProvider
        if company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
            return [{'text': enhanced_prompt}]
        else:
            return [{'role': 'system', 'content': enhanced_prompt}]


class ComplexPostprocessor(BasePostprocessor):
    """Handles complex bot-based postprocessing"""

    def postprocess(self, state_machine, llm_response, **kwargs):
        """Execute complex postprocessing using postprocess_bot"""
        if not state_machine.postprocess_bot:
            logger.warning(f"No postprocess_bot defined for state {state_machine.name}")
            return None

        try:
            # Use the postprocess_bot to analyze the LLM response
            from chatbot.services.core.prompt_builder import PromptBuilder
            from chatbot.llm_models.llm_script import handle_bedrock_model, handle_openai_model
            from chatbot.models import LLMProvider

            postprocess_bot = state_machine.postprocess_bot
            messages = kwargs.get('messages', [])

            # Add the LLM response to messages for context
            enhanced_messages = messages.copy()
            if llm_response:
                from chatbot.models import LLMProvider
                enhanced_messages.append({
                    'role': 'assistant' if postprocess_bot.provider == LLMProvider.OPENAI else 'assistant',
                    'content': str(llm_response)
                })

            # Build prompt using the postprocess bot's context
            prompt_builder = PromptBuilder()

            system_prompt = prompt_builder.build_system_prompt(postprocess_bot, None)

            if postprocess_bot.provider == LLMProvider.BEDROCK_CONVERSE:
                response = handle_bedrock_model(
                    system_prompt=system_prompt,
                    messages=enhanced_messages,
                    model_name=postprocess_bot.llm_model,
                    temperature=postprocess_bot.bot_temperature,
                    max_token=postprocess_bot.max_token,
                    company_bot=postprocess_bot
                )
            elif postprocess_bot.provider == LLMProvider.OPENAI:
                response = handle_openai_model(
                    system_prompt=system_prompt,
                    messages=enhanced_messages,
                    model_name=postprocess_bot.llm_model,
                    temperature=postprocess_bot.bot_temperature,
                    max_token=postprocess_bot.max_token,
                    tools=None,
                    tool_choice='auto',
                    is_json_response=False
                )
            else:
                response = None

            logger.info(f"Complex postprocessing response for {state_machine.name}: {response}")
            return response

        except Exception as e:
            logger.error(f"Error in complex postprocessing: {e}")
            return None
