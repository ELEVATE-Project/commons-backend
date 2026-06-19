from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator
from django.http import JsonResponse
from django.views import View
from chatbot.models import Profile, FileTypeChoices, CompanyBot
import json
import tempfile
import uuid
from chatbot.celery_tasks.knowledge_service.tag_tasks import get_auto_extracted_data
from chatbot.utils.knowledge_service.auto_tag_utils import TagProcessor
from chatbot.utils.knowledge_service.cache_manager import CacheManager


@method_decorator(staff_member_required, name='dispatch')
class BatchMediaExtractView(View):
    """API endpoint for extracting data from uploaded files"""

    def post(self, request):
        try:
            import re
            import time

            files = request.FILES.getlist('files')
            company_bot_id = request.POST.get('company_bot_id')
            session_id = request.POST.get('session_id')

            # Get file indices if provided
            file_indices = request.POST.getlist('file_indices')

            extracted_data = []

            # Generate session ID if not provided
            if not session_id:
                session_id = str(uuid.uuid4())

            company_bot = None
            if company_bot_id:
                try:
                    company_bot = CompanyBot.objects.get(id=company_bot_id)
                except CompanyBot.DoesNotExist:
                    pass

            print(f"Processing {len(files)} files with indices: {file_indices}")

            for i, file in enumerate(files):
                try:
                    # Use provided file index or generate unique one
                    if i < len(file_indices) and file_indices[i]:
                        file_index = int(file_indices[i])
                    else:
                        # Generate unique index if not provided
                        file_index = int(time.time() * 1000000) + i

                    print(f"Processing file {i}: {file.name} with index {file_index}")

                    # Store file for retry purposes with sanitized cache key
                    file_key = CacheManager.cache_file(file, session_id, file_index)

                    data = self.extract_file_data(
                        file=file,
                        company_bot=company_bot,
                        file_index=file_index,  # Use unique index
                        request=request
                    )
                    if data.get('error') or data.get('error_type'):
                        raise Exception(data.get('error', 'AI extraction failed'))

                    data['status'] = 'success'
                    data['error'] = None
                    data['session_id'] = session_id
                    data['file_key'] = file_key

                    print(f"Successfully processed file {file.name}, cache key: {file_key}")

                except Exception as e:
                    print(f"Error processing file {file.name}: {e}")

                    # For failed extractions, still cache the file
                    if i < len(file_indices) and file_indices[i]:
                        file_index = int(file_indices[i])
                    else:
                        file_index = int(time.time() * 1000000) + i

                    file_key = CacheManager.cache_file(file, session_id, file_index)

                    data = {
                        'filename': file.name,
                        'status': 'error',
                        'error': str(e),
                        'file_index': file_index,
                        'session_id': session_id,
                        'file_key': file_key,
                        'name': file.name,
                        'media_type': self.get_media_type(file.name),
                        'description': f'Extracted from {file.name}',
                        'extracted_text': '',
                        'priority': 'P1',
                        'tags': [],
                        'manual_tags': [],
                        'auto_tags': [],
                        'auto_tag_task_id': None,
                        'auto_tags_ready': True,
                        'key_values': [],
                        'subdocument': [],
                        'images': []
                    }

                extracted_data.append(data)

            print(f"Completed processing {len(extracted_data)} files")

            return JsonResponse({
                'success': True,
                'data': extracted_data,
                'session_id': session_id
            })

        except Exception as e:
            print(f"BatchMediaExtractView.post() error: {e}")
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)

    def extract_file_data(self, file, company_bot, file_index, request=None):
        """Extract data from file and start async AI extraction"""
        file_extension = file.name.rsplit('.', 1)[-1].lower() if '.' in file.name else None

        if file_extension and not FileTypeChoices.is_valid_extension(file_extension):
            raise ValueError(f"Unsupported file format: .{file_extension}")

        max_file_size_mb = 50
        if company_bot and hasattr(company_bot, 'other_params') and company_bot.other_params:
            try:
                other_params = json.loads(company_bot.other_params) if isinstance(
                    company_bot.other_params, str
                ) else company_bot.other_params
                max_file_size_mb = other_params.get('max_file_size_mb', 50)
            except:
                pass

        max_file_size_bytes = max_file_size_mb * 1024 * 1024

        if file.size > max_file_size_bytes:
            file_size_mb = file.size / (1024 * 1024)
            raise ValueError(
                f"File size ({file_size_mb:.2f} MB) exceeds the maximum allowed size of {max_file_size_mb} MB. "
                f"Please reduce the file size.")

        # Save file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_extension}") as tmp:
            for chunk in file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        user_profile = None
        company = None
        company_name = ''
        if request and request.user.is_authenticated:
            try:
                user_profile = Profile.objects.get(email=request.user.email)
                company = user_profile.company
                if company:
                    company_name = company.name
            except Profile.DoesNotExist:
                pass

        master_tags = TagProcessor.get_master_tags(
            company=company, other_params=company_bot.other_params if company_bot else None
        )
        print("Sending master tags: ", master_tags)
        base_name = file.name.rsplit('.', 1)[0] if '.' in file.name else file.name

        other_data = {
            "master_tag": master_tags,
            "original_filename": base_name
        }

        # Start async task (non-blocking)
        print(f"Starting async extraction task for {file.name}")
        task = get_auto_extracted_data.delay(
            file_path=tmp_path,
            company_bot_id=company_bot.id if company_bot else None,
            file_extension=file_extension,
            other_data=other_data
        )
        base_name = file.name.rsplit('.', 1)[0] if '.' in file.name else file.name

        return {
            'filename': file.name,
            'file_index': file_index,
            'name': base_name,
            'media_type': self.get_media_type(file.name),
            'description': f'Extracted from {file.name}',
            'extracted_text': '',
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
            'organization': company_name,
            'company_name': company_name
        }

    def get_media_type(self, filename):
        """Map file extension to media type using FileTypeChoices"""
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else None
        return FileTypeChoices.get_mime_from_extension(ext) if ext else FileTypeChoices.TXT.value


@method_decorator(staff_member_required, name='dispatch')
class BatchMediaRetryExtractView(View):
    """API endpoint for retrying extraction of a single file"""

    def post(self, request):
        try:
            data = json.loads(request.body)
            file_data = data.get('file_data')
            company_bot_id = data.get('company_bot_id')
            session_id = data.get('session_id')

            if not file_data:
                return JsonResponse({
                    'success': False,
                    'error': 'No file data provided'
                }, status=400)

            company_bot = None
            if company_bot_id:
                try:
                    company_bot = CompanyBot.objects.get(id=company_bot_id)
                except CompanyBot.DoesNotExist:
                    pass

            # Try to retrieve stored file
            file_key = file_data.get('file_key')
            stored_file = None

            if file_key:
                stored_file = CacheManager.get_cached_item(file_key)

            if not stored_file:
                return JsonResponse({
                    'success': False,
                    'error': 'Original file data not found. Please re-upload the file or try uploading again.'
                }, status=400)

            # Create a file-like object from stored data
            class StoredFile:
                def __init__(self, stored_data):
                    self.name = stored_data['name']
                    self.size = stored_data['size']
                    self._content = stored_data['content']

                def chunks(self):
                    chunk_size = 8192
                    for i in range(0, len(self._content), chunk_size):
                        yield self._content[i:i + chunk_size]

            try:
                stored_file_obj = StoredFile(stored_file)
                extract_view = BatchMediaExtractView()
                extracted_data = extract_view.extract_file_data(
                    file=stored_file_obj,
                    company_bot=company_bot,
                    file_index=file_data.get('file_index', 0),
                    request=request
                )
                extracted_data['status'] = 'success'
                extracted_data['error'] = None
                extracted_data['session_id'] = session_id
                extracted_data['file_key'] = file_key

                return JsonResponse({
                    'success': True,
                    'data': extracted_data
                })
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'error': str(e)
                })

        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data'
            }, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Unexpected error: {str(e)}'
            }, status=400)
