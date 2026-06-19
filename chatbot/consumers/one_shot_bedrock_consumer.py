import json
import os
from django.conf import settings
import traceback
from asgiref.sync import async_to_sync
from chatbot.celery_tasks.common_chat_tasks import save_in_company_db
from chatbot.consumers.base_consumer import BaseConsumer
from chatbot.models import ChatStatus, ChatSession, Profile, CompanyBot, Voice, VoiceType, ChatType
from chatbot.celery_tasks.one_shot_bedrock_tasks import get_one_shot_bedrock_response
from chatbot.models.company_models import CompanyStateMachine
from chatbot.utils.audio_provider_utils import text_translate_provider
import jwt
import logging

from shikshalokam.models import Project, ProjectStatus

logger = logging.getLogger('django')
PUBLIC_KEY = os.getenv("JWT_PUBLIC_KEY")


class OneShotBedrockConsumer(BaseConsumer):

    try:
        session_id = None
        profile_id = None
        project_id = None
        access_token = None
        route = None
        company_bot = None
        task_id = None

        def disconnect(self, code):
            chat_session = ChatSession.objects.filter(session=self.session_id)
            if chat_session.exists():
                c = chat_session[0]
            else:
                c = ChatSession(session=self.session_id)
            c.save_title(self.route)
            company_chat_status = self.determine_company_chat_status(
                session_id=self.session_id, profile_id=self.profile_id, is_disconnected=True, route='/oneshot_bot'
            )
            print("COMPANY CHAT STATUS: ", company_chat_status)
            self.update_last_chat_status(chat_status=company_chat_status)
            self.close()

        def receive(self, text_data):
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type', None)

            if message_type == 'authenticate':
                self.session_id = text_data_json.get('sessionid')
                self.profile_id = text_data_json.get('profileid')
                self.project_id = text_data_json.get('projectid')
                self.access_token = text_data_json.get('access_token')
                self.route = text_data_json.get('route')
                self.task_id = text_data_json.get('taskid')
                profile = Profile.objects.filter(id=self.profile_id).first()
                print(f"Authenticated with session_id: {self.session_id}, profile_id: {self.profile_id}, "
                      f"route: {self.route}, projectId: {self.project_id}, taskId: {self.task_id}")
                if profile:
                    self.company_bot = CompanyBot.objects.get(company=profile.company, route='/oneshot_bot')
                else:
                    self.company_bot = CompanyBot.objects.get(route='/oneshot_bot')

                if self.task_id:
                    other_params = {
                        "task_id": self.task_id
                    }
                else:
                    other_params = {}

                user_id = None

                if self.access_token:
                    decoded = jwt.decode(
                        self.access_token,
                        PUBLIC_KEY,
                        algorithms=["HS256"]
                    )
                    print(decoded)
                    if decoded:
                        user_id = decoded.get("data", {}).get("id")
    
                print("User_id: ", user_id)

                # chat session create (session, profile)
                cs, cs_created = ChatSession.objects.get_or_create(
                    session=self.session_id,
                    defaults={
                        'profile': profile,
                        'current_step': 1,
                        'language': self.route,
                        'company_bot': self.company_bot,
                        'session_status': ChatStatus.IN_PROGRESS,
                        'project_id': self.project_id,
                        'user_id': user_id,
                        'session_type': ChatType.oneStepReflection,
                        'other_params': other_params
                    }
                )
                print(cs, cs_created)
                if not cs_created and cs.language != self.route:
                    cs.language = self.route
                    cs.save(update_fields=['language'])
                project = Project.objects.filter(project_id=self.project_id).first()
                if not project:
                    print(f"Project with ID {self.project_id} not found. Creating a new one.")
                    project = Project.objects.create(
                        project_id=self.project_id,
                        author=profile,
                        project_status=ProjectStatus.STARTED,
                    )
                    print(f"Project created with id {project.id}")
                else:
                    print(f"Found existing project: {project.id}")
            else:
                company_chat_status = self.determine_company_chat_status(
                    session_id=self.session_id, profile_id=self.profile_id, route='/oneshot_bot'
                )
                print("COMPANY CHAT STATUS: ", company_chat_status)
                async_to_sync(self.channel_layer.send)(
                    self.channel_name,
                    {
                        "type": "chat_message",
                        "text": {"msg": text_data_json["text"], "source": "user"},
                    },
                )

                if self.route != 'en'  and text_data_json and text_data_json.get('text'):
                    voice_provider = Voice.objects.filter(
                        company_bot=self.company_bot, type=VoiceType.TextToText, language=self.route
                    ).first()

                    response = text_translate_provider(
                        voice_provider=voice_provider, message_body=text_data_json['text'], target_language='en',
                        source_language=self.route
                    )
                    if response.get('status') == 200:
                        translated_message = response.get('content')
                    else:
                        translated_message = text_data_json['text']
                else:
                    translated_message = None

                if message_type != 'authenticate' and text_data_json and text_data_json.get('text'):
                    chat_session = ChatSession.objects.filter(session=self.session_id).order_by('-created_at').first()
                    current_stage = None
                    if chat_session and self.company_bot:
                        state_machine = CompanyStateMachine.objects.get(
                            company_bot=self.company_bot, step=chat_session.current_step
                        )
                        if state_machine:
                            current_stage = state_machine.name
                    save_in_company_db(
                        session_id=self.session_id, profile_id=self.profile_id, initiated_by='User',
                        message=text_data_json['text'], chunks=None, status=company_chat_status,
                        translated_message=translated_message, audio_base64=text_data_json.get('asr_audio'),
                        stage=current_stage
                    )

                print(f"channel_name: {self.channel_name}, session_id: {self.session_id}, profile_id: "
                      f"{self.profile_id}, route: {self.route}")

                if message_type != 'authenticate':
                    get_one_shot_bedrock_response.delay(
                        self.channel_name, self.session_id, self.profile_id, self.route
                    )
    except Exception as e:
            logger.error('Error: %s', e, exc_info=True)
            print(f"Error: {e}")
