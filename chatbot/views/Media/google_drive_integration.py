import os
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
import io
import json
import re
import tempfile
import uuid
import time

from django.core.files.base import ContentFile
from django.http import JsonResponse, FileResponse
from django.shortcuts import redirect
from django.views.generic import TemplateView
from django.views import View
from django.conf import settings
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError

from chatbot.models import Company, CompanyBot, FileDisplayMode, FileTypeChoices, KeyValue, Media
from shikshalokam.models.enums import PriorityChoices

# Import the native LLM extraction tools
from chatbot.celery_tasks.knowledge_service.tag_tasks import get_auto_extracted_data
from chatbot.utils.knowledge_service.cache_manager import CacheManager
from chatbot.utils.knowledge_service.auto_tag_utils import TagProcessor

GOOGLE_DRIVE_SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
GOOGLE_EXPORT_MIME_TYPES = {
    "application/vnd.google-apps.document": "application/pdf",
    "application/vnd.google-apps.spreadsheet": "text/csv",
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


def get_default_extraction_bot():
    return CompanyBot.objects.filter(route='/tag_extractor').first() or CompanyBot.objects.first()



class GoogleDriveIntegrationView(TemplateView):
    template_name = 'google_drive_integration.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Pull native collections to match your Batch Upload step1 layout requirements
        context['companies'] = Company.objects.all().order_by('name')
        context['company_bots'] = CompanyBot.objects.all()
        
        # Match the normal media upload flow's extraction bot.
        default_bot = get_default_extraction_bot()
        context['default_bot_id'] = default_bot.id if default_bot else None
        
        # Check if requesting user has profile matching organization parameters
        if hasattr(self.request.user, 'email'):
            from chatbot.models import Profile
            profile = Profile.objects.filter(email=self.request.user.email).first()
            if profile and profile.company:
                context['user_company'] = profile.company

        return context


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



def extract_folder_id(folder_url):
    match = re.search(
        r'/folders/([a-zA-Z0-9_-]+)',
        folder_url
    )
    return match.group(1) if match else None


def get_all_files_in_folder(service, initial_folder_id):
    """
    Recursively fetches all files inside a folder and its subfolders.
    """
    files_found = []
    folders_to_search = [initial_folder_id]
    
    while folders_to_search:
        # Get the next folder in the queue
        current_folder_id = folders_to_search.pop(0)
        page_token = None
        
        while True:
            try:
                results = service.files().list(
                    q=f"'{current_folder_id}' in parents and trashed=false",
                    pageSize=100,
                    fields="nextPageToken, files(id, name, mimeType, size)",
                    pageToken=page_token
                ).execute()
                
                # Separate actual files from sub-folders
                for item in results.get('files', []):
                    if item['mimeType'] == 'application/vnd.google-apps.folder':
                        # Found a nested folder! Add it to the queue to search later
                        folders_to_search.append(item['id'])
                    else:
                        # Found a file! Add it to our final list
                        files_found.append(item)
                        
                page_token = results.get('nextPageToken')
                if not page_token:
                    break
                    
            except HttpError as error:
                # If a nested folder has restricted permissions, skip it and continue
                print(f"Skipping inaccessible nested folder {current_folder_id}: {error}")
                break
                
    return files_found



def download_drive_file(service, file_id):
    # 1. Ask Google for the permissions metadata alongside the file info
    metadata = service.files().get(
        fileId=file_id,
        fields="id, name, mimeType, permissions"
    ).execute()

    # 2. STRICT CHECK: Ensure the file itself is set to "Anyone with the link"
    is_public = any(p.get('type') == 'anyone' for p in metadata.get('permissions', []))
    if not is_public:
        raise ValueError("not_public")

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


class GoogleDriveFileImportView(View):
    def post(self, request):
        service = get_drive_service(request)
        if not service:
            return JsonResponse({'success': False, 'error': 'Google Drive is not connected'}, status=401)

        try:
            data = json.loads(request.body or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON body'}, status=400)

        folder_url = data.get('folder_url')
        company_id = data.get('company_id') or data.get('organization_slug')
        bot_id = data.get('company_bot_id')

        if not folder_url:
            return JsonResponse({'success': False, 'error': 'folder_url is required'}, status=400)

        folder_id = extract_folder_id(folder_url)
        if not folder_id:
            return JsonResponse({'success': False, 'error': 'Invalid folder URL'}, status=400)

        # 1. Resolve organization
        company = Company.objects.filter(slug=company_id).first() if company_id else None
        company_bot = CompanyBot.objects.filter(id=bot_id).first() if bot_id else None
        if company and company_bot and company_bot.company_id != company.id:
            return JsonResponse(
                {'success': False, 'error': 'company_bot_mismatch'},
                status=400
            )
        if company_bot and not company:
            company = company_bot.company
        if not company_bot and company:
            company_bot = CompanyBot.objects.filter(company=company, route='/tag_extractor').first()
        company_bot = company_bot or get_default_extraction_bot()

        if not company_bot:
            return JsonResponse({'success': False, 'error': 'No company bot available'}, status=400)

        # 2. Check strict permissions on root folder
        try:
            folder_meta = service.files().get(fileId=folder_id, fields="permissions").execute()
            is_public = any(p.get('type') == 'anyone' for p in folder_meta.get('permissions', []))
            if not is_public:
                return JsonResponse({'success': False, 'error': 'not_public'}, status=403)
        except HttpError:
            return JsonResponse({'success': False, 'error': 'not_public'}, status=403)

        # 3. Recursively Fetch ALL Files
        all_files = get_all_files_in_folder(service, folder_id)
        if not all_files:
            return JsonResponse({'success': False, 'error': 'empty_folder'}, status=400)

        session_id = str(uuid.uuid4())
        extracted_data = []

        # Dummy file wrapper for CacheManager compatibility
        class DummyFile:
            def __init__(self, name, size, content):
                self.name = name
                self.size = size
                self._content = content
            def chunks(self):
                chunk_size = 8192
                for i in range(0, len(self._content), chunk_size):
                    yield self._content[i:i + chunk_size]
            def read(self):
                return self._content

        # 4. Download, Cache, and Trigger LLM Extraction sequentially
        for i, file_info in enumerate(all_files):
            file_id = file_info['id']
            original_name = file_info['name']
            
            try:
                metadata, content = download_drive_file(service, file_id)
                extension = original_name.rsplit('.', 1)[-1].lower() if '.' in original_name else 'pdf'
                
                if extension not in ['pdf', 'csv', 'txt', 'docx', 'xlsx', 'doc', 'xls']:
                    extension = 'pdf'
                    
                with tempfile.NamedTemporaryFile(delete=False, suffix=f".{extension}") as tmp:
                    tmp.write(content)
                    tmp_path = tmp.name
                
                dummy_file = DummyFile(original_name, len(content), content)
                file_index = int(time.time() * 1000000) + i
                file_key = CacheManager.cache_file(dummy_file, session_id, file_index)
                if not file_key:
                    raise RuntimeError("cache_file_failed")
                master_tags = TagProcessor.get_master_tags(company=company, other_params=company_bot.other_params if company_bot else None)
                other_data = {"master_tag": master_tags, "original_filename": original_name}
                
                # TRIGGER CELERY LLM EXTRACTION TASK
                task = get_auto_extracted_data.delay(
                    file_path=tmp_path,
                    company_bot_id=company_bot.id,
                    file_extension=extension,
                    other_data=other_data
                )
                
                base_name = original_name.rsplit('.', 1)[0] if '.' in original_name else original_name
                actual_media_type = FileTypeChoices.get_mime_from_extension(extension) or FileTypeChoices.TXT.value
                
                extracted_data.append({
                    'filename': original_name,
                    'file_index': file_index,
                    'name': base_name,
                    'media_type': actual_media_type,
                    'description': f'Extracted from {original_name}',
                    'priority': 'P1',
                    'tags': [],
                    'manual_tags': [],
                    'auto_tags': [],
                    'auto_tag_task_id': task.id,
                    'auto_tags_ready': False,
                    'key_values': [],
                    'subdocument': [],
                    'images': [],
                    'failed_links': [],
                    'organization': company.name if company else '',
                    'organization_slug': company.slug if company else '',
                    'file_key': file_key,
                    'status': 'success',
                    'session_id': session_id
                })
            except Exception as e:
                print(f"Skipped file {original_name}: {e}")
                pass
        
        if not extracted_data:
            return JsonResponse({'success': False, 'error': 'All files were private or corrupted.'}, status=400)

        # 5. Return extraction tasks to frontend
        return JsonResponse({
            'success': True, 
            'data': extracted_data, 
            'session_id': session_id, 
            'company_bot_id': company_bot.id
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