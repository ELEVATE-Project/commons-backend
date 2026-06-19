from django.contrib import admin
from django.shortcuts import render
from django.urls import path
from simple_history.admin import SimpleHistoryAdmin
from chatbot.filter.custom_date_from_filter import CustomAdvanceDateFilter
from chatbot.models import I18nTag, I18nTranslation
from chatbot.services.i18n_export_service import (
    get_supported_languages,
    export_translations_to_cloud,
)


class I18nTranslationInline(admin.TabularInline):
    """Inline admin for I18nTranslation to show translations within I18nTag admin."""
    model = I18nTranslation
    extra = 1
    fields = ('variable_name', 'language', 'value')
    ordering = ('variable_name', 'language')


@admin.register(I18nTag)
class I18nTagAdmin(SimpleHistoryAdmin):
    """Admin interface for I18nTag model."""
    list_display = (
        'tag_name', 'get_translation_count', 'created_at', 'updated_at'
    )
    list_filter = (
        CustomAdvanceDateFilter,
    )
    search_fields = ('tag_name',)
    date_hierarchy = 'created_at'
    ordering = ('tag_name',)
    inlines = [I18nTranslationInline]
    change_list_template = 'admin/i18n_change_list.html'
    
    fieldsets = (
        ('Tag Information', {
            'fields': ('tag_name',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at')
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'export-to-cloud/',
                self.admin_site.admin_view(self.export_i18n_view),
                name='chatbot_i18ntag_export_s3',
            ),
        ]
        return custom_urls + urls
    
    def export_i18n_view(self, request):
        """Handle export requests."""
        context = {
            'title': 'Export I18n Translations',
            'languages': get_supported_languages(),
            'opts': self.model._meta,
        }
        
        if request.method == 'POST':
            language = request.POST.get('language')
            
            if language:
                from django.contrib import messages
                import logging
                logger = logging.getLogger('django')
                
                try:
                    # Export translations to cloud
                    result = export_translations_to_cloud(language)
                    
                    if result['success']:
                        # Log public URLs to console
                        print("="*80)
                        print("I18N TRANSLATIONS EXPORT SUCCESSFUL")
                        print("="*80)
                        
                        for export in result['exports']:
                            print(f"{export['language_name']} ({export['language_code']}): {export['public_url']}")
                        
                        print("="*80)
                        
                        # Show success message to user
                        messages.success(
                            request,
                            f"{result['message']}. Check console for public URLs."
                        )
                    else:
                        # Show error message
                        messages.error(
                            request,
                            f"Export failed: {result.get('error', 'Unknown error')}"
                        )
                        logger.error(f"Export failed: {result.get('error', 'Unknown error')}")
                        
                except Exception as e:
                    error_msg = f"Unexpected error during export: {str(e)}"
                    messages.error(request, error_msg)
                    logger.error(error_msg)
                    import traceback
                    logger.error(traceback.format_exc())
        
        return render(request, 'admin/i18n_export.html', context)
    
    def get_translation_count(self, obj):
        """Display the count of translations for this tag."""
        return obj.translations.count()
    get_translation_count.short_description = 'Translations'
    get_translation_count.admin_order_field = 'translations__count'


@admin.register(I18nTranslation)
class I18nTranslationAdmin(SimpleHistoryAdmin):
    """Admin interface for I18nTranslation model."""
    list_display = (
        'tag_id', 'variable_name', 'language', 'created_at'
    )
    list_filter = (
        'language',
        'tag_id',
        CustomAdvanceDateFilter
    )
    search_fields = ('tag_id__tag_name', 'variable_name', 'value')
    date_hierarchy = 'created_at'
    ordering = ('tag_id', 'variable_name', 'language')
    raw_id_fields = ('tag_id',)
    
    fieldsets = (
        ('Translation Information', {
            'fields': ('tag_id', 'variable_name', 'language')
        }),
        ('Content', {
            'fields': ('value',),
            'description': 'Enter the translated text content.'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at')
    
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """Customize form fields."""
        if db_field.name == 'value':
            kwargs['widget'] = admin.widgets.AdminTextareaWidget(attrs={'rows': 6, 'cols': 80})
        return super().formfield_for_dbfield(db_field, request, **kwargs)
    
    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        qs = super().get_queryset(request)
        return qs.select_related('tag_id')
