from django.contrib import admin
from django.db.models import Count
from simple_history.admin import SimpleHistoryAdmin
from chatbot.filter.custom_date_from_filter import CustomAdvanceDateFilter
from chatbot.models import Theme, ThemeType, ResourceTheme, ThemeStatus, Profile
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


@admin.register(ResourceTheme)
class ResourceThemeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_primary', 'status', 'media_count', 'created_by', 'created_at')
    list_filter = ('is_primary', 'status', CustomAdvanceDateFilter)
    list_editable = ('status',)
    search_fields = ('name', 'code', 'description')
    raw_id_fields = ('created_by',)
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'
    ordering = ('-is_primary', 'name')
    actions = ('mark_published', 'mark_draft')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('created_by').annotate(
            primary_count=Count('primary_media', distinct=True),
            secondary_count=Count('media_links', distinct=True),
        )

    @admin.display(description='Media')
    def media_count(self, obj):
        return obj.primary_count if obj.is_primary else obj.secondary_count

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by_id:
            obj.created_by = Profile.objects.filter(email=request.user.email).first()
        super().save_model(request, obj, form, change)

    def _set_status(self, request, queryset, status):
        updated = queryset.update(status=status)
        self.message_user(request, f"{updated} theme(s) marked as {status}.")

    @admin.action(description='Mark selected as published')
    def mark_published(self, request, queryset):
        self._set_status(request, queryset, ThemeStatus.PUBLISHED)

    @admin.action(description='Mark selected as draft')
    def mark_draft(self, request, queryset):
        self._set_status(request, queryset, ThemeStatus.DRAFT)
