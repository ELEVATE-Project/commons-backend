from django.views.generic import TemplateView
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator
from chatbot.models import Tag, Profile, FileTypeChoices, TagSourceChoices, TagChoices, Company, EntityStatus
from chatbot.models.media_models import PriorityChoices
import json


@method_decorator(staff_member_required, name='dispatch')
class BatchMediaUploadView(TemplateView):
    template_name = 'admin/batch_upload/batch_upload.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
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

        # Add companies for organization selection
        context['companies'] = Company.objects.filter(status=EntityStatus.ACTIVE).order_by('name')

        # Add user's company info
        user_company = None
        if self.request.user.is_authenticated:
            try:
                user_profile = Profile.objects.get(email=self.request.user.email)
                user_company = user_profile.company
                context['user_company'] = user_company
            except Profile.DoesNotExist:
                pass

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
