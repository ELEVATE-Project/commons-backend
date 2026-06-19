import base64
from django.core.files.base import ContentFile
from django.utils.timezone import now
from celery import shared_task
from channels.layers import get_channel_layer
from chatbot.models import CompanyChat, Profile, CompanyBot
from chatbot.models.geo_models import ProfileAddress


channel_layer = get_channel_layer()


@shared_task
def save_in_company_db(
        session_id, profile_id, initiated_by, message, chunks, status, translated_message=None, audio_base64=None,
        stage=None, other_params=None
):
    if initiated_by == 'AI':
        receiver = Profile.objects.filter(id=profile_id).first()
        sender = Profile.objects.get(id=1)
    else:
        sender = Profile.objects.filter(id=profile_id).first()
        receiver = Profile.objects.get(id=1)

    last_chat = CompanyChat.objects.filter(session=session_id).order_by('-created_at').first()
    print(last_chat)

    # if audio_base64:
    #     audio_file = base64_to_audio_file(base64_string=audio_base64, session_id=session_id)
    # else:
    #     audio_file=None

    if last_chat and last_chat.sender == sender:
        last_chat.message = message
        last_chat.translated_message = translated_message
        last_chat.chunks = chunks
        last_chat.status = status
        if audio_base64:
            if last_chat.file_url:
                last_chat.file_url = f"{last_chat.file_url},{audio_base64}"
            else:
                last_chat.file_url = audio_base64
        
        last_chat.stage = stage
        last_chat.other_params = other_params
        last_chat.save()
    else:
        company_chat = CompanyChat(
            message=message,
            translated_message=translated_message,
            chunks=chunks,
            sender=sender,
            receiver=receiver,
            session=session_id,
            status=status,
            file_url=audio_base64,
            stage=stage,
            other_params=other_params
        )
        company_chat.save()


@shared_task
def get_company_bot(profile, route):
    company = profile.company
    print(company.slug)
    company_bot = CompanyBot.objects.filter(company=company).order_by('created_at')
    print(company_bot)
    if company.slug == 'shikshalokam':
        if route == 'testimonial':
            return company_bot[2]
        profile_address = ProfileAddress.objects.get(profile=profile)
        state = profile_address.state
        if state == 'Karnataka':
            return company_bot[1]
    return company_bot[0]


def base64_to_audio_file(base64_string, session_id):
    """Convert Base64 string to Django File object"""
    if not base64_string:
        return None

    try:
        format, audio_str = base64_string.split(";base64,")
        ext = format.split("/")[-1]
        audio_data = base64.b64decode(audio_str)

        filename = f"{session_id}/{int(now().timestamp())}.{ext}"

        return ContentFile(audio_data, name=filename)
    except Exception as e:
        print(f"Base64 conversion error: {e}")
        return None
