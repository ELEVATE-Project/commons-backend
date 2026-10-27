import csv
from itertools import groupby

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Prefetch
from django.http import HttpResponse
from django.urls import path
from django.utils import timezone
from simple_history.admin import SimpleHistoryAdmin
from chatbot.constants.constants import TITLE_KEY
from chatbot.filter.custom_date_from_filter import CustomAdvanceDateFilter
from chatbot.models import Theme, ThemeType, ResourceTheme, ThemeStatus, Profile, KeyValue, MediaSecondaryTheme
from chatbot.utils.company_utils import get_user_company
# from rangefilter.filters import DateTimeRangeFilter

SECONDARY_MAPPING_EXPORT_FIELDS = (
    'Resource', 'Assigned Primary Theme', 'AI-Recommended Secondary Themes', 'AI Confidence Scores'
)
CSV_FORMULA_PREFIXES = ('=', '+', '-', '@', '\t', '\r')
def csv_safe(value):
    return f"'{value}" if isinstance(value, str) and value.startswith(CSV_FORMULA_PREFIXES) else value


def csv_response(filename):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('﻿')
    return response


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


class ResourceThemeTypeFilter(admin.SimpleListFilter):
    title = 'Theme type'
    parameter_name = 'theme_type'
    PRIMARY = 'primary'
    SECONDARY = 'secondary'
    ALL = 'all'

    def lookups(self, request, model_admin):
        return ((self.ALL, 'All'), (self.PRIMARY, 'Primary'), (self.SECONDARY, 'Secondary'))

    def queryset(self, request, queryset):
        if self.value() in (self.PRIMARY, self.SECONDARY):
            return queryset.filter(is_primary=self.value() == self.PRIMARY)
        return queryset


@admin.register(ResourceTheme)
class ResourceThemeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_primary', 'status', 'created_at')
    list_filter = (ResourceThemeTypeFilter, 'status', CustomAdvanceDateFilter)
    list_editable = ('status',)
    search_fields = ('name', 'code', 'description')
    raw_id_fields = ('created_by',)
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'
    ordering = ('-is_primary', 'name')
    actions = ('mark_published', 'mark_draft')

    def get_urls(self):
        custom_urls = [
            path('export-csv/', self.admin_site.admin_view(self.export_csv_view),
                 name='chatbot_resourcetheme_export_csv'),
        ]
        return custom_urls + super().get_urls()

    def export_csv_view(self, request):
        if not (self.has_view_permission(request) and request.user.has_perm('chatbot.view_media')):
            raise PermissionDenied
        themes = self.get_changelist_instance(request).queryset.filter(is_primary=False)
        links = (
            MediaSecondaryTheme.objects.filter(theme__in=themes.values('pk'), media__parent__isnull=True)
            .select_related('theme', 'media__primary_theme')
            .prefetch_related(Prefetch(
                'media__key_values', queryset=KeyValue.objects.filter(key=TITLE_KEY), to_attr='title_values'
            ))
            .order_by('media_id', '-confidence')
        )
        if not request.user.is_superuser:
            company = get_user_company(request.user)
            links = links.filter(media__organization=company) if company else links.none()

        response = csv_response(f'secondary_theme_mapping_{timezone.localdate():%Y%m%d}.csv')
        writer = csv.writer(response)
        writer.writerow(SECONDARY_MAPPING_EXPORT_FIELDS)
        for _, media_links in groupby(links, key=lambda link: link.media.id):
            media_links = list(media_links)
            media = media_links[0].media
            title = media.title_values[0].value if media.title_values else ''
            writer.writerow([
                csv_safe(title or media.name),
                csv_safe(media.primary_theme.name if media.primary_theme else ''),
                csv_safe(', '.join(link.theme.name for link in media_links)),
                ', '.join(f'{link.confidence:.2f}' if link.confidence is not None else '-' for link in media_links),
            ])
        return response

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('created_by').annotate(
            primary_count=Count('primary_media', distinct=True),
            secondary_count=Count('media_links', distinct=True),
        )

    @admin.display(description='Media')
    def media_count(self, obj):
        return obj.primary_count if obj.is_primary else obj.secondary_count

    def has_add_permission(self, request):
        return False

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ('code', 'description')
        return self.readonly_fields

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
