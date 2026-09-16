import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.http import JsonResponse
from chatbot.models import (CompanyBot, Voice, VoiceType, Profile,
BotVernacular, StoryMedia, MediaTypeChoices, SessionFlowName, ChatSession,
CompanyChat)
from chatbot.serializer.story_serializer import StoryMediaRetrieveSerializer
from chatbot.utils.chat_utils import get_guided_chat
from shikshalokam.utils.action_list.action_processor import post_process_actions_with_source
from shikshalokam.utils.action_list.action_steps_utils import generate_action_list_utils, generate_action_list_parallel
from asgiref.sync import async_to_sync
from shikshalokam.utils.mitra_base_utils import get_mitra_paraphrase_utils, generate_title_utils
from chatbot.utils.story_llama_utils import translate_field
from chatbot.utils.media_utils import upload_to_cloud
from chatbot.utils.shikshalokam_story_utils import update_story_pdf
from shikshalokam.models import Project
from shikshalokam.utils.objective_list.objective_processor import post_process_objectives_with_source
from shikshalokam.utils.objective_list.objective_utils import generate_objective_utils
from shikshalokam.utils.project_utils import update_project_status_utils
import json_repair
from shikshalokam.utils.validation_utils import validate_objective_utils, validate_actions_utils, validate_title_utils

logger = logging.getLogger('django')


@api_view(['POST'])
def paraphrase_view(request):
    try:
        body = request.data
        user_input = body.get('user_input')
        session_id = body.get('session_id')

        if not session_id:
            raise ValueError("Session ID is required")

        company_bot = CompanyBot.objects.get(route='/paraphrase')

        session_data = ChatSession.objects.values('language').get(session=session_id)
        company_chats = CompanyChat.objects.filter(session=session_id).order_by('created_at')
        language = session_data["language"]

        formatted_chats = get_guided_chat(company_bot=company_bot, company_chats=company_chats)

        voice_provider = Voice.objects.filter(
            company_bot=company_bot, type=VoiceType.TextToText, language=language
        ).first()

        if language != 'en':
            user_input = translate_field(
                voice_provider=voice_provider, message_body=user_input, source_language=language,
                target_language='en'
            )
            print("user_translated_message: ", user_input)

        paraphrased_output = get_mitra_paraphrase_utils(messages=formatted_chats, company_bot=company_bot, session_id=session_id)

        print("\n\nParaphrased Output: ", paraphrased_output)
        return Response({
            'status': 'ok',
            'paraphrased_output': paraphrased_output
        }, status=200)
    except Exception as e:
        logger.error(f"[paraphrase_view] Unhandled exception: {str(e)}", exc_info=True)
        return Response({
            'status': 'error',
            'message': str(e)
        }, status=500)


@api_view(['POST'])
def generate_objectives_view(request):
    error_message = ""
    try:
        body = request.data
        user_input = body.get('user_input')
        language = body.get('language')
        profile_id = body.get('profile_id')

        logger.info(
            f"[generate_objectives_view] Request received - user_input: {user_input}, language: {language}, "
            f"profile_id: {profile_id}")

        profile = Profile.objects.filter(id=profile_id).first()
        if profile:
            company_bot = CompanyBot.objects.get(company=profile.company, route='/objective')
        else:
            company_bot = CompanyBot.objects.get(route='/objective')

        voice_provider = Voice.objects.filter(
            company_bot=company_bot, type=VoiceType.TextToText, language=language
        ).first()

        if language != 'en':
            logger.info(f"[generate_objectives_view] Translating user input from {language} to English")
            user_input = translate_field(
                voice_provider=voice_provider, message_body=user_input, source_language=language,
                target_language='en'
            )
            logger.info(f"[generate_objectives_view] Translated user input: {user_input}")

        logger.info(f"[generate_objectives_view] Calling generate_objective_utils")
        gen_result = generate_objective_utils(
            user_problem_statement=user_input, company_bot=company_bot
        )
        logger.info(
            f"[generate_objectives_view] Generation result status: {gen_result['status']}, "
            f"objectives count: {len(gen_result.get('objective_list', []))}")

        if gen_result['objective_list'] == [] or not gen_result['objective_list']:
            bot_vernacular = BotVernacular.objects.filter(company_bot=company_bot, language=language).first()
            error_message = bot_vernacular.error_message if bot_vernacular and bot_vernacular.error_message \
                else "Please try again!"
            if voice_provider and language != 'en':
                error_message = translate_field(
                    voice_provider=voice_provider, message_body=error_message, target_language=language
                )
            logger.info(f"[generate_objectives_view] No objectives generated, error message: {error_message}")

        if gen_result['status'] != 'ok':
            logger.error(
                f"[generate_objectives_view] Generation failed with status: "
                f"{gen_result['status']}, message: {gen_result.get('message')}")
            return Response({
                'status': gen_result['status'],
                'message': error_message,
                'objective_list': [],
                'chunks': None
            }, status=gen_result['status_code'])

        objective_list = gen_result['objective_list']
        chunk_response = gen_result.get('chunks_response', None)
        filtered_chunks = gen_result['filtered_chunks']

        logger.info(
            f"[generate_objectives_view] Objectives parsed: {len(objective_list)}, filtered chunks: {len(filtered_chunks)}")

        if not objective_list:
            logger.info(f"[generate_objectives_view] Empty objective list, returning early")
            return Response({
                'status': 'ok',
                'message': error_message,
                'objective_list': []
            }, status=200)

        logger.info(f"[generate_objectives_view] Calling post_process_objectives_with_source")
        post_result = post_process_objectives_with_source(objective_list, filtered_chunks, chunk_response)
        logger.info(f"[generate_objectives_view] Post-processing result status: {post_result['status']}")

        if post_result['status'] != 'ok':
            logger.error(f"[generate_objectives_view] Post-processing failed: {post_result.get('message')}")
            return Response({
                'status': post_result['status'],
                'message': error_message,
                'objective_list': [],
                'chunks': chunk_response
            }, status=post_result['status_code'])

        objective_list = post_result['objective_list']
        logger.info(f"[generate_objectives_view] Post-processed objectives count: {len(objective_list)}")

        translated_list = None
        if language != 'en':
            logger.info(f"[generate_objectives_view] Translating objectives to {language}")
            translated_list = translate_field(
                voice_provider=voice_provider, message_body=json.dumps(objective_list), target_language=language,
                source_language='en'
            )
            if isinstance(translated_list, str):
                try:
                    translated_list = json_repair.repair_json(translated_list, return_objects=True)
                    logger.info(f"[generate_objectives_view] Successfully parsed translated objectives")
                except Exception as e:
                    logger.error(f"[generate_objectives_view] Error parsing translated objectives: {e}")

        if translated_list:
            objective_list = translated_list
            logger.info(f"[generate_objectives_view] Using translated objectives")

        logger.info(f"[generate_objectives_view] Returning {len(objective_list)} objectives successfully")
        return Response({
            'status': 'ok',
            'message': error_message,
            'objective_list': objective_list,
            'chunks': chunk_response
        }, status=200)

    except Exception as e:
        logger.error(f"[generate_objectives_view] Unhandled exception: {str(e)}", exc_info=True)
        return Response({
            'status': 'error',
            'message': error_message if error_message else "Please try again!",
            'objective_list': [],
            'chunks': None
        }, status=500)


@api_view(['POST'])
def validate_objectives_view(request):
    error_message = "Please try again!"
    try:
        body = request.data
        user_input = body.get('user_input')
        user_problem_statement = body.get('user_problem_statement')
        language = body.get('language')
        profile_id = body.get('profile_id')

        logger.info(
            f"[validate_objectives_view] Request received - user_input: {user_input}, language: {language}, "
            f"profile_id: {profile_id}")

        if isinstance(user_input, list):
            user_input = " and ".join(
                str(obj).strip() for obj in user_input if obj
            )

        profile = Profile.objects.filter(id=profile_id).first()
        if profile:
            company_bot = CompanyBot.objects.get(company=profile.company, route='/validate-objective')
        else:
            company_bot = CompanyBot.objects.get(route='/validate-objective')

        bot_vernacular = BotVernacular.objects.filter(company_bot=company_bot, language=language).first()
        error_message = bot_vernacular.error_message if bot_vernacular and bot_vernacular.error_message else \
            "Please try again!"

        if language != 'en':
            logger.info(f"[validate_objectives_view] Translating user input from {language} to English")
            voice_provider = Voice.objects.filter(
                company_bot=company_bot, type=VoiceType.TextToText, language=language
            ).first()
            user_input = translate_field(
                voice_provider=voice_provider, message_body=user_input, source_language=language,
                target_language='en'
            )
            user_problem_statement = translate_field(
                voice_provider=voice_provider, message_body=user_problem_statement, source_language=language,
                target_language='en'
            )
            logger.info(f"[validate_objectives_view] Translated user input: {user_input}")

        logger.info(f"[validate_objectives_view] Calling validate_objective_utils")
        validation_result = validate_objective_utils(
            user_input=user_input, user_problem_statement=user_problem_statement, company_bot=company_bot
        )

        if not validation_result.get('success'):
            logger.error(f"[validate_objectives_view] Validation utility failed: {validation_result.get('error')}")
            return Response({
                'status': 'error',
                'result': None,
                'error_message': error_message
            }, status=500)

        llm_data = validation_result.get('data', {})
        valid = llm_data.get('valid', False)

        response_data = {
            'status': 'ok',
            'result': valid,
        }

        if not valid:
            response_data['error_message'] = llm_data.get('overall_message', error_message)
            if 'objectives_validation' in llm_data:
                response_data['validation_details'] = llm_data.get('objectives_validation')
            if 'reason' in llm_data:
                response_data['reason'] = llm_data.get('reason')

        logger.info(f"[validate_objectives_view] Returning validation result successfully")
        return Response(response_data, status=200)

    except Exception as e:
        logger.error(f"[validate_objectives_view] Unhandled exception: {str(e)}", exc_info=True)
        return Response({
            'status': 'error',
            'result': None,
            'error_message': error_message
        }, status=500)


@api_view(['POST'])
def validate_actions_view(request):
    error_message = "Please try again!"
    try:
        body = request.data
        user_input = body.get('user_input')
        user_objective = body.get('user_objective')
        language = body.get('language')
        problem_statement = body.get('problem_statement')
        profile_id = body.get('profile_id')

        logger.info(
            f"[validate_actions_view] Request received - user_input: {user_input}, user_objective: {user_objective}, "
            f"language: {language}, profile_id: {profile_id}")

        if isinstance(user_objective, list):
            user_objective = " and ".join(
                str(obj).strip() for obj in user_objective if obj
            )

        profile = Profile.objects.filter(id=profile_id).first()
        if profile:
            company_bot = CompanyBot.objects.get(company=profile.company, route='/validate-action_list')
        else:
            company_bot = CompanyBot.objects.get(route='/validate-action_list')

        bot_vernacular = BotVernacular.objects.filter(company_bot=company_bot, language=language).first()
        error_message = bot_vernacular.error_message if bot_vernacular and bot_vernacular.error_message else \
            "Please try again!"

        if language != 'en':
            logger.info(f"[validate_actions_view] Translating inputs from {language} to English")
            voice_provider = Voice.objects.filter(
                company_bot=company_bot, type=VoiceType.TextToText, language=language
            ).first()

            if isinstance(user_input, list):
                user_input = [
                    translate_field(
                        voice_provider=voice_provider, message_body=action, source_language=language,
                        target_language='en'
                    ) for action in user_input
                ]
            else:
                user_input = translate_field(
                    voice_provider=voice_provider, message_body=user_input, source_language=language,
                    target_language='en'
                )

            user_objective = translate_field(
                voice_provider=voice_provider, message_body=user_objective, source_language=language,
                target_language='en'
            )
            problem_statement = translate_field(
                voice_provider=voice_provider, message_body=problem_statement, source_language=language,
                target_language='en'
            )

            logger.info(f"[validate_actions_view] Translated user input: {user_input}")
            logger.info(f"[validate_actions_view] Translated user objective: {user_objective}")
            logger.info(f"[validate_actions_view] Translated problem statement: {problem_statement}")

        logger.info(f"[validate_actions_view] Calling validate_actions_utils")
        validation_result = validate_actions_utils(
            user_input=user_input, user_objective=user_objective, problem_statement=problem_statement,
            company_bot=company_bot
        )

        if not validation_result.get('success'):
            logger.error(f"[validate_actions_view] Validation utility failed: {validation_result.get('error')}")
            return Response({
                'status': 'error',
                'result': None,
                'error_message': error_message
            }, status=500)

        llm_data = validation_result.get('data', {})
        valid = llm_data.get('valid', False)

        response_data = {
            'status': 'ok',
            'result': valid,
        }

        if not valid:
            response_data['error_message'] = llm_data.get('overall_message', error_message)
            if 'actions_validation' in llm_data:
                response_data['validation_details'] = llm_data.get('actions_validation')
            if 'reason' in llm_data:
                response_data['reason'] = llm_data.get('reason')

        logger.info(f"[validate_actions_view] Returning validation result successfully")
        return Response(response_data, status=200)

    except Exception as e:
        logger.error(f"[validate_actions_view] Unhandled exception: {str(e)}", exc_info=True)
        return Response({
            'status': 'error',
            'result': None,
            'error_message': error_message
        }, status=500)


@api_view(['POST'])
def generate_action_list_view(request):
    error_message = "Please try again!"
    try:
        body = request.data
        user_problem_statement = body.get('user_problem_statement')
        user_objective = body.get('user_objective')
        language = body.get('language')
        profile_id = body.get('profile_id')

        logger.info(
            f"[generate_action_list_view] Request received - user_problem_statement: {user_problem_statement}, "
            f"user_objective: {user_objective}, language: {language}, profile_id: {profile_id}")

        if isinstance(user_objective, str) and user_objective.strip() != "":
            user_objective = [user_objective.strip()]

        elif not isinstance(user_objective, list):
            raise ValueError("Invalid user_objective format")

        profile = Profile.objects.filter(id=profile_id).first()
        if profile:
            company_bot = CompanyBot.objects.get(company=profile.company, route='/action_list')
        else:
            company_bot = CompanyBot.objects.get(route='/action_list')

        voice_provider = Voice.objects.filter(
            company_bot=company_bot, type=VoiceType.TextToText, language=language
        ).first()

        bot_vernacular = BotVernacular.objects.filter(company_bot=company_bot, language=language).first()
        error_message = bot_vernacular.error_message if bot_vernacular and bot_vernacular.error_message \
            else "Please try again!"
        if voice_provider and language != 'en':
            error_message = translate_field(voice_provider=voice_provider, message_body=error_message, target_language=language)
            logger.info(f"[generate_action_list_view] No action plans generated, error message: {error_message}")

        # Call async fan-out from sync DRF view safely (production-safe under ASGI)
        gen_result = async_to_sync(generate_action_list_parallel)(
            query=user_problem_statement,
            objectives=user_objective,
            company_bot=company_bot,
            language=language,
            voice_provider=voice_provider
        )


        action_list = gen_result['action_list']
        chunk_response = gen_result.get('chunks_response', None)
        filtered_chunks = gen_result.get('filtered_chunks', [])

        if not action_list:
            logger.info(f"[generate_action_list_view] Empty action list, returning early")
            return Response({
                'status': 'error',
                'message': error_message,
                'action_list': []
            }, status=500)

        post_result = post_process_actions_with_source(action_list, filtered_chunks, chunk_response)

        if post_result['status'] != 'ok':
            logger.error(f"[generate_action_list_view] Post-processing failed: {post_result.get('message')}")
            return Response({
                'status': post_result['status'],
                'message': error_message,
                'action_list': []
            }, status=post_result['status_code'])

        action_list = post_result['action_list']

        if language != 'en':
            logger.info(f"[generate_action_list_view] Translating action steps to {language}")
            for idx, action_item in enumerate(action_list):
                action_steps = action_item.get('actionSteps', [])
                if action_steps:
                    translated_steps = translate_field(
                        voice_provider=voice_provider, message_body=json.dumps(action_steps), target_language=language,
                        source_language='en'
                    )

                    if isinstance(translated_steps, str):
                        try:
                            translated_steps = json_repair.repair_json(translated_steps, return_objects=True)
                            logger.info(
                                f"[generate_action_list_view] Successfully translated action steps for plan {idx + 1}")
                        except Exception as e:
                            logger.error(
                                f"[generate_action_list_view] Error parsing translated steps for plan {idx + 1}: {e}")
                            translated_steps = action_steps

                    action_item['actionSteps'] = translated_steps

        # logger.info(f"[generate_action_list_view] Returning {len(action_list)} action plans successfully")
        return Response({
            'status': 'ok',
            'message': "Response generated successfully",
            'action_list': action_list
        }, status=200)

    except Exception as e:
        logger.error(f"[generate_action_list_view_v2] Unhandled exception: {str(e)}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': error_message if error_message else "Please try again!"
        }, status=500)


@api_view(['POST'])
def generate_title_view(request):
    try:
        body = request.data
        user_problem_statement = body.get('user_problem_statement')
        user_objective = body.get('user_objective')
        user_action_list = body.get('user_action_list')
        language = body.get('language')
        profile_id = body.get('profile_id')

        logger.info(
            f"[generate_title_view] Request received - user_problem_statement: {user_problem_statement}, "
            f"user_objective: {user_objective}, language: {language}, profile_id: {profile_id}")

        profile = Profile.objects.filter(id=profile_id).first()
        if profile:
            company_bot = CompanyBot.objects.get(company=profile.company, route='/title')
        else:
            company_bot = CompanyBot.objects.get(route='/title')

        voice_provider = Voice.objects.filter(
            company_bot=company_bot, type=VoiceType.TextToText, language=language
        ).first()

        if language != 'en':
            logger.info(f"[generate_title_view] Translating inputs from {language} to English")
            user_problem_statement = translate_field(
                voice_provider=voice_provider, message_body=user_problem_statement, source_language=language,
                target_language='en'
            )
            user_objective = translate_field(
                voice_provider=voice_provider, message_body=user_objective, source_language=language,
                target_language='en'
            )

            if isinstance(user_action_list, list):
                user_action_list = user_action_list[0]
                user_action_list = user_action_list.get('actionSteps')
                logger.info(f"[generate_title_view] Extracting action steps from list")
                user_action_list = [
                    translate_field(
                        voice_provider=voice_provider, message_body=action, source_language=language,
                        target_language='en'
                    ) for action in user_action_list
                ]
            else:
                user_action_list = translate_field(
                    voice_provider=voice_provider, message_body=user_action_list, source_language=language,
                    target_language='en'
                )

            logger.info(f"[generate_title_view] Translated problem statement: {user_problem_statement}")
            logger.info(f"[generate_title_view] Translated objective: {user_objective}")
            logger.info(f"[generate_title_view] Translated action list: {user_action_list}")

        input_data = {
            "user_problem_statement": user_problem_statement,
            "user_objective": user_objective,
            "user_action_list": user_action_list
        }

        logger.info(f"[generate_title_view] Calling generate_title_utils")
        title = generate_title_utils(input_data=input_data, company_bot=company_bot)
        logger.info(f"[generate_title_view] Generated title: {title}")

        if language != 'en':
            logger.info(f"[generate_title_view] Translating title to {language}")
            title = translate_field(
                voice_provider=voice_provider, message_body=title, target_language=language,
                source_language='en'
            )
            logger.info(f"[generate_title_view] Translated title: {title}")

        logger.info(f"[generate_title_view] Returning title successfully")
        return Response({
            'status': 'ok',
            'title': title
        }, status=200)

    except Exception as e:
        logger.error(f"[generate_title_view] Unhandled exception: {str(e)}", exc_info=True)
        return Response({
            'status': 'error',
            'title': ''
        }, status=500)


@api_view(['POST'])
def validate_title_view(request):
    try:
        body = request.data
        user_actions = body.get('user_actions')
        user_objective = body.get('user_objective')
        language = body.get('language')
        problem_statement = body.get('problem_statement')
        user_input = body.get('user_input')
        profile_id = body.get('profile_id')

        logger.info(
            f"[validate_title_view] Request received - user_input: {user_input}, user_objective: {user_objective}, "
            f"language: {language}, profile_id: {profile_id}")

        profile = Profile.objects.filter(id=profile_id).first()
        if profile:
            company_bot = CompanyBot.objects.get(company=profile.company, route='/validate-title')
        else:
            company_bot = CompanyBot.objects.get(route='/validate-title')

        bot_vernacular = BotVernacular.objects.filter(company_bot=company_bot, language=language).first()
        error_message = bot_vernacular.error_message if bot_vernacular and bot_vernacular.error_message else \
            "Please try again!"

        if language != 'en':
            logger.info(f"[validate_title_view] Translating inputs from {language} to English")
            voice_provider = Voice.objects.filter(
                company_bot=company_bot, type=VoiceType.TextToText, language=language
            ).first()

            if isinstance(user_actions, list):
                user_actions = user_actions[0]
                user_actions = user_actions.get('actionSteps')
                logger.info(f"[validate_title_view] Extracting action steps from list")
                user_actions = [
                    translate_field(
                        voice_provider=voice_provider, message_body=action, source_language=language,
                        target_language='en'
                    ) for action in user_actions
                ]
            else:
                user_actions = translate_field(
                    voice_provider=voice_provider, message_body=user_actions, source_language=language,
                    target_language='en'
                )

            user_objective = translate_field(
                voice_provider=voice_provider, message_body=user_objective, source_language=language,
                target_language='en'
            )
            problem_statement = translate_field(
                voice_provider=voice_provider, message_body=problem_statement, source_language=language,
                target_language='en'
            )
            user_input = translate_field(
                voice_provider=voice_provider, message_body=user_input, source_language=language,
                target_language='en'
            )

            logger.info(f"[validate_title_view] Translated user input: {user_input}")
            logger.info(f"[validate_title_view] Translated user actions: {user_actions}")
            logger.info(f"[validate_title_view] Translated user objective: {user_objective}")
            logger.info(f"[validate_title_view] Translated problem statement: {problem_statement}")

        logger.info(f"[validate_title_view] Calling validate_title_utils")
        response = validate_title_utils(
            user_input=user_input, user_objective=user_objective, problem_statement=problem_statement,
            user_actions=user_actions, company_bot=company_bot
        )
        logger.info(f"[validate_title_view] Validation result: {response}")

        logger.info(f"[validate_title_view] Returning validation result successfully")
        return Response({
            'status': 'ok',
            'result': response,
            'error_message': error_message
        }, status=200)

    except Exception as e:
        logger.error(f"[validate_title_view] Unhandled exception: {str(e)}", exc_info=True)
        return Response({
            'status': 'error',
            'result': None,
            'error_message': "Please try again!"
        }, status=500)

@api_view(['POST'])
def update_project_status_view(request):
    try:
        body = request.data
        access_token = body.get('access_token')
        project_id = body.get('project_id')
        flow = body.get('flow')
        status = body.get("status", "completed")

        logger.info(
            f"[update_project_status_view] Request received - project_id: {project_id}, flow: {flow}, status: {status}")

        if not project_id:
            logger.info(f"[update_project_status_view] No project_id provided, skipping")
            return JsonResponse(
                {"message": "Project ID not provided. Skipping this API call."},
                status=200
            )

        session = None
        project = Project.objects.filter(project_id=project_id).first()

        if project:
            logger.info(f"[update_project_status_view] Project found: {project}")
            if project.story:
                session = project.story.session
                logger.info(f"[update_project_status_view] Session: {session}")

        if (project and project.story and flow in [SessionFlowName.Reflection, SessionFlowName.GuestMiStory] and
                status == 'completed'):
            logger.info(f"[update_project_status_view] Processing story media for project")
            story_media_objects = StoryMedia.objects.filter(
                story=project.story, include_in_story=True
            ).exclude(media_type=MediaTypeChoices.PDF)
            serialized_data = StoryMediaRetrieveSerializer(story_media_objects, many=True).data
            logger.info(f"[update_project_status_view] Found {len(serialized_data)} story media objects")

            with ThreadPoolExecutor() as executor:
                futures = [executor.submit(
                    upload_to_cloud, session_value=session, access_token=access_token, instance=story_obj, story=None
                ) for story_obj in serialized_data]

                for future in as_completed(futures):
                    future.result()

            logger.info(f"[update_project_status_view] Story media uploaded, updating story PDF")
            update_story_pdf(is_edit_story=True, session=session, access_token=access_token, flow=flow)

        logger.info(f"[update_project_status_view] Calling update_project_status_utils")
        response = update_project_status_utils(
            project_id=project_id, access_token=access_token, status=status
        )
        logger.info(f"[update_project_status_view] Update response: {response}")

        logger.info(f"[update_project_status_view] Returning response successfully")
        return JsonResponse(response.get("message"), status=response.get("status"), safe=False)

    except Exception as e:
        logger.error(f"[update_project_status_view] Unhandled exception: {str(e)}", exc_info=True)
        return JsonResponse({'message': f"{e}"}, status=500)
