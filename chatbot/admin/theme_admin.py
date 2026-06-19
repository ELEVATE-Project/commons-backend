from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from chatbot.filter.custom_date_from_filter import CustomAdvanceDateFilter
from chatbot.models import Theme, ThemeType
# from rangefilter.filters import DateTimeRangeFilter


@admin.register(Theme)
class ThemeAdmin(SimpleHistoryAdmin):
    list_display = ('bot', 'theme_type', 'created_at', 'updated_at')
    list_filter = (
        CustomAdvanceDateFilter,
        # ('updated_at', DateTimeRangeFilter),
        'bot', 
        'theme_type'
    )
    search_fields = ('bot__name', 'themes')
    raw_id_fields = ('bot', 'master_theme')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        # Remove fields based on theme_type
        if obj:
            if obj.theme_type == ThemeType.MASTER:
                # Hide 'themes' field
                form.base_fields.pop('themes', None)
            else:
                # Hide 'master_theme' field
                form.base_fields.pop('master_theme', None)
        else:
            # On add form, hide 'master_theme' initially
            form.base_fields.pop('master_theme', None)
        return form

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        # Optionally, adjust behavior dynamically if needed
        return super().changeform_view(request, object_id, form_url, extra_context)
