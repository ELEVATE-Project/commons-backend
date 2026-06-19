from django.contrib import admin
from chatbot.filter.custom_date_from_filter import CustomAdvanceDateFilter
from observability.models import CompanyBotTCRun


@admin.register(CompanyBotTCRun)
class CompanyBotTCRunAdmin(admin.ModelAdmin):
    readonly_fields = ['status', 'metrics_result']
    raw_id_fields = ('company_bot', )
    list_display = ('company_bot', 'status', 'created_at')
    
    list_filter = (
        'status',                          
        ('company_bot', admin.RelatedFieldListFilter),
        CustomAdvanceDateFilter,
    )
    
    search_fields = ('company_bot__name', 'status')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)