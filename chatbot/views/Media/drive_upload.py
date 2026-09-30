from django.views.generic import TemplateView

from chatbot.models import CompanyBot
from chatbot.views.Media.admin_context import add_media_admin_context
from chatbot.views.Media.google_drive_integration import get_default_extraction_bot
from chatbot.utils.company_utils import get_companies_for_display, get_user_company
import chatbot.constants.endpoints as ENDPOINTS


class DriveUploadView(TemplateView):
    template_name = 'drive_upload.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        add_media_admin_context(context, self.request, 'Drive Upload')

        # Set superuser flag for template
        context['is_superuser'] = getattr(self.request.user, 'is_superuser', False)
        context['companies'] = get_companies_for_display(self.request.user)

        default_bot = get_default_extraction_bot()
        context['default_bot_id'] = default_bot.id if default_bot else None
        if self.request.path.startswith('/admin/'):
            context['google_drive_auth_url'] = ENDPOINTS.GOOGLE_DRIVE_AUTH_URL
            context['google_drive_file_import_url'] = ENDPOINTS.GOOGLE_DRIVE_FILES_IMPORT_URL
            context['list_repositories_url'] = ENDPOINTS.LIST_REPOSITORIES_URL
        else:
            context['google_drive_auth_url'] = ENDPOINTS.NON_ADMIN_GOOGLE_DRIVE_AUTH_URL
            context['google_drive_file_import_url'] = ENDPOINTS.NON_ADMIN_GOOGLE_DRIVE_FILES_IMPORT_URL
            context['list_repositories_url'] = ENDPOINTS.NON_ADMIN_LIST_REPOSITORIES_URL

        user_company = get_user_company(self.request.user)
        if user_company:
            context['user_company'] = user_company

        return context
