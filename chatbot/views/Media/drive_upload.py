from django.views.generic import TemplateView

from chatbot.models import Company, CompanyBot, Profile
from chatbot.views.Media.google_drive_integration import get_default_extraction_bot


class DriveUploadView(TemplateView):
    template_name = 'drive_upload.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['companies'] = Company.objects.all().order_by('name')
        context['company_bots'] = CompanyBot.objects.all()

        default_bot = get_default_extraction_bot()
        context['default_bot_id'] = default_bot.id if default_bot else None
        if self.request.path.startswith('/admin/'):
            context['google_drive_auth_url'] = '/admin/chatbot/media/google-drive/auth/'
            context['google_drive_file_import_url'] = '/admin/chatbot/media/google-drive/files/import/'
        else:
            context['google_drive_auth_url'] = '/google-drive/auth/'
            context['google_drive_file_import_url'] = '/google-drive/files/import/'

        user_email = getattr(self.request.user, 'email', None)
        if user_email:
            profile = Profile.objects.filter(email=user_email).first()
            if profile and profile.company:
                context['user_company'] = profile.company

        return context
