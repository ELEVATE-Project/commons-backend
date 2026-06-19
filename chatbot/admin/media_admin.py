from django.contrib import admin
from django.shortcuts import render
from django.http import HttpResponseRedirect
from django.contrib.admin.decorators import action
from .generic_upload_admin import BatchUploadMixin
from chatbot.filter.custom_date_from_filter import CustomAdvanceDateFilter
from chatbot.form.media.media_form import MediaAdminForm
from chatbot.models import Tag, Profile, TagChoices, TagSourceChoices
from chatbot.models.media_models import Media, KeyValue, MediaImage
from chatbot.models.enums import FileDisplayMode, ProfileType
from simple_history.admin import SimpleHistoryAdmin
from chatbot.utils.knowledge_service.cache_manager import GetCachedItemView
from chatbot.views.Media.extract_views import BatchMediaExtractView, BatchMediaRetryExtractView
from chatbot.views.Media.save_views import BatchMediaSaveView, BatchMediaRetrySaveView
from chatbot.views.Media.status_views import BatchMediaTaskStatusView, VectorDBTaskStatusView
from chatbot.views.Media.upload_views import BatchMediaUploadView
from chatbot.views.Media.google_drive_integration import (
    GoogleDriveAuthView,
    GoogleDriveCallbackView,
    GoogleDriveFilesView,
    GoogleDriveFileImportView,
    GoogleDriveIntegrationView,
)


class KeyValueInline(admin.TabularInline):
    model = KeyValue
    extra = 1


class MediaImagesInline(admin.TabularInline):
    model = MediaImage
    extra = 1
    fk_name = 'media'
    fields = ('name', 'media_type', 'page', 'width', 'height')
    readonly_fields = ('created_at',)


@admin.register(Media)
class MediaAdmin(SimpleHistoryAdmin, admin.ModelAdmin):
    form = MediaAdminForm
    list_display = (
        'file_name', 'get_title', 'media_type', 'display_mode', 'parent__name',
        'view_count', 'download_count', 'updated_at', 'created_at'
    )
    list_filter = (
        CustomAdvanceDateFilter,
        'display_mode',
        'name',
        'media_type',
        'company_bot'
    )
    search_fields = ('name', 'key_values__value')
    actions = ['export_selected', 'change_display_mode_action']
    list_export = ('csv', 'xlsx')
    inlines = [KeyValueInline, MediaImagesInline]
    raw_id_fields = ('company_bot', 'parent', 'organization')
    date_hierarchy = 'created_at'
    readonly_fields = ('view_count', 'download_count', 'thumbnail')
    ordering = ('-created_at',)

    def file_name(self, obj):
        return obj.name

    file_name.short_description = "File name"

    def get_title(self, obj):
        """Get TITLE from key-value pairs"""
        try:
            title_kv = obj.key_values.filter(key__iexact='title').first()
            if title_kv and title_kv.value:
                # Truncate long titles for display
                title = title_kv.value
                if len(title) > 50:
                    return f"{title[:47]}..."
                return title
            return "-"
        except Exception:
            return "-"

    get_title.short_description = 'Title'
    get_title.admin_order_field = 'key_values__value'

    def get_queryset(self, request):
        """Optimize queries by prefetching related objects"""
        qs = super().get_queryset(request)
        return qs.prefetch_related('key_values', 'tags', 'parent')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        manual_tags = getattr(obj, '_manual_tags_to_set', [])
        auto_tags = getattr(obj, '_auto_tags_to_preserve', [])

        print("manual_tags to set:", manual_tags)
        print("auto_tags to preserve:", auto_tags)

        obj.tags.set(manual_tags + auto_tags)

    def get_fieldsets(self, request, obj=None):
        # Check if user is a MODERATOR
        is_moderator = False
        try:
            profile = Profile.objects.get(email=request.user.email)
            is_moderator = profile.profile_type == ProfileType.MODERATOR
            print("Is User Moderator: ", is_moderator)
        except Profile.DoesNotExist:
            is_moderator = False

        if is_moderator:
            base_fields = ('name', 'organization', 'file', 'markdown_file', 'thumbnail', 'url', 'display_mode', 'description', 'extracted_text',
                           'media_type', 'view_count', 'download_count')
        else:
            base_fields = (
                'name', 'organization', 'file', 'markdown_file', 'thumbnail', 'url', 'display_mode', 'description', 'extracted_text', 'priority',
                'media_type', 'company_bot', 'parent', 'view_count', 'download_count'
            )

        fieldsets = [
            (None, {
                'fields': base_fields
            }),
            ('Manual Tags', {
                'fields': ('manual_tags',),
            }),
        ]

        if obj and obj.pk:
            if obj.tags.filter(created_by_id=1).exists():
                fieldsets.append(
                    ('Auto Tags', {
                        'fields': ('auto_tags',),
                        'description': 'Automatically generated tags'
                    })
                )

        return fieldsets

    def get_actions(self, request):
        """Remove the delete selected action"""
        actions = super().get_actions(request)
        # if 'delete_selected' in actions:
        #     del actions['delete_selected']
        return actions

    @action(description="Change display mode")
    def change_display_mode_action(self, request, queryset):
        """
        Custom action to change display_mode for selected Media objects.
        Redirects to a change form where user can select the new display_mode.
        """
        # Store the selected objects in the session for processing
        selected_ids = queryset.values_list('id', flat=True)
        request.session['selected_media_ids'] = list(selected_ids)

        # Redirect to the display mode change view
        return HttpResponseRedirect(f"{request.path}change-display-mode/")

    def change_display_mode(self, request):
        """
        View to handle display mode changes for selected media objects.
        """
        selected_ids = request.session.get('selected_media_ids', [])

        if not selected_ids:
            self.message_user(request, "No files selected.", level="error")
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', '../'))

        if request.method == 'POST':
            new_display_mode = request.POST.get('display_mode')
            apply_to = request.POST.get('apply_to', 'selected')

            if not new_display_mode:
                self.message_user(request, "Please select a display mode.", level="error")
                return HttpResponseRedirect(request.path)

            # Determine which objects to update
            if apply_to == 'all':
                media_objects = Media.objects.all()
            else:
                media_objects = Media.objects.filter(id__in=selected_ids)

            # Update display_mode for selected/all objects
            updated_count = media_objects.update(display_mode=new_display_mode)

            self.message_user(
                request,
                f"Successfully updated display mode for {updated_count} file(s) to '{new_display_mode}'."
            )

            # Clear the session
            if 'selected_media_ids' in request.session:
                del request.session['selected_media_ids']

            return HttpResponseRedirect('../')

        # GET request - show the form
        context = {
            'title': 'Change Display Mode',
            'selected_count': len(selected_ids),
            'display_mode_choices': FileDisplayMode.choices,
        }
        return render(request, 'admin/change_display_mode.html', context)

    def get_urls(self):
        """Add custom URLs for batch upload and display mode change"""
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path(
                'change-display-mode/',
                self.admin_site.admin_view(self.change_display_mode),
                name='chatbot_media_change_display_mode'
            ),
            path('batch-upload/',
                 self.admin_site.admin_view(BatchMediaUploadView.as_view()),
                 name='chatbot_media_batch_upload'),
            path('google-drive/',
                 self.admin_site.admin_view(GoogleDriveIntegrationView.as_view()),
                 name='chatbot_media_google_drive'),
            path('google-drive/auth/',
                 self.admin_site.admin_view(GoogleDriveAuthView.as_view()),
                 name='chatbot_media_google_drive_auth'),
            path('google-drive/callback/',
                 self.admin_site.admin_view(GoogleDriveCallbackView.as_view()),
                 name='chatbot_media_google_drive_callback'),
            path('google-drive/files/',
                 self.admin_site.admin_view(GoogleDriveFilesView.as_view()),
                 name='chatbot_media_google_drive_files'),
            path('google-drive/files/import/',
                 self.admin_site.admin_view(GoogleDriveFileImportView.as_view()),
                 name='chatbot_media_google_drive_file_import'),
            path('api/batch-extract/',
                 self.admin_site.admin_view(BatchMediaExtractView.as_view()),
                 name='chatbot_media_batch_extract'),
            path('api/batch-save/',
                 self.admin_site.admin_view(BatchMediaSaveView.as_view()),
                 name='chatbot_media_batch_save'),
            path('api/batch-task-status/',
                 self.admin_site.admin_view(BatchMediaTaskStatusView.as_view()),
                 name='chatbot_media_task_status'),
            path('api/retry-extract/',
                 self.admin_site.admin_view(BatchMediaRetryExtractView.as_view()),
                 name='chatbot_media_retry_extract'),
            path('api/retry-save/',
                 self.admin_site.admin_view(BatchMediaRetrySaveView.as_view()),
                 name='chatbot_media_retry_save'),
            path('api/vector-db-task-status/',
                 self.admin_site.admin_view(VectorDBTaskStatusView.as_view()),
                 name='chatbot_media_vector_db_task_status'),
            path('api/get-cached-item/',
                 self.admin_site.admin_view(GetCachedItemView.as_view()),
                 name='chatbot_media_get_cached_item'),
        ]
        return custom_urls + urls

    def delete_queryset(self, request, queryset):
        errors = []

        for obj in queryset:
            try:
                obj.delete()
            except Exception as e:
                errors.append(f"{obj.id}: {str(e)}")

        if errors:
            self.message_user(
                request,
                f"Some files failed to delete:\n" + "\n".join(errors),
                level="error"
            )


@admin.register(Tag)
class MasterTagAdmin(BatchUploadMixin, admin.ModelAdmin):
    list_display = ('name', 'status', 'source_type', 'created_by', 'created_at')
    list_filter = (
        CustomAdvanceDateFilter,
        'name',
        'created_by',
        'source_type'
    )
    raw_id_fields = ('created_by',)
    readonly_fields = ('source_type', 'company', 'created_by')
    search_fields = ('name', 'description')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)

    enable_batch_upload = True
    batch_upload_fields = ['name', 'status', 'description', 'created_by']

    def save_model(self, request, obj, form, change):
        print("In save")
        if not obj.pk:
            print("obj.pk= ", obj.pk)
            try:
                print("request.user.email: ", request.user.email)
                profile = Profile.objects.get(email=request.user.email)
                print("profile found: ", profile)
            except Profile.DoesNotExist:
                print("Exception profile doesnot exist")
                profile = None
            obj.created_by = profile
            obj.status = TagChoices.APPROVED
            obj.source_type = TagSourceChoices.MANUAL
        super().save_model(request, obj, form, change)
