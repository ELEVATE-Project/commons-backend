from chatbot.models import LLMProvider


class PromptBuilder:
    """Centralized prompt building logic"""

    @staticmethod
    def build_system_prompt(company_bot, state_machine=None):
        """Build system prompt based on provider type"""

        system_parts = [company_bot.context.strip()]

        if state_machine and state_machine.context:
            system_parts.append(state_machine.context.strip())

        if state_machine and state_machine.completion_criteria:
            system_parts.append(f"Completion Criteria:\n{state_machine.completion_criteria.strip()}")

        tool_context = ""
        if (state_machine and
                hasattr(state_machine, 'tool_context') and
                state_machine.tool_context and
                state_machine.tool_context.strip()):
            tool_context = None
        elif company_bot.tool_context and company_bot.tool_context.strip():
            tool_context = company_bot.tool_context.strip()

        if company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
            result = [{'text': system_parts[0]}]
            if len(system_parts) > 1:
                result.append({'text': "\n\n".join(system_parts[1:])})
            if tool_context:
                result.append({'text': tool_context})
            return result

        elif company_bot.provider == LLMProvider.OPENAI:
            return [{
                'role': 'system',
                'content': "\n\n".join(system_parts)
            }]

        return []
