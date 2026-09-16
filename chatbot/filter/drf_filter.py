from django.db.models import Q
from rest_framework import filters
from chatbot.models import CompanyChat


class ChatSessionProfileFilter(filters.BaseFilterBackend):

    def filter_queryset(self, request, queryset, view):
        profile_id = request.query_params.get('profile')
        if profile_id:
            sessions = CompanyChat.objects.filter(
                Q(sender__id=profile_id) | Q(receiver__id=profile_id)
            ).values_list('session', flat=True).distinct()
            return queryset.filter(session__in=sessions)
        return queryset
