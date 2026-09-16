from django.contrib import admin
from chatbot.filter.custom_date_from_filter import CustomAdvanceDateFilter
from observability.models import CompanyBotTestCases, TCBotRunMetrics


class TCBotRunMetricsAdmin(admin.TabularInline):
    model = TCBotRunMetrics
    extra = 1


@admin.register(CompanyBotTestCases)
class CompanyBotTestCasesAdmin(admin.ModelAdmin):
    list_display = ('company_bot', 'about', 'created_at')
    raw_id_fields = ('company_bot', )
    
    list_filter = (
        ('company_bot', admin.RelatedFieldListFilter),
        CustomAdvanceDateFilter,
    )
    
    # Adds search capability
    search_fields = ('about', 'company_bot__name', 'test_case_input', 'expected_output')
    
    date_hierarchy = 'created_at' 
    ordering = ('-created_at',)

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        # This method is called when the admin change form is rendered.
        if object_id:
            self.inlines = [TCBotRunMetricsAdmin]
        else:
            self.inlines = []
        return super().changeform_view(request, object_id, form_url, extra_context)