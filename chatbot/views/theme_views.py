from django.db import transaction
from django.db.models import Count
from rest_framework import serializers, status
from rest_framework.generics import CreateAPIView, UpdateAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.permissions import IsAdminUser
from rest_framework.views import APIView

from chatbot.constants.constants import MAX_BIGINT

from chatbot.serializer.theme_serializer import (
    ResourceThemeCreateSerializer, ResourceThemeUpdateSerializer,
)
from chatbot.models.theme_models import ResourceTheme
from chatbot.models.media_models import Media
from chatbot.utils.theme_cache import get_theme_list, invalidate_theme_list_cache


class ResourceThemeCreateView(CreateAPIView):
    """Create a resource theme, defaulting to draft and non-primary."""

    serializer_class = ResourceThemeCreateSerializer
    permission_classes = (IsAdminUser,)
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def perform_create(self, serializer):
        serializer.save()
        transaction.on_commit(invalidate_theme_list_cache)


class ResourceThemeUpdateView(UpdateAPIView):
    """Update a theme selected by exactly one query parameter: id or code."""

    serializer_class = ResourceThemeUpdateSerializer
    permission_classes = (IsAdminUser,)
    parser_classes = (JSONParser, MultiPartParser, FormParser)
    queryset = ResourceTheme.objects.all()

    def perform_update(self, serializer):
        serializer.save()
        transaction.on_commit(invalidate_theme_list_cache)

    def get_object(self):
        params = self.request.query_params
        selectors = [key for key in ('id', 'code') if key in params]
        if len(selectors) != 1:
            raise serializers.ValidationError(
                {'detail': 'Provide exactly one query parameter: id or code.'}
            )
        selector = selectors[0]
        if len(params.getlist(selector)) != 1:
            raise serializers.ValidationError({selector: 'Provide a single value.'})
        if selector == 'id':
            value = serializers.IntegerField(min_value=1, max_value=MAX_BIGINT).run_validation(params[selector])
            lookup = {'pk': value}
        else:
            value = serializers.CharField(max_length=100).run_validation(params[selector])
            lookup = {'code': value}
        theme = get_object_or_404(self.get_queryset(), **lookup)
        self.check_object_permissions(self.request, theme)
        return theme


class ResourceThemeListView(APIView):
    """List published primary resource themes."""

    def get(self, request):
        try:
            payload = get_theme_list(primary_only=True, published_only=True)
            media_counts = dict(
                Media.objects.filter(
                    primary_theme_id__in=[theme['code'] for theme in payload['result']]
                ).order_by().values('primary_theme_id').annotate(
                    media_count=Count('pk')
                ).values_list('primary_theme_id', 'media_count')
            )
            return Response({
                **payload,
                'result': [
                    {**theme, 'media_count': media_counts.get(theme['code'], 0)}
                    for theme in payload['result']
                ],
            })
        except LookupError:
            return Response(
                {'detail': 'Resource themes are not available yet.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
