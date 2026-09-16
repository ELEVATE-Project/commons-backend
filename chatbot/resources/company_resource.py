from import_export.resources import ModelResource
from import_export.fields import Field
from chatbot.models import ChatSession, CompanyChat


class ChatSessionResource(ModelResource):
    transcription = Field(attribute='transcription', column_name='Transcription')

    class Meta:
        model = ChatSession
        fields = (
            'transcription',
        )

    def dehydrate_transcription(self, obj):
        chats = CompanyChat.objects.filter(session=obj.session).order_by('created_at')
        if not chats.exists():
            return "-"
        formatted_chats = [
            (f'{chat.created_at.strftime("%Y-%m-%d %H:%M")} - {chat.sender.first_name if chat.sender else "System"}: '
             f'{chat.message}')
            for chat in chats
        ]
        return "\n\n".join(formatted_chats) + " | "

