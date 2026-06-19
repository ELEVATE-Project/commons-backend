from chatbot.models import CompanyChat


def get_chat_dict(chat_session_id: int, exclude_end_ai_message=True):
    chats = list(CompanyChat.objects.filter(
        session=chat_session_id).order_by('created_at').all())

    chat_dict = []

    bot_profile_id = 1  # NOTE: assuiming bot id will be always 1

    for i in range(len(chats)):
        if i == len(chats) - 1 and chats[i].sender.id == bot_profile_id and exclude_end_ai_message:
            continue

        if chats[i].sender.id == bot_profile_id:
            chat_dict.append(
                {"role": "assistant", "content": chats[i].message}
            )

        else:
            chat_dict.append({"role": "user", "content": chats[i].message})

    return chat_dict
