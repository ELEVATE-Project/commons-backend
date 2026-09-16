import json
import traceback
from asgiref.sync import async_to_sync
from chatbot.celery_tasks.common_chat_tasks import save_in_company_db
from chatbot.consumers.base_consumer import BaseConsumer
from chatbot.models import ChatStatus, ChatSession, Profile, CompanyBot, Voice, VoiceType, ChatType
from chatbot.models.company_models import CompanyStateMachine
from chatbot.utils.audio_provider_utils import text_translate_provider
from chatbot.celery_tasks.guided_guest_tasks import get_guided_guest_response
import logging

from chatbot.utils.transliterate_utils import transliterate_text
from shikshalokam.models import Project, ProjectStatus

logger = logging.getLogger('django')


class GuidedGuestConsumer(BaseConsumer):
    try:
        session_id = None
        profile_id = None
        route = None
        company_bot = None
        project_id = None
        task_id = None
        ip_address = None

        def translate_message(self, message):
            try:
                if not self.company_bot:
                    return message

                voice_provider = Voice.objects.filter(
                    company_bot=self.company_bot,
                    type=VoiceType.TextToText,
                    language=self.route
                ).first()

                if not voice_provider:
                    return message

                chat_session = ChatSession.objects.filter(session=self.session_id).first()
                if not chat_session:
                    return message

                state_machine = CompanyStateMachine.objects.get(
                    company_bot=self.company_bot, step=chat_session.current_step
                )

                if state_machine and state_machine.name in [
                    'INTRODUCTION', 'ROLE_INSTITUTE', 'FEDERATION_DETAILS', 'OCCUPATION', 'IMPLEMENTATION_LOCATION'
                ]:
                    transliterate_voice_provider = Voice.objects.filter(
                        company_bot=self.company_bot,
                        type=VoiceType.Transliterate,
                        language=self.route
                    ).first()
                    is_sentence = ' ' in message
                    response = transliterate_text(
                        voice_provider=transliterate_voice_provider, source_language=self.route, target_language='en',
                        message_body=message, is_sentence=is_sentence
                    )
                    print("Trans response: ", response)
                    if response and response.get('content'):
                        content = response.get('content')
                        print("Trans content: ", content)
                        if content and isinstance(content, list) and len(content) > 0:
                            content = content[0]
                        return content
                else:
                    response = text_translate_provider(
                        voice_provider=voice_provider, message_body=message,
                        target_language='en', source_language=self.route
                    )

                    if response.get('status') == 200:
                        return response.get('content')
                    else:
                        return message

            except Exception as e:
                logger.error('Translation Error: %s', e, exc_info=True)
                return message

        def disconnect(self, code):
            print('Websocket closed')
            chat_session = ChatSession.objects.filter(session=self.session_id)
            if chat_session.exists():
                c = chat_session[0]
            else:
                c = ChatSession(session=self.session_id)
            c.save_title(self.route)
            company_chat_status = self.determine_company_chat_status(
                session_id=self.session_id, profile_id=self.profile_id, is_disconnected=True, route='/guided_guest'
            )
            print("COMPANY CHAT STATUS: ", company_chat_status)
            self.update_last_chat_status(chat_status=company_chat_status)
            self.close()

        def receive(self, text_data):
            print(text_data)
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type', None)
            company_chat_status = None

            try:
                if message_type == 'authenticate':
                    self.session_id = text_data_json.get('sessionid')
                    self.profile_id = text_data_json.get('profileid')
                    self.route = text_data_json.get('route')
                    self.task_id = text_data_json.get('taskid')
                    self.project_id = text_data_json.get('projectid')
                    self.ip_address = text_data_json.get('address')
                    profile = Profile.objects.filter(id=self.profile_id).first()
                    print(f"Authenticated with session_id: {self.session_id}, profile_id: {self.profile_id}, "
                          f"route: {self.route}, projectId: {self.project_id}, taskId: {self.task_id}")
                    if profile:
                        self.company_bot = CompanyBot.objects.get(company=profile.company, route='/guided_guest')
                    else:
                        self.company_bot = CompanyBot.objects.get(route='/guided_guest')
                    if self.task_id:
                        other_params = {
                            "task_id": self.task_id
                        }
                    else:
                        other_params = {}
                    # chat session create (session, profile)
                    step_number = 1
                    if profile and profile.first_name and profile.first_name != '':
                        try:
                            educational_step = CompanyStateMachine.objects.get(
                                company_bot=self.company_bot, name="EDUCATIONAL_PROBLEMS"
                            )
                            step_number = educational_step.step
                        except CompanyStateMachine.DoesNotExist:
                            step_number = 1
                    cs, cs_created = ChatSession.objects.get_or_create(
                        session=self.session_id,
                        defaults={
                            'profile': profile,
                            'current_step': step_number,
                            'language': self.route,
                            'company_bot': self.company_bot,
                            'session_status': ChatStatus.IN_PROGRESS,
                            'session_type': ChatType.guidedReflection,
                            'project_id': self.project_id,
                            'other_params': other_params
                        }
                    )
                    print(cs, cs_created)

                    if not cs_created:
                        if cs.language != self.route:
                            cs.language = self.route

                        other_params = cs.other_params or {}
                        other_params["ip_address"] = self.ip_address

                        cs.other_params = other_params

                        cs.save(update_fields=["language", "other_params"])
                    else:
                        cs.other_params = {"ip_address": self.ip_address}
                        cs.save(update_fields=["other_params"])

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
                        session_id=self.session_id, profile_id=self.profile_id, route='/guided_guest'
                    )
                    print("COMPANY CHAT STATUS: ", company_chat_status)
                    async_to_sync(self.channel_layer.send)(
                        self.channel_name,
                        {
                            "type": "chat_message",
                            "text": {"msg": text_data_json["text"], "source": "user"},
                        },
                    )
                translated_message = None
                if self.route != 'en' and text_data_json and text_data_json.get('text'):
                    translated_message = self.translate_message(message=text_data_json['text'])

                print("text_data_json: ", text_data_json)
                if message_type != 'authenticate' and text_data_json and text_data_json.get('text'):
                    chat_session = ChatSession.objects.filter(session=self.session_id).order_by('-created_at').first()
                    current_stage=None
                    if chat_session and self.company_bot:
                        state_machine = CompanyStateMachine.objects.get(
                            company_bot=self.company_bot, step=chat_session.current_step
                        )
                        if state_machine:
                            current_stage=state_machine.name
                    save_in_company_db(
                        session_id=self.session_id, profile_id=self.profile_id, initiated_by='User',
                        message=text_data_json['text'], chunks=None, status=company_chat_status,
                        translated_message=translated_message, audio_base64=text_data_json.get('asr_audio'),
                        stage=current_stage
                    )

                print(f"channel_name: {self.channel_name}, session_id: {self.session_id}, profile_id: "
                      f"{self.profile_id}, route: {self.route}")

                if message_type != 'authenticate':
                    get_guided_guest_response.delay(
                        self.channel_name, self.session_id, self.profile_id, self.route
                    )
            except Exception as e:
                print(e)
                logger.error('Receive Error: %s', e, exc_info=True)
                traceback.print_exc()

        def connect(self):
            try:
                print('Attempting to connect to websocket')
                super().connect()
            except Exception as e:
                logger.error('Connect Error: %s', e, exc_info=True)
                print(f"Connect Error: {e}")
                traceback.print_exc()
    except Exception as e:
        logger.error('Error: %s', e, exc_info=True)
        print(f"Error: {e}")
