from django.db.models import Q

from chatbot.models import Company, Profile


def get_user_profile(user):
    if not user or not getattr(user, "is_authenticated", False):
        return None

    username = getattr(user, "username", None)
    get_username = getattr(user, "get_username", None)
    if callable(get_username):
        username = username or get_username()

    identifiers = {
        value.strip()
        for value in [
            getattr(user, "email", None),
            username,
            str(getattr(user, "pk", "") or ""),
        ]
        if value and str(value).strip()
    }

    if identifiers:
        identity_query = Q()
        for identifier in identifiers:
            identity_query |= Q(email__iexact=identifier)
            identity_query |= Q(userid__iexact=identifier)
            identity_query |= Q(profile_code__iexact=identifier)

        profile = Profile.objects.select_related("company").filter(identity_query).first()
        if profile:
            return profile

    if username and str(username).strip():
        name_matches = Profile.objects.select_related("company").filter(
            first_name__iexact=str(username).strip()
        )
        if name_matches.count() == 1:
            return name_matches.first()

    return None


def get_user_company(user):
    profile = get_user_profile(user)
    if not profile:
        return None

    if profile.company:
        return profile.company

    org_name = (profile.org_associated or "").strip()
    if org_name:
        company = Company.objects.filter(
            Q(name__iexact=org_name) | Q(slug__iexact=org_name)
        ).first()
        if company:
            return company

    return None


def get_company_queryset_for_user(user):
    """
    Return the organization queryset a user should be allowed to choose from.

    Superusers can see all organizations. Non-superusers can only see their own.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return Company.objects.none()

    if getattr(user, "is_superuser", False):
        return Company.objects.all().order_by("name")

    user_company = get_user_company(user)
    if not user_company:
        return Company.objects.none()

    return Company.objects.filter(pk=user_company.pk).order_by("name")
