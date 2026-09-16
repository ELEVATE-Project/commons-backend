from django.utils.html import format_html
from django.contrib import admin
from django.db.models import Q
from chatbot.filter.admin_filter import StoryCompanyFilter, StoryStateFilter, StoryDistrictFilter, StoryBlockFilter
from chatbot.filter.custom_date_from_filter import CustomAdvanceDateFilter
from chatbot.filter.flow_filter import FlowFilter
from chatbot.filter.story_filter import UserNameFilter
from chatbot.models import StoryTag, StoryMedia, Story, Profile, ProfileType, MediaTypeChoices, StoryTranslation
from chatbot.models.geo_models import ProfileAddress
from chatbot.resources.story_resource import (
    redirect_to_export_view, generate_csv_response, generate_xls_response, generate_docx_response,
    get_story_fields, get_story_data, generate_zip_response
)
from chatbot.utils.shikshalokam_story_utils import update_story_pdf, save_shikshalokam_story
from chatbot.views.admin.post_processing_views import PostProcessingView
from django.urls import path
from django.shortcuts import render
import tablib


class StoryTagInline(admin.TabularInline):
    model = StoryTag
    exclude = ['created_by']
    extra = 1  # Number of empty forms to display for adding new tags


class StoryMediaInline(admin.TabularInline):
    model = StoryMedia
    exclude = ['base64_str', 'file']
    extra = 0

    def public_url(self, obj):
        url = obj.get_public_url()
        if obj.media_type == MediaTypeChoices.PDF:
            return url
        return format_html('<img src="%s" width="100" height="100" />' % url)

    public_url.short_description = 'Public URL'

    readonly_fields = ['public_url']


@admin.register(Story)
class StoryAdmin(admin.ModelAdmin):
    list_display = ('title', 'user_name_from_other_params', 'author', 'session', 'state', 'district', 'created_at',)
    list_filter = (
        CustomAdvanceDateFilter,
        StoryCompanyFilter, 
        'author', 
        'session', 
        StoryStateFilter,
        StoryDistrictFilter, 
        StoryBlockFilter, 
        UserNameFilter, 
        FlowFilter,
    )
    list_editable = ('state', 'district')
    search_fields = ('title', 'session',)
    readonly_fields = ('created_at',)
    exclude = ('formatted_content', )
    inlines = [StoryTagInline, StoryMediaInline]
    list_per_page = 20
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)

    def user_name_from_other_params(self, obj):
        return obj.other_params.get('user_name') if obj.other_params else ''

    user_name_from_other_params.short_description = 'User Name'

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related('author').defer('formatted_content')
        user_email = request.user.email
        profile = Profile.objects.filter(email=user_email).first()
        if request.user.is_superuser:
            return qs
        elif profile and profile.profile_type == ProfileType.MODERATOR:
            profile_address = ProfileAddress.objects.filter(profile=profile).first()
            print("profile_address: ", profile_address)
            query = Q(author__company=profile.company)
            print("Query: ", query)
            if profile_address and profile_address.district:
                query &= Q(author__profile__profile_address__district=profile_address.district)
            if profile_address and profile_address.state:
                query &= Q(author__profile__profile_address__state=profile_address.state)
            results = qs.filter(query)
            print("Filtered results:", results)
            return results
            # return qs.filter(query)
        else:
            return qs.none()

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        print(f"Story saved: {obj.title}")
        flow = obj.other_params.get('flow') if obj.other_params else None
        story_pdf_exists = StoryMedia.objects.filter(
            story=obj,
            media_type=MediaTypeChoices.PDF
        ).exists()
        if story_pdf_exists:
            # Update existing PDF
            print(f"Updating existing PDF for story: {obj.title}")
            update_story_pdf(
                access_token=None, session=obj.session, flow=flow, is_edit_story=False
            )
        else:
            # Create new PDF
            print(f"Creating new PDF for story: {obj.title}")
            save_shikshalokam_story(
                story=obj, profile=obj.author,
                problem_statement=None, chat_history=None, access_token=None,
                project_id=None, session=obj.session, conversation=None, flow=flow
            )

    actions = [redirect_to_export_view]

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('export_stories/', self.admin_site.admin_view(self.export_stories_view), name='export_stories'),
            path('post_processing/', self.admin_site.admin_view(PostProcessingView.as_view()), name='chatbot_story_post_processing'),
        ]
        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['show_post_processing_button'] = True
        return super().changelist_view(request, extra_context=extra_context)

    def export_stories_view(self, request):
        ids = request.GET.get('ids', '')
        selected_ids = ids.split(',') if ids else []
        stories = Story.objects.filter(id__in=selected_ids)

        if request.method == 'POST':
            export_format = request.POST.get('format')
            dataset = tablib.Dataset()
            fields_to_export = [
                "id", "title", "author", "content", "blurb", "objective", "action_steps", "impact",
                "location", "language", "stage", "created_at", "organisation"
            ]
            # fields_to_export=[]
            headers = get_story_fields(stories, fields_to_export)
            dataset.headers = headers
            for story in stories:
                dataset.append(get_story_data(story, headers))

            if export_format == 'csv':
                return generate_csv_response(dataset)
            elif export_format == 'xls':
                return generate_xls_response(dataset)
            elif export_format == 'docx':
                return generate_docx_response(stories, fields_to_export)
            elif export_format == 'zip-pdf':
                return generate_zip_response(stories)


        return render(request, 'admin/export_story_format.html', {'ids': ids})


@admin.register(StoryTranslation)
class StoryTranslationAdmin(admin.ModelAdmin):
    list_display = ('story', 'language', 'story_session', 'created_at')
    list_filter = (
        CustomAdvanceDateFilter,
        'language', 
        'story', 
        'story__session'
    )
    search_fields = ('story__title', 'story__session', 'title')
    readonly_fields = ('created_at',)
    ordering = ('-created_at', 'story__session', 'language')
    exclude = ('formatted_content', )
    raw_id_fields = ('story',)
    list_per_page = 20
    date_hierarchy = 'created_at'

    def story_session(self, obj):
        """Display session from related story"""
        return obj.story.session if obj.story else '-'

    story_session.short_description = 'Session'
