import os
from jwt import ExpiredSignatureError, InvalidTokenError
from rest_framework.decorators import api_view
from rest_framework.response import Response
from chatbot.models import CompanyChat, ChatSession, ChatStatus, Profile, Company, TextConversionType, Voice, VoiceType
import jwt
from django.http import JsonResponse
from chatbot.celery_tasks.ptm_report_tasks import create_ptm_report
from chatbot.utils.audio_provider_utils import text_translate_provider
from chatbot.utils.ptm_utils.chat_utils import save_question_answer_utils
from chatbot.utils.transliterate_utils import transliterate_text

JWT_PUBLIC_KEY = os.getenv("JWT_PUBLIC_KEY")


@api_view(['POST'])
def save_chats_view(request):
    body = request.data
    message = body.get('message')
    session = body.get('session')
    status = body.get('status', 'COMPLETED')
    role = body.get('role')
    chunks = body.get('chunks')
    user_profile = None
    if not message or not session:
        return Response({"error": "message and session are required."}, status=400)

    print("message: ", message)


    try:
        ai_user = Profile.objects.get(id=1)
    except Profile.DoesNotExist:
        return Response({"error": "AI profile not found."}, status=400)

    try:
        chat_session = ChatSession.objects.get(session=session)
        if chat_session:
            user_profile = chat_session.profile
    except ChatSession.DoesNotExist:
        return Response({"error": "chat_session not found."}, status=400)


    if role == 'bot':
        sender = ai_user
        receiver = user_profile
    elif role == 'user':
        sender = user_profile
        receiver = ai_user
    else:
        return Response({"error": "Invalid role. Must be 'bot' or 'user'."}, status=400)

    CompanyChat.objects.create(
        message=message,
        session=session,
        status=status,
        sender=sender,
        receiver=receiver,
        chunks=chunks
    )


    return Response({
        'status': 'ok',
        'message': 'Message saved successfully!'
    }, status=200)


@api_view(['POST'])
def create_chatsession(request):
    body = request.data
    session = body.get('session')
    email = body.get('email')
    preferred_language =  body.get('preferred_language', {}).get('value')

    access_token = request.headers.get("X-auth-token")
    if not access_token:
        return JsonResponse({"message": "Access token missing"}, status=401)

    try:
        decoded = jwt.decode(
            access_token,
            JWT_PUBLIC_KEY,
            algorithms=["HS256"]
        )
        user_id = decoded.get("data", {}).get("id")
        first_name = decoded.get("data", {}).get("name")
        user_roles = decoded.get("roles", [])

    except ExpiredSignatureError:
        return JsonResponse({"message": "Access token expired"}, status=401)

    except InvalidTokenError:
        return JsonResponse({"message": "Invalid access token"}, status=401)


    if not session:
        return Response({"error": "session is required."}, status=400)

    if not email:
        return Response({"error": "Email is required."}, status=400)

    try:
        company = Company.objects.get(slug='shikshalokamstaging')
    except Exception as e:
        return Response({"error": f"{e}"}, status=400)

    profile, created = Profile.objects.get_or_create(
        userid = user_id,
        defaults={
            'first_name': first_name,
            'email': email,
            'password': 'grit@123',
            'preferred_route': preferred_language,
            'company': company,
            "designation": user_roles
        }
    )

    c, created = ChatSession.objects.get_or_create(
        session=session,
        defaults={
            'session_status': ChatStatus.IN_PROGRESS,
            'profile': profile,
        }
    )

    return Response({
        'status': 'ok',
        'message': 'Chatsession created!' if created else 'Chatsession already exists!',
        'chatsession': {
            'session': c.session,
            'session_status': c.session_status,
            'profile_id': profile.id
        }
    }, status=200)


@api_view(['POST'])
def save_ptm_chats(request):
    body = request.data
    session = body.get('session')
    status = body.get('status', 'COMPLETED')
    flow = body.get('flow')
    profile_id = body.get('profile_id')
    question_id = body.get('id')
    answer_id = body.get('answer_id')
    sequence = body.get('sequence')
    question = body.get('question')
    translated_message = body.get('translated_question')
    answer = body.get('answer')
    language = body.get('language')
    sent_at = body.get('sent_at')
    audio_file = body.get('audio_url')
    service = body.get('service')
    # should_transliterate = body.get('should_transliterate', False)

    if not question or not session or not answer:
        return Response({"error": "question, answer and session are required."}, status=400)

    res = save_question_answer_utils(
        profile_id=profile_id, flow=flow, session=session, sequence=sequence, status=status,
        language=language, question_id=question_id, sent_at=sent_at, question=question,
        translated_message=translated_message, answer=answer,
        audio_file=audio_file, answer_id=answer_id, service=service
        # should_transliterate=should_transliterate,
    )

    if res.get("status") != 200:
        return Response(res, status=res.get("status"))

    # if status == "COMPLETED":
    #     create_ptm_report.delay(
    #         profile_id=profile_id,
    #         session=session,
    #         flow=flow,
    #         language=language
    #     )

    return Response({
        "status": "ok",
        "message": res.get("message", "Message saved successfully!")
    }, status=200)
