from django.contrib import admin
from chatbot.filter.custom_date_from_filter import CustomAdvanceDateFilter
from observability.models import BotRunTestCaseMap


@admin.register(BotRunTestCaseMap)
class CompanyBotRunTestCaseMapAdmin(admin.ModelAdmin):
    list_display = ('bot_run', 'metric_name', 'test_case', 'status', 'created_at')
    raw_id_fields = ('bot_run', 'test_case', )
    
    list_filter = (
        'status',
        'metric_name',
        ('bot_run', admin.RelatedFieldListFilter),
        ('test_case', admin.RelatedFieldListFilter),
        CustomAdvanceDateFilter,
    )
    
    search_fields = (
        'metric_name',
        'status',
        'bot_run__id',
        'test_case__about',
        'response_log',
    )
    
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)