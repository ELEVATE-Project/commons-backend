import json
from channels.generic.websocket import WebsocketConsumer
from chatbot.models import ChatSession, CompanyChat, ChatStatus, Profile, CompanyBot
from chatbot.models.company_models import CompanyStateMachine


class BaseConsumer(WebsocketConsumer):
    def connect(self):
        self.accept()

    def disconnect(self, code):
        session_id = self.scope['cookies']['sessionid']
        chat_session = ChatSession.objects.filter(session=session_id)
        if chat_session.exists():
            c = chat_session[0]
        else:
            c = ChatSession(session=session_id)
        c.save_title()
        self.close()

    def receive(self, text_data):
        raise NotImplementedError("receive method must be implemented in subclass")

    def chat_message(self, event):
        text = event["text"]
        self.send(text_data=json.dumps({"text": text}))

    def determine_company_chat_status(self, session_id, profile_id, route,is_disconnected=False):
        if not session_id:
            return None
        chat_session = ChatSession.objects.filter(session=session_id).first()

        profile = Profile.objects.filter(id=self.profile_id).first()
        if profile:
            company_bot = CompanyBot.objects.get(company=profile.company, route=route)
        else:
            company_bot = CompanyBot.objects.get(route=route)

        state_machine = CompanyStateMachine.objects.filter(
            company_bot=company_bot, step=chat_session.current_step
        ).first()

        existing_chats = CompanyChat.objects.filter(session=session_id)

        if existing_chats.count() == 0:
            return ChatStatus.STARTED
        elif state_machine and state_machine.name != 'APPRECIATION' and is_disconnected:
            return ChatStatus.PAUSED
        elif existing_chats.exists():
            last_chat = existing_chats.last()
            if last_chat.status == ChatStatus.PAUSED:
                return ChatStatus.RESUME
        elif chat_session and chat_session.session_status == ChatStatus.COMPLETED:
            return ChatStatus.COMPLETED

        return ChatStatus.IN_PROGRESS

    def update_last_chat_status(self, chat_status):
        existing_chat = CompanyChat.objects.filter(session=self.session_id).last()
        if not existing_chat:
            return
        print("msg: ", existing_chat.message)
        if existing_chat and existing_chat.status != ChatStatus.COMPLETED:
            existing_chat.status = chat_status
            existing_chat.save()
