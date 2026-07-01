import os
insecure_transport = os.getenv('OAUTHLIB_INSECURE_TRANSPORT')
if insecure_transport:
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = insecure_transport
import io
import json
import re
import uuid

from django.core.files.base import ContentFile
from django.http import JsonResponse, FileResponse
from django.shortcuts import redirect
from django.views.generic import TemplateView
from django.views import View
from django.conf import settings
from django.utils import timezone
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError

from chatbot.models import Company, CompanyBot, FileDisplayMode, FileTypeChoices, KeyValue, Media, Profile
from chatbot.models.repository_models import Repository
from chatbot.views.Media.admin_context import add_media_admin_context
from chatbot.views.Media.extract_views import BatchMediaExtractView
from shikshalokam.models.enums import PriorityChoices
import mimetypes
# Import the native LLM extraction tools
from chatbot.celery_tasks.knowledge_service.tag_tasks import get_auto_extracted_data
from chatbot.utils.knowledge_service.cache_manager import CacheManager
from chatbot.utils.knowledge_service.auto_tag_utils import TagProcessor
from chatbot.utils.company_utils import get_company_queryset_for_user, get_user_company
import chatbot.constants.constants as CONSTANTS
import chatbot.constants.endpoints as ENDPOINTS

raw_scopes = os.getenv('GOOGLE_DRIVE_SCOPES', 'https://www.googleapis.com/auth/drive.readonly')
GOOGLE_DRIVE_SCOPES = [scope.strip() for scope in raw_scopes.split(',')]

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
        return request.build_absolute_uri(ENDPOINTS.GOOGLE_DRIVE_CALLBACK_URL)
    return request.build_absolute_uri(ENDPOINTS.NON_ADMIN_GOOGLE_DRIVE_CALLBACK_URL)


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
        add_media_admin_context(context, self.request, 'List Repositories')
        # Pull native collections to match your Batch Upload step1 layout requirements
        context['companies'] = get_company_queryset_for_user(self.request.user)
        context['company_bots'] = CompanyBot.objects.all()

        # Match the normal media upload flow's extraction bot.
        default_bot = get_default_extraction_bot()
        context['default_bot_id'] = default_bot.id if default_bot else None
        if self.request.path.startswith('/admin/'):
            context['drive_upload_url'] = ENDPOINTS.DRIVE_UPLOAD_URL

        selected_company = None
        company_identifier = (
            self.request.GET.get('company_id')
            or self.request.GET.get('organization_slug')
            or self.request.GET.get('orgId')
            or self.request.GET.get('org_id')
        )

        if company_identifier:
            selected_company = Company.objects.filter(slug=company_identifier).first()
            if not selected_company:
                try:
                    selected_company = Company.objects.filter(id=int(company_identifier)).first()
                except (TypeError, ValueError):
                    selected_company = None

        # Fall back to the logged-in user's company when no explicit company was passed in.
        if not selected_company and hasattr(self.request.user, 'email'):
            profile = Profile.objects.filter(email=self.request.user.email).first()
            if profile and profile.company:
                selected_company = profile.company

        if selected_company:
            context['selected_company'] = selected_company
            context['user_company'] = selected_company
            context['repositories_org_id'] = selected_company.id

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
            return redirect(ENDPOINTS.DRIVE_CONNECTED_URL)
        return redirect(ENDPOINTS.NON_ADMIN_DRIVE_UPLOAD_URL)



def extract_folder_id(folder_url):
    match = re.search(
        r'/folders/([a-zA-Z0-9_-]+)',
        folder_url
    )
    return match.group(1) if match else None


def get_request_profile(request, company=None):
    user_email = getattr(request.user, 'email', None)
    if not user_email:
        return None

    resolved_company = company or get_user_company(request.user)
    if not resolved_company:
        return None

    return Profile.objects.select_related('company').filter(
        email__iexact=user_email,
        company=resolved_company,
    ).first()


def upsert_repository_from_drive_import(
    *,
    folder_url,
    folder_meta,
    company,
    repository_id=None,
    status=CONSTANTS.COMPLETED,
    total_resources,
    error_message=None,
    created_by=None,
    updated_by=None,
):
    org_id = company.id if company else None
    if not org_id:
        return None

    repository_name = (
        (folder_meta or {}).get('name')
        or (company.name if company else None)
        or 'Google Drive Repository'
    )
    org_name = (
        (company.name if company else None)
        or 'Unknown Organization'
    )
    now = timezone.now()

    update_fields = {
        'repository_name': repository_name,
        'provider_type': CONSTANTS.GOOGLE_DRIVE,
        'status': status,
        'sync_enabled': True,
        'last_sync_cursor': (folder_meta or {}).get('id'),
        'last_sync_time': now,
        'last_error_message': error_message,
        'total_resources': total_resources,
        'org_name': org_name,
        'updated_by': updated_by or created_by,
    }

    if status == CONSTANTS.COMPLETED:
        update_fields['last_successful_sync'] = now
        update_fields['last_failed_sync'] = None
    elif error_message:
        update_fields['last_failed_sync'] = now

    if repository_id:
        repository = Repository.objects.filter(id=repository_id, org_id=org_id).first()
        if repository:
            for key, value in update_fields.items():
                setattr(repository, key, value)
            repository.root_link = folder_url
            repository.save()
            return repository

    create_defaults = dict(update_fields)
    create_defaults['created_by'] = created_by

    repository, created = Repository.objects.get_or_create(
        org_id=org_id,
        root_link=folder_url,
        defaults=create_defaults,
    )
    if not created:
        for key, value in update_fields.items():
            setattr(repository, key, value)
        repository.save()
    return repository


def resolve_company_from_import(company_identifier):
    if not company_identifier:
        return None

    company = Company.objects.filter(slug=company_identifier).first()
    if company:
        return company

    try:
        return Company.objects.filter(id=int(company_identifier)).first()
    except (TypeError, ValueError):
        return None


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
                    pageSize=1000,
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
        fields="id, name, mimeType, permissions, webViewLink"
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

        company = resolve_company_from_import(company_id)
        company_bot = CompanyBot.objects.filter(id=bot_id).first() if bot_id else None
        if not company_bot and company:
            company_bot = CompanyBot.objects.filter(company=company, route='/tag_extractor').first()
        company_bot = company_bot or get_default_extraction_bot()
        if not company_bot:
            return JsonResponse({'success': False, 'error': 'No company bot available'}, status=400)

        request_profile = get_request_profile(request, company=company)

        try:
            folder_meta = service.files().get(
                fileId=folder_id,
                fields="id, name, permissions"
            ).execute()
        except HttpError as exc:
            return JsonResponse(
                {
                    'success': False,
                    'error': f'Failed to read Google Drive folder: {exc}',
                },
                status=400
            )

        repository = upsert_repository_from_drive_import(
            folder_url=folder_url,
            folder_meta=folder_meta,
            company=company,
            repository_id=None,
            status='IN-PROGRESS',
            total_resources=0,
            created_by=request_profile,
            updated_by=request_profile,
        )

        session_id = str(uuid.uuid4())
        from chatbot.celery_tasks.knowledge_service.google_drive_tasks import process_google_drive_import

        task = process_google_drive_import.delay(
            session_id=session_id,
            credentials_data=request.session.get('google_credentials', {}),
            folder_url=folder_url,
            folder_id=folder_id,
            company_id=company.id if company else None,
            company_bot_id=company_bot.id if company_bot else None,
            profile_id=request_profile.id if request_profile else None,
            repository_id=str(repository.id) if repository else None,
        )

        return JsonResponse({
            'success': True,
            'message': 'Folder uploaded successfully',
            'session_id': session_id,
            'task_id': task.id,
            'company_bot_id': company_bot.id,
            'repository_id': str(repository.id) if repository else None,
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
        
        # Determine original name and mime type
        original_name = metadata.get('name', str(file_id))
        original_mime = metadata.get('mimeType', '')
        
        # Check if we exported it as a different format (e.g., GSheet to CSV)
        actual_mime = GOOGLE_EXPORT_MIME_TYPES.get(original_mime, original_mime)
        
        # If the file lacks an extension (common for Google Docs), generate the correct one
        if '.' not in original_name:
            ext = mimetypes.guess_extension(actual_mime) or '.bin'
            file_name = f"{original_name}{ext}"
        else:
            file_name = original_name

        return FileResponse(
            io.BytesIO(content),
            as_attachment=True,
            filename=file_name
        )
