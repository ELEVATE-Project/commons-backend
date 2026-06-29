import django_filters
from math import ceil
from urllib.parse import urlencode
from rest_framework import generics
from rest_framework.response import Response
from rest_framework import status
from chatbot.filter.drf_filter import ChatSessionProfileFilter
from chatbot.models import ChatSession, BotVernacular, SessionFlowName, ChatType
from chatbot.models.company_models import CompanyChat, CompanyBot, Flow
from chatbot.models.profile_models import Profile
from chatbot.models.repository_models import Repository
from chatbot.serializer.base_serializer import ChatSessionSerializer
from chatbot.serializer.company_serializer import (
    CompanyBotSerializer, BotVernacularSerializer, ImageConfigurationSerializer,
    FlowLanguagesSerializer, FlowConnectionInfoSerializer
)
from chatbot.serializer.profile_serializer import ProfileSerializer, CompanyChatSerializer
from chatbot.serializer.repository_serializer import RepositorySerializer


class CompanyChatListCreateView(generics.ListCreateAPIView):
    queryset = CompanyChat.objects.all().order_by('created_at')
    serializer_class = CompanyChatSerializer
    filter_backends = [django_filters.rest_framework.DjangoFilterBackend]
    filterset_fields = ['message', 'sender', 'receiver', 'session', 'status']


class CompanyChatRetrieveUpdateDestroyView(generics.RetrieveUpdateAPIView):
    queryset = CompanyChat.objects.all()
    serializer_class = CompanyChatSerializer


class CompanyBotListCreateView(generics.ListCreateAPIView):
    queryset = CompanyBot.objects.all()
    serializer_class = CompanyBotSerializer
    filter_backends = [django_filters.rest_framework.DjangoFilterBackend]
    filterset_fields = ['name', 'company__name', 'llm_model', 'company__slug', 'route']


class CompanyBotRetrieveUpdateDestroyView(generics.RetrieveUpdateAPIView):
    queryset = CompanyBot.objects.all()
    serializer_class = CompanyBotSerializer


class BotVernacularListCreateView(generics.ListCreateAPIView):
    queryset = BotVernacular.objects.all()
    serializer_class = BotVernacularSerializer
    filter_backends = [django_filters.rest_framework.DjangoFilterBackend]
    filterset_fields = ['company_bot', 'language', 'company_bot__route']


class BotVernacularRetrieveUpdateDestroyView(generics.RetrieveUpdateAPIView):
    queryset = BotVernacular.objects.all()
    serializer_class = BotVernacularSerializer


class ProfileListCreateView(generics.ListCreateAPIView):
    queryset = Profile.objects.all()
    serializer_class = ProfileSerializer
    filter_backends = [django_filters.rest_framework.DjangoFilterBackend]
    filterset_fields = ['first_name', 'email', 'company__name', 'phone', 'company__slug']


class ProfileRetrieveUpdateDestroyView(generics.RetrieveUpdateAPIView):
    queryset = Profile.objects.all()
    serializer_class = ProfileSerializer


class ChatSessionListCreateView(generics.ListCreateAPIView):
    queryset = ChatSession.objects.all()
    serializer_class = ChatSessionSerializer
    filter_backends = [django_filters.rest_framework.DjangoFilterBackend, ChatSessionProfileFilter]
    filterset_fields = ['session', 'project_id', 'user_id', 'profile', 'session_type']


class ChatSessionRetrieveUpdateDestroyView(generics.RetrieveUpdateAPIView):
    queryset = ChatSession.objects.all()
    serializer_class = ChatSessionSerializer
    filter_backends = [django_filters.rest_framework.DjangoFilterBackend]
    filterset_fields = ['session']


class ChatSessionRetrieveUpdateDestroyViewSession(generics.RetrieveUpdateAPIView):
    queryset = ChatSession.objects.all()
    serializer_class = ChatSessionSerializer
    lookup_field = 'session'


class FlowImageConfigView(generics.GenericAPIView):
    """
    API endpoint to get image configuration for a specific flow route.
    Query param: flow_route (required)
    Returns: ImageConfiguration object or 404
    """
    serializer_class = ImageConfigurationSerializer

    def get(self, request, *args, **kwargs):
        flow_route = request.query_params.get('flow_route')
        
        if not flow_route:
            return Response(
                {'error': 'flow_route query parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            flow = Flow.objects.select_related('image_config_id').get(
                flow_route=flow_route,
                active=True
            )
            
            if not flow.image_config_id:
                return Response(
                    {'error': 'No image configuration found for this flow'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            serializer = self.get_serializer(flow.image_config_id)
            return Response(serializer.data)
            
        except Flow.DoesNotExist:
            return Response(
                {'error': 'Flow not found or inactive'},
                status=status.HTTP_404_NOT_FOUND
            )


class FlowLanguagesView(generics.GenericAPIView):
    """
    API endpoint to get supported languages for a specific flow route.
    Query param: flow_route (required)
    Returns: List of language codes
    """
    serializer_class = FlowLanguagesSerializer
    
    def get(self, request, *args, **kwargs):
        flow_route = request.query_params.get('flow_route')
        
        if not flow_route:
            return Response(
                {'error': 'flow_route query parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            flow = Flow.objects.get(
                flow_route=flow_route,
                active=True
            )
            
            serializer = self.get_serializer(flow)
            return Response(serializer.data)
            
        except Flow.DoesNotExist:
            return Response(
                {'error': 'Flow not found or inactive'},
                status=status.HTTP_404_NOT_FOUND
            )


class FlowConnectionInfoView(generics.GenericAPIView):
    """
    API endpoint to get websocket URL and bot route for a flow.
    Query param: flow_route (required)
    Returns: websocket_url, bot route, isParentFlow flag, children flows, and image configuration
    """
    serializer_class = FlowConnectionInfoSerializer
    
    def get(self, request, *args, **kwargs):
        flow_route = request.query_params.get('flow_route')
        
        if not flow_route:
            return Response(
                {'error': 'flow_route query parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            flow = Flow.objects.select_related('bot', 'image_config').prefetch_related('child_flows').get(
                flow_route=flow_route
            )
            
            # Check if flow is active
            if not flow.active:
                return Response(
                    {'error': 'Flow is inactive'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            serializer = self.get_serializer(flow)
            return Response(serializer.data)
            
        except Flow.DoesNotExist:
            return Response(
                {'error': 'Flow not found'},
                status=status.HTTP_404_NOT_FOUND
            )


class RepositoryListView(generics.ListAPIView):
    serializer_class = RepositorySerializer

    def get_queryset(self):
        org_identifier = self.request.query_params.get('org_id') or self.request.query_params.get('orgId')
        if not org_identifier:
            return Repository.objects.none()
        try:
            org_id = int(org_identifier)
        except (TypeError, ValueError):
            return Repository.objects.none()
        return Repository.objects.filter(org_id=org_id).order_by('created_at', 'id')

    def list(self, request, *args, **kwargs):
        org_identifier = request.query_params.get('org_id') or request.query_params.get('orgId')
        if not org_identifier:
            return Response(
                {'error': 'org_id/orgId query parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            page = int(request.query_params.get('page', 1))
            limit = int(request.query_params.get('limit', 100))
        except (TypeError, ValueError):
            return Response(
                {'error': 'page and limit must be integers'},
                status=status.HTTP_400_BAD_REQUEST
            )

        max_limit = 100

        if page < 1 or limit < 1:
            return Response(
                {'error': 'page and limit must be greater than 0'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if limit > max_limit:
            return Response(
                {'error': f'limit must be less than or equal to {max_limit}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        queryset = self.filter_queryset(self.get_queryset())
        total_count = queryset.count()
        start_index = (page - 1) * limit
        end_index = start_index + limit

        if start_index >= total_count:
            page_results = []
        else:
            page_results = queryset[start_index:end_index]

        serializer = self.get_serializer(page_results, many=True)

        total_pages = ceil(total_count / limit) if total_count else 0
        base_url = request.build_absolute_uri(request.path)
        query_params = request.query_params.copy()

        next_url = None
        if page < total_pages:
            query_params['page'] = str(page + 1)
            query_params['limit'] = str(limit)
            next_url = f"{base_url}?{urlencode(query_params, doseq=True)}"

        previous_url = None
        if page > 1 and total_pages > 0:
            query_params['page'] = str(page - 1)
            query_params['limit'] = str(limit)
            previous_url = f"{base_url}?{urlencode(query_params, doseq=True)}"

        response_message = "No repositories available."
        if total_count != 0:
            response_message = "Repository data fetched successfully."

        return Response({
            "message" : response_message,
            "result" : {
                "data" : serializer.data,
                "count" : total_count
            }
        })
