from django.contrib import admin
from django.db.models import Q

from chatbot.models import Company, Profile, ProfileType
from chatbot.models.geo_models import ProfileAddress


class ProfileCompanyChatFilter(admin.SimpleListFilter):
    title = 'Profile'
    parameter_name = 'profile'

    def lookups(self, request, model_admin):
        user_email = request.user.email
        profile = Profile.objects.filter(email=user_email).only('company').first()

        if request.user.is_superuser:
            return Profile.objects.all().values_list('id', 'first_name')
        elif profile and profile.profile_type == ProfileType.MODERATOR:
            company = profile.company
            return Profile.objects.filter(company=company).values_list('id', 'first_name')
        return []

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(Q(sender__id=self.value()) | Q(receiver__id=self.value())).prefetch_related(
                'sender__company', 'receiver__company')
        return queryset


class ProfileEmailFilter(admin.SimpleListFilter):
    title = 'ProfileEmail'
    parameter_name = 'profile_email'

    def lookups(self, request, model_admin):
        user_email = request.user.email
        profile = Profile.objects.filter(email=user_email).only('company').first()

        if request.user.is_superuser:
            return Profile.objects.all().values_list('id', 'email')
        elif profile and profile.profile_type == ProfileType.MODERATOR:
            company = profile.company
            return Profile.objects.filter(company=company).values_list('id', 'email')
        return []

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(Q(sender__id=self.value()) | Q(receiver__id=self.value())).prefetch_related(
                'sender__company', 'receiver__company')
        return queryset


class CompanyChatCompanyFilter(admin.SimpleListFilter):
    title = 'Company'
    parameter_name = 'company'

    def lookups(self, request, model_admin):
        user_email = request.user.email
        profile = Profile.objects.filter(email=user_email).select_related('company').first()

        if request.user.is_superuser:
            return Company.objects.values_list('id', 'name')

        if profile and profile.profile_type == ProfileType.MODERATOR:
            return [(profile.company.id, profile.company.name)]

        return [()]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(Q(sender__company__id=self.value()) | Q(receiver__company__id=self.value()))
        return queryset



class ProfileCityFilter(admin.SimpleListFilter):
    title = 'City'
    parameter_name = 'profile_city'

    def lookups(self, request, model_admin):
        fmch_company = Company.objects.filter(slug='fmch').only('id').first()
        if not fmch_company:
            return []

        cities = ProfileAddress.objects.filter(profile__company=fmch_company).values_list('city', flat=True).distinct()
        return [(city, city) for city in cities if city]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(
                Q(sender__profile_address__city=self.value()) | Q(receiver__profile_address__city=self.value())
            ).select_related('sender__profile_address', 'receiver__profile_address')
        return queryset


class ProfileStateFilter(admin.SimpleListFilter):
    title = 'State'
    parameter_name = 'profile_state'

    def lookups(self, request, model_admin):
        fmch_company = Company.objects.filter(slug='fmch').only('id').first()
        if not fmch_company:
            return []

        states = ProfileAddress.objects.filter(profile__company=fmch_company).values_list('state', flat=True).distinct()
        return [(state, state) for state in states if state]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(
                Q(sender__profile_address__state=self.value()) | Q(receiver__profile_address__state=self.value())
            ).select_related('sender__profile_address', 'receiver__profile_address')
        return queryset


class ProfileCompanyFilter(admin.SimpleListFilter):
    title = 'Company'
    parameter_name = 'company'

    def lookups(self, request, model_admin):
        user_email = request.user.email
        profile = Profile.objects.filter(email=user_email)
        if request.user.is_superuser:
            return [(company.id, company.name) for company in Company.objects.all()]
        elif len(profile) > 0 and profile[0].profile_type == ProfileType.MODERATOR:
            return [(profile[0].company.id, profile[0].company.name)]
        else:
            return [()]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(Q(company__id=self.value()))


class StoryCompanyFilter(admin.SimpleListFilter):
    title = 'Company'
    parameter_name = 'company'

    def lookups(self, request, model_admin):
        user_email = request.user.email
        profile = Profile.objects.filter(email=user_email)
        if request.user.is_superuser:
            return [(company.id, company.name) for company in Company.objects.all()]
        elif len(profile) > 0 and profile[0].profile_type == ProfileType.MODERATOR:
            return [(profile[0].company.id, profile[0].company.name)]
        else:
            return [()]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(Q(author__company__id=self.value()))


class StoryStateFilter(admin.SimpleListFilter):
    title = 'State'
    parameter_name = 'state'

    def lookups(self, request, model_admin):
        user_email = request.user.email
        profile = Profile.objects.filter(email=user_email)
        if request.user.is_superuser:
            states = ProfileAddress.objects.values_list('state', flat=True).distinct()
            state_filters = []
            for state in states:
                if state:
                    # Add as (value, display name)
                    state_filters.append((state, state))
            return state_filters
        elif len(profile) > 0 and profile[0].profile_type == ProfileType.MODERATOR:
            profile_address = ProfileAddress.objects.filter(profile=profile[0]).first()
            if profile_address and profile_address.state:
                return [(profile_address.state, profile_address.state)]
            else:
                return []
        else:
            return []

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(author__profile_address__state=self.value())
        return queryset


class StoryDistrictFilter(admin.SimpleListFilter):
    title = 'District'
    parameter_name = 'district'

    def lookups(self, request, model_admin):
        user_email = request.user.email
        profile = Profile.objects.filter(email=user_email)
        if request.user.is_superuser:
            districts = ProfileAddress.objects.values_list('district', flat=True).distinct()
            district_filters = []
            for district in districts:
                if district:
                    # Add as (value, display name)
                    district_filters.append((district, district))
            return district_filters
        elif len(profile) > 0 and profile[0].profile_type == ProfileType.MODERATOR:
            profile_address = ProfileAddress.objects.filter(profile=profile[0]).first()
            if profile_address and profile_address.district:
                return [(profile_address.district, profile_address.district)]
        else:
            return [()]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(author__profile_address__district=self.value())
        return queryset


class StoryBlockFilter(admin.SimpleListFilter):
    title = 'Block'
    parameter_name = 'block'

    def lookups(self, request, model_admin):
        user_email = request.user.email
        profile = Profile.objects.filter(email=user_email)
        if request.user.is_superuser:
            blocks = ProfileAddress.objects.values_list('block', flat=True).distinct()
            block_filters = []
            for block in blocks:
                if block:
                    # Add as (value, display name)
                    block_filters.append((block, block))
            return block_filters
        elif len(profile) > 0 and profile[0].profile_type == ProfileType.MODERATOR:
            profile_address = ProfileAddress.objects.filter(profile=profile[0]).first()
            if profile_address and profile_address.block:
                return [(profile_address.block, profile_address.block)]
        else:
            return [()]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(author__profile_address__block=self.value())
        return queryset


class ChatSessionFilter(admin.SimpleListFilter):
    title = 'company'
    parameter_name = 'chat_session'

    def lookups(self, request, model_admin):
        user_email = request.user.email
        profile = Profile.objects.filter(email=user_email)
        if request.user.is_superuser:
            return [(company.id, company.name) for company in Company.objects.all()]
        elif len(profile) > 0 and profile[0].profile_type == ProfileType.MODERATOR:
            return [(profile[0].company.id, profile[0].company.name)]
        else:
            return [()]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(profile__company=self.value())
