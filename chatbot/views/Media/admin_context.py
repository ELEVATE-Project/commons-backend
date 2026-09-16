from django.contrib import admin

from chatbot.models.media_models import Media


def add_media_admin_context(context, request, title):
    context.update(admin.site.each_context(request))
    context.update({
        'app_label': Media._meta.app_label,
        'opts': Media._meta,
        'title': title,
    })
    return context
