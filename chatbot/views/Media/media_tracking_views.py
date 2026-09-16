from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import F
from chatbot.models.media_models import Media
from shikshalokam.models import Project


class MediaViewTrackAPIView(APIView):
    """
    Track media view count (intent-based)
    """

    authentication_classes = []  # guest allowed
    permission_classes = []

    def post(self, request, media_id):
        Media.objects.filter(id=media_id).update(
            view_count=F("view_count") + 1
        )

        return Response(
            {"status": "view tracked"},
            status=status.HTTP_200_OK
        )


class MediaDownloadTrackAPIView(APIView):
    """
    Track media download count
    """
    def post(self, request, media_id):
        Media.objects.filter(id=media_id).update(
            download_count=F("download_count") + 1
        )

        return Response(
            {"status": "download tracked"},
            status=status.HTTP_200_OK
        )


class SolutionDownloadTrackView(APIView):
    def post(self, request, project_id):
        updated = Project.objects.filter(project_id=project_id).update(
            solution_download_count=F("solution_download_count") + 1
        )

        if not updated:
            return Response(
                {"error": "Project not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        return Response(
            {"status": "solution download tracked"},
            status=status.HTTP_200_OK
        )
