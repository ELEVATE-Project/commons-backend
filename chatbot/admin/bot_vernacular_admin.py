from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from chatbot.filter.custom_date_from_filter import CustomAdvanceDateFilter
from chatbot.models import BotVernacular
from chatbot.models.story_vernacular_model import StoryVernacular


@admin.register(BotVernacular)
class BotVernacularAdmin(SimpleHistoryAdmin):
    list_display = ('company_bot', 'language', 'introductory_message', 'created_at')
    list_filter = (
        'company_bot', 
        'language',
        CustomAdvanceDateFilter,
    )
    inlines = []
    raw_id_fields = ('company_bot', )
    search_fields = ('company_bot__name', 'language', 'introductory_message')
    date_hierarchy = 'created_at'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.order_by('company_bot', 'language')


@admin.register(StoryVernacular)
class StoryVernacularAdmin(SimpleHistoryAdmin):
    list_display = ('company_bot', 'language', 'created_at')
    list_filter = (
        'company_bot', 
        'language',
        CustomAdvanceDateFilter,
    )
    inlines = []
    raw_id_fields = ('company_bot', )
    search_fields = ('company_bot__name', 'language')
    date_hierarchy = 'created_at'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.order_by('company_bot', 'language')