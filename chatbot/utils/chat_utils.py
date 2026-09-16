from chatbot.models import Profile, LLMProvider, CompanyChat
import json

def format_message_as_per_openai_format(chats, intro=None):
    ai_user = Profile.objects.values("id").get(id=1)
    if intro:
        messages = [
            {
                'role': 'user',
                'content': "Hello"
            }, {
                'role': 'assistant',
                'content': intro
            }
        ]
    else:
        messages = []
    for chat in chats:
        chat_receiver = None
        chat_message = None
        chat_translated_message = None
        
        # variable instialisation
        if isinstance(chat, CompanyChat):
            chat_receiver = getattr(chat.receiver, 'id', None)
            chat_message = getattr(chat, 'message', None)
            chat_translated_message = getattr(chat, 'translated_message', None)

        elif isinstance(chat, dict):
            chat_receiver = chat.get("receiver")
            chat_message = chat.get("message")
            chat_translated_message = chat.get("translated_message")

        if chat_receiver == ai_user.get("id"):
            user_message = chat_message
            if chat_translated_message is not None and chat_translated_message != '':
                user_message = chat_translated_message
            messages.append({
                'role': 'user',
                'content': user_message
            })
        else:
            messages.append({
                'role': 'assistant',
                "content": chat_message
            })
    return messages


def format_message_as_per_bedrock_format(chats, intro=None, other_info=None):
    ai_user = Profile.objects.values("id").get(id=1)
    if intro:
        if other_info:
            user_name = other_info.get('first_name', None)
            user_location = other_info.get('user_location', None)
            if user_name:
                initial_msg = f"Hello my name is {user_name}."
                if user_location:
                    initial_msg += f" I am from {user_location}"
            else:
                initial_msg = "Hello"
        else:
            initial_msg = "Hello"
        messages = [
            {
                'role': 'user',
                'content': [{'text': initial_msg}]
            }, {
                'role': 'assistant',
                'content': [{'text': intro}]
            }
        ]
    else:
        messages = []
    for chat in chats:
        chat_receiver = None
        chat_message = None
        chat_translated_message = None
        
        # variable instialisation
        if isinstance(chat, CompanyChat):
            chat_receiver = getattr(chat.receiver, 'id', None)
            chat_message = getattr(chat, 'message', None)
            chat_translated_message = getattr(chat, 'translated_message', None)

        elif isinstance(chat, dict):
            chat_receiver = chat.get("receiver")
            chat_message = chat.get("message")
            chat_translated_message = chat.get("translated_message")

        if chat_receiver == ai_user.get("id"):
            user_message = chat_message
            if chat_translated_message is not None and chat_translated_message != '':
                user_message = chat_translated_message
            messages.append({
                'role': 'user',
                'content': [{'text': user_message}]
            })
        else:
            messages.append({
                'role': 'assistant',
                "content": [{'text': chat_message}]
            })

    if not messages or messages[0].get('role') != 'user':
        messages.insert(0, {
            'role': 'user',
            'content': [{'text': 'Hello'}]
        })

    return messages


def get_guided_chat(company_bot, company_chats, intro=None, other_info=None):
    messages = []
    if company_bot.provider == LLMProvider.BEDROCK_CONVERSE:
        messages = format_message_as_per_bedrock_format(chats=company_chats, intro=intro, other_info=other_info)
    elif company_bot.provider == LLMProvider.OPENAI:
        messages = format_message_as_per_openai_format(chats=company_chats, intro=intro)

    return messages


def convert_llama_to_openai_tool(llama_tool_call):
    try:
        tool_spec = llama_tool_call.get("toolConfig", {}).get("tools", [])[0].get("toolSpec", {})

        if not tool_spec:
            raise ValueError("Invalid toolSpec structure in the provided Llama tool call.")

        parameters = tool_spec.get("inputSchema", {}).get("json", {})

        if "properties" in parameters:
            for key, value in parameters["properties"].items():
                if value.get("type") == "array" and "items" not in value:
                    value["items"] = {"type": "string"}

        openai_tool = [
            {
                "type": "function",
                "function": {
                    "name": tool_spec.get("name"),
                    "description": tool_spec.get("description"),
                    "parameters": parameters
                }
            }
        ]

        print("Converted OpenAI tool:", json.dumps(openai_tool, indent=4))
        return openai_tool

    except Exception as e:
        print("Error converting tool:", str(e))
        return None
