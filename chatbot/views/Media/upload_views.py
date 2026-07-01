from django.views.generic import TemplateView
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator
from chatbot.models import Tag, FileTypeChoices, TagSourceChoices, TagChoices
from chatbot.models.media_models import PriorityChoices
import json
from chatbot.utils.company_utils import get_company_queryset_for_user, get_user_company
from chatbot.views.Media.admin_context import add_media_admin_context


@method_decorator(staff_member_required, name='dispatch')
class BatchMediaUploadView(TemplateView):
    template_name = 'admin/batch_upload/batch_upload.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        add_media_admin_context(context, self.request, 'Batch Upload')
        context['media_types'] = FileTypeChoices.choices
        context['priorities'] = PriorityChoices.choices

        extension_mapping = FileTypeChoices.get_extension_mapping()
        context['file_types'] = [
            {
                'mime_type': choice[0],
                'label': choice[1],
                'extension': extension_mapping.get(choice[0], '')
            }
            for choice in FileTypeChoices.choices
        ]

        from chatbot.models import CompanyBot
        context['company_bots'] = CompanyBot.objects.all()
        default_bot = CompanyBot.objects.filter(route='/tag_extractor')
        if default_bot:
            default_bot = default_bot.first()
            context['default_bot_id'] = default_bot.id

        # Restrict the organization dropdown based on the logged-in user's role.
        context['companies'] = get_company_queryset_for_user(self.request.user)
        context['user_company'] = get_user_company(self.request.user)

        try:
            existing_tags_query = Tag.objects.filter(
                source_type=TagSourceChoices.MANUAL,
                status=TagChoices.APPROVED
            )

            context['existing_manual_tags'] = list(
                existing_tags_query.values_list('name', flat=True).distinct().order_by('name')
            )

            document_types = []
            try:
                tag_extractor_bot = CompanyBot.objects.filter(route='/tag_extractor').first()
                if tag_extractor_bot and tag_extractor_bot.other_params:
                    try:
                        other_params = json.loads(tag_extractor_bot.other_params) if isinstance(
                            tag_extractor_bot.other_params, str
                        ) else tag_extractor_bot.other_params

                        master_document_types = other_params.get('master_document_types', [])
                        if isinstance(master_document_types, list):
                            document_types = master_document_types
                    except (json.JSONDecodeError, TypeError):
                        pass
            except Exception as e:
                print(f"Error getting document types: {e}")

            if not document_types:
                document_types = []

            context['master_document_types'] = document_types

        except Exception as e:
            print(f"Error getting context data: {e}")
            context['existing_manual_tags'] = []
            context['master_document_types'] = []

        return context
