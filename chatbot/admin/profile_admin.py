from django.utils.html import format_html
from import_export.admin import ExportActionMixin, ImportMixin
from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from chatbot.filter.admin_filter import ProfileCompanyFilter
from chatbot.filter.custom_date_from_filter import CustomAdvanceDateFilter
from chatbot.models import Profile, ProfileType
from chatbot.resources.resource import ProfileResource
from chatbot.models.geo_models import ProfileAddress
from chatbot.models.media_models import ProfileMedia


class ProfileAddressInline(admin.StackedInline):
    model = ProfileAddress
    exclude = ['created_at', 'updated_at']  # Exclude fields from the inline form
    extra = 0


class ProfileMediaInline(admin.TabularInline):
    model = ProfileMedia
    extra = 0
    exclude = ['base64_str', 'file']
    readonly_fields = ['public_url']

    def public_url(self, obj):
        url = obj.get_public_url()
        return format_html('<img src="%s"/>' % url)

    public_url.short_description = 'Public URL'


@admin.register(Profile)
class ProfileAdmin(ImportMixin, ExportActionMixin, SimpleHistoryAdmin):
    resource_class = ProfileResource
    list_display = (
        'email',
        'first_name',
        'created_at',
        'org_associated',
        'company_spoc'
    )
    list_filter = (
        CustomAdvanceDateFilter,
        'email',
        'phone',
        ProfileCompanyFilter,
        'profile_type'
    )
    actions = ['export_selected']
    inlines = [ProfileAddressInline, ProfileMediaInline]
    search_fields = ['first_name', 'email', 'phone']
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        user_email = request.user.email
        profile = Profile.objects.filter(email=user_email)
        if request.user.is_superuser:
            return qs
        elif len(profile) > 0 and profile[0].profile_type == ProfileType.MODERATOR:
            return qs.filter(company=profile[0].company)
        else:
            return qs.none()

    def get_list_filter(self, request):
        return super().get_list_filter(request)

    def get_list_display(self, request):
        return 'email', 'first_name', 'created_at', 'company',

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        user = request.user
        user_email = request.user.email
        profile = Profile.objects.filter(email=user_email)
        if not user.is_superuser and len(profile) > 0 and profile[0].profile_type == ProfileType.MODERATOR:
            company = profile[0].company
            if 'company' in form.base_fields:
                form.base_fields['company'].queryset = \
                    form.base_fields['company'].queryset.filter(id=company.id)
            if 'resume' in form.base_fields:
                form.base_fields['resume'].queryset = \
                    form.base_fields['resume'].queryset.filter(company=company)

            excluded_fields = []
            if company.slug in ['zeiss']:
                excluded_fields = ['resume', 'password', 'profile_code',
                                   'location', 'caste', 'gender', 'product_interested', 'other_params']
            for field_name in excluded_fields:
                if field_name in form.base_fields:
                    form.base_fields.pop(field_name)

        return form

    # Custom method to display 'product_interested' field
    def sector(self, obj):
        product_interested = obj.other_params.get('product_interested', []) if obj.other_params else []
        sectors = [item.get('sector', '') for item in product_interested]
        return ', '.join(sectors)
    sector.short_description = 'Sector'

    def product(self, obj):
        product_interested = obj.other_params.get('product_interested', []) if obj.other_params else []
        products = [item.get('product', '') for item in product_interested]
        return ', '.join(products)
    product.short_description = 'Product'

    # Custom method to display 'other_params->>'model_name' field
    def other_params_model_name(self, obj):
        return obj.other_params.get('model_name', '') if obj.other_params else ''
    other_params_model_name.short_description = 'Model Name'

    # Custom method to display 'other_params->>'inquiry_status' field
    def other_params_inquiry_status(self, obj):
        return obj.other_params.get('inquiry_status', '') if obj.other_params else ''
    other_params_inquiry_status.short_description = 'Inquiry Status'

    # Custom method to display 'other_params->>'discussion_details' field
    def other_params_discussion_details(self, obj):
        return obj.other_params.get('discussion_details', '') if obj.other_params else ''
    other_params_discussion_details.short_description = 'Discussion Details'

    # Custom method to display 'other_params->>'others_budget_planning_etc' field
    def other_params_others_budget_planning(self, obj):
        return obj.other_params.get('others_budget_plannning_etc', '') if obj.other_params else ''
    other_params_others_budget_planning.short_description = 'Other Parameters (Budget Planning etc)'

    def other_params_present_activity(self, obj):
        return obj.other_params.get('present_activity', '') if obj.other_params else ''
    other_params_present_activity.short_description = 'Present Activity'

    def other_params_price_offered(self, obj):
        return obj.other_params.get('price_offered', '') if obj.other_params else ''
    other_params_price_offered.short_description = 'Price Offered'

    def other_params_action_to_be_taken(self, obj):
        return obj.other_params.get('action_to_be_taken', '') if obj.other_params else ''
    other_params_action_to_be_taken.short_description = 'Action to be Taken'

    def other_params_remarks(self, obj):
        return obj.other_params.get('remarks', '') if obj.other_params else ''
    other_params_remarks.short_description = 'Remarks'

    def state(self, obj):
        profile_address = ProfileAddress.objects.filter(profile=obj)
        if len(profile_address) > 0 and profile_address[0].state:
            return profile_address[0].state
        else:
            return ''
    state.short_description = 'State'

    def city(self, obj):
        profile_address = ProfileAddress.objects.filter(profile=obj)
        if len(profile_address) > 0 and profile_address[0].city:
            return profile_address[0].city
        else:
            return ''
    city.short_description = 'City'

    def business_card(self, obj):
        profile_media = ProfileMedia.objects.filter(profile=obj)
        if len(profile_media) > 0:
            url = profile_media[0].get_public_url()
            return format_html('<img src="%s" width="50" height="50" />' % url)
    business_card.short_description = 'Business Card'

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)

        user_email = request.user.email
        profile = Profile.objects.filter(email=user_email).first()
        if not request.user.is_superuser and profile and profile.profile_type == ProfileType.MODERATOR:
            if profile.company:
                queryset = queryset.filter(company=profile.company)
        return queryset, use_distinct
