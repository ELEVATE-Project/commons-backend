from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from chatbot.filter.custom_date_from_filter import CustomAdvanceDateFilter
from chatbot.models import PDFTemplates


@admin.register(PDFTemplates)
class PDFTemplatesAdmin(SimpleHistoryAdmin):
    """Admin interface for PDFTemplates model."""
    list_display = (
        'template_name', 'user_type', 'created_at', 'updated_at', 'flow'
    )
    list_filter = (
        'user_type',
        'flow',
        CustomAdvanceDateFilter
    )
    search_fields = ('template_name',)
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('template_name', 'user_type', 'flow')
        }),
        ('Template Content', {
            'fields': ('template', 'constants_json'),
            'description': 'Configure the template content and constants.'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at')
    
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """Customize form fields."""
        if db_field.name == 'template':
            kwargs['widget'] = admin.widgets.AdminTextareaWidget(attrs={'rows': 20, 'cols': 100})
        elif db_field.name == 'constants_json':
            kwargs['help_text'] = 'Enter constants as JSON object, e.g., {"key1": "value1", "key2": "value2"}'
        return super().formfield_for_dbfield(db_field, request, **kwargs)
