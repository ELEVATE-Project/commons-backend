import os
import io
import json

from django.core.files.base import ContentFile
from django.http import FileResponse, JsonResponse
from django.shortcuts import redirect
from django.views.generic import TemplateView
from django.views import View
from django.conf import settings
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from chatbot.models import Company, CompanyBot, FileDisplayMode, FileTypeChoices, KeyValue, Media
from shikshalokam.models.enums import PriorityChoices

import re

GOOGLE_DRIVE_SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
GOOGLE_EXPORT_MIME_TYPES = {
    "application/vnd.google-apps.document": "application/pdf",
    "application/vnd.google-apps.spreadsheet": "application/pdf",
    "application/vnd.google-apps.presentation": "application/pdf",
}


def get_client_secret_path():
    paths_to_try = [
        os.path.join(getattr(settings, 'CODE_BASE_DIR', ''), 'client_secret.json'),
        os.path.join(settings.BASE_DIR, 'client_secret.json'),
    ]
    for path in paths_to_try:
        if path and os.path.exists(path):
            return path
    return paths_to_try[0]


def get_redirect_uri(request):
    if request.path.startswith('/admin/'):
        return request.build_absolute_uri('/admin/chatbot/media/google-drive/callback/')
    return request.build_absolute_uri('/google-drive/callback/')


def get_drive_credentials(request):
    credentials_data = request.session.get('google_credentials')
    if not credentials_data:
        return None
    return Credentials(**credentials_data)


def get_drive_service(request):
    credentials = get_drive_credentials(request)
    if not credentials:
        return None
    return build('drive', 'v3', credentials=credentials)


def download_drive_file(service, file_id):
    metadata = service.files().get(
        fileId=file_id,
        fields="id, name, mimeType"
    ).execute()

    #request = service.files().get_media(fileId=file_id)
    mime_type = metadata["mimeType"]

    if mime_type in GOOGLE_EXPORT_MIME_TYPES:
        request = service.files().export_media(
            fileId=file_id,
            mimeType=GOOGLE_EXPORT_MIME_TYPES[mime_type]
        )
    else:
        request = service.files().get_media(
            fileId=file_id
        )

    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        _, done = downloader.next_chunk()
    fh.seek(0)

    return metadata, fh.read()


class GoogleDriveIntegrationView(TemplateView):
    template_name = 'google_drive_integration.html'


class GoogleDriveAuthView(View):
    def get(self, request):
        client_secret_path = get_client_secret_path()
        if not os.path.exists(client_secret_path):
            return JsonResponse({
                'success': False,
                'error': 'client_secret.json not found',
                'message': f'Create {client_secret_path} from client_secret.sample.json'
            }, status=500)

        flow = Flow.from_client_secrets_file(
            client_secret_path,
            scopes=GOOGLE_DRIVE_SCOPES,
            redirect_uri=get_redirect_uri(request)
        )
        auth_url, state = flow.authorization_url(
            prompt='consent',
            access_type='offline',
            include_granted_scopes='true'
        )
        # CRITICAL: Store the state and generated code verifier in the session
        request.session['oauth_state'] = state
        request.session['oauth_code_verifier'] = flow.code_verifier

        return redirect(auth_url)


class GoogleDriveCallbackView(View):
    def get(self, request):
        client_secret_path = get_client_secret_path()
        if not os.path.exists(client_secret_path):
            return JsonResponse({
                'success': False,
                'error': 'client_secret.json not found',
                'message': f'Create {client_secret_path} from client_secret.sample.json'
            }, status=500)

        # FIX: Extract state and code_verifier back out of the user's session
        state = request.session.get('oauth_state')
        code_verifier = request.session.get('oauth_code_verifier')

        flow = Flow.from_client_secrets_file(
            client_secret_path,
            scopes=GOOGLE_DRIVE_SCOPES,
            redirect_uri=get_redirect_uri(request),
            state=state  # Added 'state' parameter to cross-verify structural security integrity
        )
       
        # CRITICAL: Pass the saved code_verifier to complete the handshake
        flow.fetch_token(
            authorization_response=request.build_absolute_uri(),
            code_verifier=code_verifier
        )

        credentials = flow.credentials
        request.session['google_credentials'] = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }

        # Clean up the session variables since authentication is complete
        request.session.pop('oauth_state', None)
        request.session.pop('oauth_code_verifier', None)

        if request.path.startswith('/admin/'):
            return redirect('/admin/chatbot/media/google-drive/?connected=1')
        return redirect('/google-drive/?connected=1')


class GoogleDriveFilesViewOld(View):
    def get(self, request):
        service = get_drive_service(request)
        if not service:
            return JsonResponse({
                'success': False,
                'error': 'Google Drive is not connected'
            }, status=401)

        results = service.files().list(
            q="mimeType='application/pdf' and trashed=false",
            pageSize=50,
            fields="nextPageToken, files(id, name, mimeType, size)"
        ).execute()
        files = results.get('files', [])
        return JsonResponse({'success': True, 'files': files})


def extract_folder_id(folder_url):
    match = re.search(
        r'/folders/([a-zA-Z0-9_-]+)',
        folder_url
    )
    return match.group(1) if match else None

class GoogleDriveFilesView(View):
    def get(self, request):
        service = get_drive_service(request)

        if not service:
            return JsonResponse({
                'success': False,
                'error': 'Google Drive is not connected'
            }, status=401)

        folder_url = request.GET.get('folder_url')

        if not folder_url:
            return JsonResponse({
                'success': False,
                'error': 'folder_url is required'
            }, status=400)

        folder_id = extract_folder_id(folder_url)

        if not folder_id:
            return JsonResponse({
                'success': False,
                'error': 'Invalid Google Drive folder URL'
            }, status=400)

        results = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            pageSize=100,
            fields="files(id,name,mimeType,size)"
        ).execute()

        return JsonResponse({
            'success': True,
            'files': results.get('files', [])
        })
class GoogleDriveFileDownloadView(View):
    def get(self, request, file_id):
        service = get_drive_service(request)
        if not service:
            return JsonResponse({
                'success': False,
                'error': 'Google Drive is not connected'
            }, status=401)

        metadata, content = download_drive_file(service, file_id)
        return FileResponse(
            io.BytesIO(content),
            as_attachment=True,
            filename=metadata.get('name') or f'{file_id}.pdf'
        )


class GoogleDriveFileImportView(View):
    def post(self, request):
        service = get_drive_service(request)
        if not service:
            return JsonResponse({
                'success': False,
                'error': 'Google Drive is not connected'
            }, status=401)

        try:
            data = json.loads(request.body or '{}')
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON body'
            }, status=400)

        file_ids = data.get('file_ids', [])
        if not file_ids:
            return JsonResponse({
                'success': False,
                'error': 'No file_ids provided'
            }, status=400)

        company = None
        company_id = data.get('company_id')
        if company_id:
            company = Company.objects.filter(slug=company_id).first()
            if not company:
                return JsonResponse({
                    'success': False,
                    'error': f'Company with slug "{company_id}" was not found'
                }, status=404)

        company_bot = None
        if company:
            company_bot = CompanyBot.objects.filter(company=company).first()
        company_bot = company_bot or CompanyBot.objects.first()
        if not company_bot:
            return JsonResponse({
                'success': False,
                'error': 'No company bot available'
            }, status=400)

        results = []
        for file_id in file_ids:
            try:
                metadata, content = download_drive_file(service, file_id)
                filename = metadata.get('name') or f'{file_id}.pdf'
                extension = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'pdf'
                media_type = FileTypeChoices.get_mime_from_extension(extension) or FileTypeChoices.PDF

                media = Media(
                    name=filename.rsplit('.', 1)[0],
                    media_type=media_type,
                    priority=data.get('priority', PriorityChoices.P1),
                    description=data.get('summary', ''),
                    company_bot=company_bot,
                    organization=company,
                    display_mode=FileDisplayMode.VISIBLE
                )
                media.file.save(filename, ContentFile(content), save=False)

                company_slug = company.slug if company else (
                    company_bot.company.slug if company_bot.company else None
                )
                vector_task_id = media.save(company_slug=company_slug)

                KeyValue.objects.create(media=media, key='SOURCE_ID', value=file_id)
                KeyValue.objects.create(media=media, key='SOURCE', value='Google Drive')

                results.append({
                    'success': True,
                    'file_id': file_id,
                    'media_id': media.id,
                    'name': media.name,
                    'vector_task_id': vector_task_id
                })
            except Exception as exc:
                results.append({
                    'success': False,
                    'file_id': file_id,
                    'error': str(exc)
                })

        return JsonResponse({
            'success': True,
            'results': results
        })