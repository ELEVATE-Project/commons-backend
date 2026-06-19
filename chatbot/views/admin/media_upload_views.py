# import logging
# import traceback
# from pathlib import Path
#
# import requests
# from django.views.generic import TemplateView
# from django.contrib.admin.views.decorators import staff_member_required
# from django.utils.decorators import method_decorator
# from django.http import JsonResponse
# from django.views import View
# from chatbot.models import Media, Tag, KeyValue, Profile, FileTypeChoices, CompanyBot, TagSourceChoices, TagChoices, \
#     Company, EntityStatus, FileDisplayMode
# from chatbot.models.media_models import PriorityChoices, MediaImage, MediaTypeChoices
# import json
# import tempfile, os
# import uuid
# from django.core.cache import cache
# from chatbot.celery_tasks.knowledge_service.tag_tasks import get_auto_extracted_data
# from chatbot.utils.knowledge_service.base_task_utils import determine_media_type_from_url
# from chatbot.utils.knowledge_service.duplicate_detector import DuplicateDetector
# from django.core.files.base import ContentFile
# import base64
# from django.utils.text import slugify
# from django.conf import settings
#
# BOT_PROFILE_ID = 1
# ENABLE_SIMILARITY_CHECK = getattr(settings, 'BATCH_UPLOAD_ENABLE_SIMILARITY_CHECK', False)
# CACHE_TIMEOUT = getattr(settings, 'BATCH_UPLOAD_CACHE_TIMEOUT', 7200)
# logger = logging.getLogger('django')
#
#
# @method_decorator(staff_member_required, name='dispatch')
# class BatchMediaUploadView(TemplateView):
#     template_name = 'admin/batch_upload.html'
#
#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         context['media_types'] = FileTypeChoices.choices
#         context['priorities'] = PriorityChoices.choices
#
#         extension_mapping = FileTypeChoices.get_extension_mapping()
#         context['file_types'] = [
#             {
#                 'mime_type': choice[0],
#                 'label': choice[1],
#                 'extension': extension_mapping.get(choice[0], '')
#             }
#             for choice in FileTypeChoices.choices
#         ]
#
#         from chatbot.models import CompanyBot
#         context['company_bots'] = CompanyBot.objects.all()
#         default_bot = CompanyBot.objects.filter(route='/tag_extractor')
#         if default_bot:
#             default_bot = default_bot.first()
#             context['default_bot_id'] = default_bot.id
#
#         # Add companies for organization selection
#         context['companies'] = Company.objects.filter(status=EntityStatus.ACTIVE).order_by('name')
#
#         # Add user's company info
#         user_company = None
#         if self.request.user.is_authenticated:
#             try:
#                 user_profile = Profile.objects.get(email=self.request.user.email)
#                 user_company = user_profile.company
#                 context['user_company'] = user_company
#             except Profile.DoesNotExist:
#                 pass
#
#         try:
#             existing_tags_query = Tag.objects.filter(
#                 source_type=TagSourceChoices.MANUAL,
#                 status=TagChoices.APPROVED
#             )
#
#             context['existing_manual_tags'] = list(
#                 existing_tags_query.values_list('name', flat=True).distinct().order_by('name')
#             )
#
#             document_types = []
#             try:
#                 tag_extractor_bot = CompanyBot.objects.filter(route='/tag_extractor').first()
#                 if tag_extractor_bot and tag_extractor_bot.other_params:
#                     try:
#                         other_params = json.loads(tag_extractor_bot.other_params) if isinstance(
#                             tag_extractor_bot.other_params, str
#                         ) else tag_extractor_bot.other_params
#
#                         master_document_types = other_params.get('master_document_types', [])
#                         if isinstance(master_document_types, list):
#                             document_types = master_document_types
#                     except (json.JSONDecodeError, TypeError):
#                         pass
#             except Exception as e:
#                 print(f"Error getting document types: {e}")
#
#             if not document_types:
#                 document_types = []
#
#             context['master_document_types'] = document_types
#
#         except Exception as e:
#             print(f"Error getting context data: {e}")
#             context['existing_manual_tags'] = []
#             context['master_document_types'] = []
#
#         return context
#
#
# class CacheManager:
#     """Centralized cache management for batch upload"""
#
#     @staticmethod
#     def get_cache_key(session_id, item_type, item_id):
#         """Generate consistent cache keys with proper sanitization"""
#         import re
#
#         # Sanitize all components to ensure memcached compatibility
#         sanitized_session_id = re.sub(r'[^a-zA-Z0-9\-_.]', '_', str(session_id))
#         sanitized_item_type = re.sub(r'[^a-zA-Z0-9\-_.]', '_', str(item_type))
#         sanitized_item_id = re.sub(r'[^a-zA-Z0-9\-_.]', '_', str(item_id))
#
#         # Remove multiple consecutive underscores
#         sanitized_session_id = re.sub(r'_+', '_', sanitized_session_id)
#         sanitized_item_type = re.sub(r'_+', '_', sanitized_item_type)
#         sanitized_item_id = re.sub(r'_+', '_', sanitized_item_id)
#
#         # Generate the cache key
#         cache_key = f"batch_upload_{sanitized_session_id}_{sanitized_item_type}_{sanitized_item_id}"
#
#         # Final length check
#         if len(cache_key) > 240:
#             import hashlib
#             key_hash = hashlib.md5(cache_key.encode('utf-8')).hexdigest()
#             cache_key = f"batch_upload_{sanitized_session_id}_{sanitized_item_type}_{key_hash[:16]}"
#
#         # Final sanitization pass
#         cache_key = re.sub(r'[^a-zA-Z0-9\-_.]', '_', cache_key)
#
#         return cache_key
#
#     @staticmethod
#     def cache_file(file, session_id, file_index):
#         """Cache uploaded file content with sanitized cache key"""
#         try:
#             import re
#             import hashlib
#
#             file_content = b''
#             for chunk in file.chunks():
#                 file_content += chunk
#
#             # More aggressive sanitization for memcached compatibility
#             # Remove all non-alphanumeric characters except dots, hyphens, underscores
#             sanitized_name = re.sub(r'[^a-zA-Z0-9\-_.]', '_', file.name)
#             # Remove multiple consecutive underscores
#             sanitized_name = re.sub(r'_+', '_', sanitized_name)
#             # Remove leading/trailing underscores
#             sanitized_name = sanitized_name.strip('_')
#             # Ensure reasonable length (memcached has 250 char limit for keys)
#             if len(sanitized_name) > 30:
#                 # Keep first 30 chars and add hash of full name for uniqueness
#                 name_hash = hashlib.md5(file.name.encode('utf-8')).hexdigest()[:8]
#                 sanitized_name = sanitized_name[:22] + '_' + name_hash
#
#             # Generate cache key with additional validation
#             cache_key_suffix = f"{file_index}_{sanitized_name}"
#             # Ensure the final cache key component doesn't have problematic characters
#             cache_key_suffix = re.sub(r'[^a-zA-Z0-9\-_.]', '_', cache_key_suffix)
#
#             cache_key = CacheManager.get_cache_key(session_id, 'file', cache_key_suffix)
#
#             # Additional validation: ensure cache key is memcached compatible
#             # Total length should be under 250 chars and contain only safe characters
#             if len(cache_key) > 240:  # Leave some buffer
#                 # If still too long, use a hash-based approach
#                 key_hash = hashlib.md5(cache_key.encode('utf-8')).hexdigest()
#                 cache_key = f"batch_upload_{session_id}_file_{file_index}_{key_hash[:16]}"
#
#             # Final validation - ensure only safe characters
#             cache_key = re.sub(r'[^a-zA-Z0-9\-_.]', '_', cache_key)
#
#             cache_data = {
#                 'content': file_content,
#                 'name': file.name,  # Keep original name
#                 'size': file.size,
#                 'type': 'file',
#                 'file_index': file_index
#             }
#
#             cache.set(cache_key, cache_data, timeout=CACHE_TIMEOUT)
#             print(f"Cached file: {cache_key} (original: {file.name})")
#             return cache_key
#         except Exception as e:
#             print(f"Error caching file {file.name}: {e}")
#             import traceback
#             traceback.print_exc()
#             return None
#
#     @staticmethod
#     def cache_subdocument(subdoc_data, session_id, parent_index, subdoc_path):
#         """Cache subdocument data for retry purposes - with all fields"""
#         try:
#             cache_key = CacheManager.get_cache_key(session_id, 'subdoc', f"{parent_index}_{subdoc_path}")
#
#             # Ensure all subdocument fields are included
#             complete_subdoc_data = {
#                 'title': subdoc_data.get('title', ''),
#                 'summary': subdoc_data.get('summary', ''),
#                 'description': subdoc_data.get('description', subdoc_data.get('summary', '')),
#                 'media_type': subdoc_data.get('media_type', FileTypeChoices.TXT.value),
#                 'priority': subdoc_data.get('priority', 'P1'),
#                 'extracted_text': subdoc_data.get('extracted_text', subdoc_data.get('exact_content', '')),
#                 'exact_content': subdoc_data.get('exact_content', ''),
#                 'organization': subdoc_data.get('organization', ''),
#                 'document_type': subdoc_data.get('document_type', ''),
#                 'key_entities': subdoc_data.get('key_entities', []),
#                 'manual_tags': subdoc_data.get('manual_tags', []),
#                 'auto_tags': subdoc_data.get('auto_tags', []),
#                 'tags': subdoc_data.get('tags', []),
#                 'key_values': subdoc_data.get('key_values', []),
#                 'images': subdoc_data.get('images', []),
#                 'subdocument': subdoc_data.get('subdocument', []),
#                 'url': subdoc_data.get('url', [])
#             }
#
#             cache_data = {
#                 'data': complete_subdoc_data,
#                 'parent_index': parent_index,
#                 'path': subdoc_path,
#                 'type': 'subdocument'
#             }
#
#             cache.set(cache_key, cache_data, timeout=CACHE_TIMEOUT)
#             print(f"Cached subdocument: {cache_key} with data: {complete_subdoc_data.get('title', 'No title')}")
#             return cache_key
#         except Exception as e:
#             print(f"Error caching subdocument: {e}")
#             traceback.print_exc()
#             return None
#
#     @staticmethod
#     def get_cached_item(cache_key):
#         """Retrieve item from cache with Redis-specific debugging"""
#         import time
#         from django.core.cache import cache
#
#         max_retries = 2
#         retry_delay = 0.1
#
#         for attempt in range(max_retries + 1):
#             try:
#                 # Add timing to detect slow Redis responses
#                 start_time = time.time()
#                 cached_data = cache.get(cache_key)
#                 response_time = time.time() - start_time
#
#                 if cached_data:
#                     print(f"✓ Cache HIT: {cache_key} (attempt {attempt + 1}, {response_time:.3f}s)")
#                     return cached_data
#                 else:
#                     print(f"✗ Cache MISS: {cache_key} (attempt {attempt + 1}, {response_time:.3f}s)")
#
#                     # For Redis, try to get connection info
#                     try:
#                         from django.core.cache import cache
#                         if hasattr(cache, '_cache') and hasattr(cache._cache, 'get_client'):
#                             redis_client = cache._cache.get_client()
#                             connection_info = redis_client.connection_pool.connection_kwargs
#                             print(f"Redis connection: {connection_info.get('host')}:{connection_info.get('port')}")
#
#                             # Check Redis connection
#                             redis_client.ping()
#                             print("Redis ping successful")
#
#                             # Check if key actually exists
#                             exists = redis_client.exists(cache_key)
#                             print(f"Redis key exists check: {exists}")
#
#                     except Exception as redis_debug_error:
#                         print(f"Redis debug error: {redis_debug_error}")
#
#                     # If not last attempt, wait and retry
#                     if attempt < max_retries:
#                         print(f"Retrying cache get in {retry_delay}s...")
#                         time.sleep(retry_delay)
#                         retry_delay *= 2  # Exponential backoff
#                         continue
#                     else:
#                         return None
#
#             except Exception as e:
#                 print(f"Cache retrieval error for {cache_key} (attempt {attempt + 1}): {e}")
#                 if attempt < max_retries:
#                     time.sleep(retry_delay)
#                     retry_delay *= 2
#                     continue
#                 else:
#                     return None
#
#         return None
#
#     @staticmethod
#     def extend_cache_timeout(cache_keys, additional_timeout=None):
#         """Extend cache timeout for failed items"""
#         timeout = additional_timeout or CACHE_TIMEOUT
#         for cache_key in cache_keys:
#             cached_item = cache.get(cache_key)
#             if cached_item:
#                 cache.set(cache_key, cached_item, timeout=timeout)
#                 print(f"Extended cache timeout for: {cache_key}")
#
#
# @method_decorator(staff_member_required, name='dispatch')
# class GetCachedItemView(View):
#     """API endpoint to retrieve cached items"""
#
#     def post(self, request):
#         try:
#             self._source_doc_cache = {}
#             data = json.loads(request.body)
#             company_bot_id = data.get('company_bot_id')
#             media_items = data.get('items', [])
#             session_id = data.get('session_id')
#
#             results = []
#             stats = {
#                 'total': len(media_items),
#                 'successful': 0,
#                 'failed': 0,
#                 'partial_success': 0,
#                 'timeouts': 0,
#                 'similarity_failures': 0
#             }
#
#             # Get current user's profile
#             try:
#                 user_profile = Profile.objects.get(email=request.user.email)
#             except Profile.DoesNotExist:
#                 user_profile = None
#
#             print(f"Starting batch save for {len(media_items)} files")
#
#             # Process each file with fault tolerance
#             for i, item_data in enumerate(media_items):
#                 filename = item_data.get('filename', f'File_{i}')
#                 print(f"Processing file {i + 1}/{len(media_items)}: {filename}")
#
#                 try:
#                     bypass_similarity = item_data.get('bypass_similarity', False)
#
#                     # CRITICAL FIX: Use the file_index from item_data, not the loop index
#                     # The file_index in item_data corresponds to the actual index used during caching
#                     actual_file_index = item_data.get('file_index', i)
#                     print(f"Using file_index {actual_file_index} for {filename} (loop index: {i})")
#
#                     # Ensure the item_data has the correct file_index for cache lookup
#                     item_data['file_index'] = actual_file_index
#
#                     result = self.save_single_item_with_vector_db_wait_safe(
#                         item_data=item_data,
#                         company_bot_id=company_bot_id,
#                         user_profile=user_profile,
#                         session_id=session_id,
#                         bypass_similarity=bypass_similarity
#                     )
#
#                     # Track statistics
#                     if result['success']:
#                         stats['successful'] += 1
#                     else:
#                         stats['failed'] += 1
#                         if result.get('partial_success'):
#                             stats['partial_success'] += 1
#                         if result.get('error_type') in ['VECTOR_DB_TIMEOUT', 'WAIT_ERROR']:
#                             stats['timeouts'] += 1
#                         if result.get('error_type') == 'SIMILARITY_CHECK_FAILED':
#                             stats['similarity_failures'] += 1
#
#                     results.append(result)
#                     print(
#                         f"File {i + 1} result: {'✓' if result['success'] else '✗'} - {result.get('message', 'No message')}")
#
#                 except Exception as item_error:
#                     print(f"Critical error processing {filename}: {item_error}")
#                     stats['failed'] += 1
#
#                     # Use the actual file_index for error reporting too
#                     actual_file_index = item_data.get('file_index', i)
#
#                     results.append({
#                         'success': False,
#                         'filename': filename,
#                         'message': f'Critical processing error: {str(item_error)}',
#                         'error_type': 'CRITICAL_ERROR',
#                         'file_index': actual_file_index,
#                         'file_key': item_data.get('file_key'),
#                         'session_id': session_id,
#                         'vector_db_saved': False
#                     })
#
#             # Preserve cache for failed files
#             failed_cache_keys = []
#             for r in results:
#                 if not r['success'] and r.get('file_key'):
#                     failed_cache_keys.append(r['file_key'])
#                 # Also preserve cache for failed subdocuments
#                 if r.get('subdocument_results'):
#                     for subdoc_result in r['subdocument_results']:
#                         if not subdoc_result.get('success') and subdoc_result.get('cache_key'):
#                             failed_cache_keys.append(subdoc_result['cache_key'])
#
#             if failed_cache_keys:
#                 CacheManager.extend_cache_timeout(failed_cache_keys)
#
#             # Generate summary message
#             summary_message = self.generate_batch_summary(stats)
#             print(f"Batch complete: {summary_message}")
#
#             return JsonResponse({
#                 'success': True,
#                 'results': results,
#                 'stats': stats,
#                 'summary_message': summary_message,
#                 'session_id': session_id
#             })
#
#         except json.JSONDecodeError:
#             return JsonResponse({
#                 'success': False,
#                 'error': 'Invalid JSON data'
#             }, status=400)
#         except Exception as batch_error:
#             print(f"Batch processing error: {batch_error}")
#             traceback.print_exc()
#             return JsonResponse({
#                 'success': False,
#                 'error': f'Batch processing failed: {str(batch_error)}'
#             }, status=500)
#
#
# @method_decorator(staff_member_required, name='dispatch')
# class BatchMediaExtractView(View):
#     """API endpoint for extracting data from uploaded files"""
#
#     def post(self, request):
#         try:
#             import re
#             import time
#
#             files = request.FILES.getlist('files')
#             company_bot_id = request.POST.get('company_bot_id')
#             session_id = request.POST.get('session_id')
#
#             # Get file indices if provided
#             file_indices = request.POST.getlist('file_indices')
#
#             extracted_data = []
#
#             # Generate session ID if not provided
#             if not session_id:
#                 session_id = str(uuid.uuid4())
#
#             company_bot = None
#             if company_bot_id:
#                 try:
#                     company_bot = CompanyBot.objects.get(id=company_bot_id)
#                 except CompanyBot.DoesNotExist:
#                     pass
#
#             print(f"Processing {len(files)} files with indices: {file_indices}")
#
#             for i, file in enumerate(files):
#                 try:
#                     # Use provided file index or generate unique one
#                     if i < len(file_indices) and file_indices[i]:
#                         file_index = int(file_indices[i])
#                     else:
#                         # Generate unique index if not provided
#                         file_index = int(time.time() * 1000000) + i
#
#                     print(f"Processing file {i}: {file.name} with index {file_index}")
#
#                     # Store file for retry purposes with sanitized cache key
#                     file_key = CacheManager.cache_file(file, session_id, file_index)
#
#                     data = self.extract_file_data(
#                         file=file,
#                         company_bot=company_bot,
#                         file_index=file_index,  # Use unique index
#                         request=request
#                     )
#                     if data.get('error') or data.get('error_type'):
#                         raise Exception(data.get('error', 'AI extraction failed'))
#
#                     data['status'] = 'success'
#                     data['error'] = None
#                     data['session_id'] = session_id
#                     data['file_key'] = file_key
#
#                     print(f"Successfully processed file {file.name}, cache key: {file_key}")
#
#                 except Exception as e:
#                     print(f"Error processing file {file.name}: {e}")
#
#                     # For failed extractions, still cache the file
#                     if i < len(file_indices) and file_indices[i]:
#                         file_index = int(file_indices[i])
#                     else:
#                         file_index = int(time.time() * 1000000) + i
#
#                     file_key = CacheManager.cache_file(file, session_id, file_index)
#
#                     data = {
#                         'filename': file.name,
#                         'status': 'error',
#                         'error': str(e),
#                         'file_index': file_index,
#                         'session_id': session_id,
#                         'file_key': file_key,
#                         'name': file.name,
#                         'media_type': self.get_media_type(file.name),
#                         'description': f'Extracted from {file.name}',
#                         'extracted_text': '',
#                         'priority': 'P1',
#                         'tags': [],
#                         'manual_tags': [],
#                         'auto_tags': [],
#                         'auto_tag_task_id': None,
#                         'auto_tags_ready': True,
#                         'key_values': [],
#                         'subdocument': [],
#                         'images': []
#                     }
#
#                 extracted_data.append(data)
#
#             print(f"Completed processing {len(extracted_data)} files")
#
#             return JsonResponse({
#                 'success': True,
#                 'data': extracted_data,
#                 'session_id': session_id
#             })
#
#         except Exception as e:
#             print(f"BatchMediaExtractView.post() error: {e}")
#             import traceback
#             traceback.print_exc()
#             return JsonResponse({
#                 'success': False,
#                 'error': str(e)
#             }, status=400)
#
#     def extract_file_data(self, file, company_bot, file_index, request=None):
#         """Extract data from file and start async AI extraction"""
#         file_extension = file.name.rsplit('.', 1)[-1].lower() if '.' in file.name else None
#
#         if file_extension and not FileTypeChoices.is_valid_extension(file_extension):
#             raise ValueError(f"Unsupported file format: .{file_extension}")
#
#         max_file_size_mb = 50
#         if company_bot and hasattr(company_bot, 'other_params') and company_bot.other_params:
#             try:
#                 other_params = json.loads(company_bot.other_params) if isinstance(
#                     company_bot.other_params, str
#                 ) else company_bot.other_params
#                 max_file_size_mb = other_params.get('max_file_size_mb', 50)
#             except:
#                 pass
#
#         max_file_size_bytes = max_file_size_mb * 1024 * 1024
#
#         if file.size > max_file_size_bytes:
#             file_size_mb = file.size / (1024 * 1024)
#             raise ValueError(
#                 f"File size ({file_size_mb:.2f} MB) exceeds the maximum allowed size of {max_file_size_mb} MB. "
#                 f"Please reduce the file size.")
#
#         # Save file temporarily
#         with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_extension}") as tmp:
#             for chunk in file.chunks():
#                 tmp.write(chunk)
#             tmp_path = tmp.name
#
#         user_profile = None
#         company = None
#         company_name = ''
#         if request and request.user.is_authenticated:
#             try:
#                 user_profile = Profile.objects.get(email=request.user.email)
#                 company = user_profile.company
#                 if company:
#                     company_name = company.name
#             except Profile.DoesNotExist:
#                 pass
#
#         master_tags = get_master_tags(
#             company=company, other_params=company_bot.other_params if company_bot else None
#         )
#         print("Sending master tags: ", master_tags)
#         base_name = file.name.rsplit('.', 1)[0] if '.' in file.name else file.name
#
#         other_data = {
#             "master_tag": master_tags,
#             "original_filename": base_name
#         }
#
#         # Start async task (non-blocking)
#         print(f"Starting async extraction task for {file.name}")
#         task = get_auto_extracted_data.delay(
#             file_path=tmp_path,
#             company_bot_id=company_bot.id if company_bot else None,
#             file_extension=file_extension,
#             other_data=other_data
#         )
#         base_name = file.name.rsplit('.', 1)[0] if '.' in file.name else file.name
#
#         return {
#             'filename': file.name,
#             'file_index': file_index,
#             'name': base_name,
#             'media_type': self.get_media_type(file.name),
#             'description': f'Extracted from {file.name}',
#             'extracted_text': 'AI extraction in progress...',
#             'priority': 'P1',
#             'tags': [],
#             'manual_tags': [],
#             'auto_tags': [],
#             'auto_tag_task_id': task.id,
#             'auto_tags_ready': False,
#             'key_values': [],
#             'subdocument': [],
#             'images': [],
#             'failed_links': [],
#             'organization': company_name,
#             'company_name': company_name
#         }
#
#     def get_media_type(self, filename):
#         """Map file extension to media type using FileTypeChoices"""
#         ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else None
#         return FileTypeChoices.get_mime_from_extension(ext) if ext else FileTypeChoices.TXT.value
#
#
# @method_decorator(staff_member_required, name='dispatch')
# class BatchMediaRetryExtractView(View):
#     """API endpoint for retrying extraction of a single file"""
#
#     def post(self, request):
#         try:
#             data = json.loads(request.body)
#             file_data = data.get('file_data')
#             company_bot_id = data.get('company_bot_id')
#             session_id = data.get('session_id')
#
#             if not file_data:
#                 return JsonResponse({
#                     'success': False,
#                     'error': 'No file data provided'
#                 }, status=400)
#
#             company_bot = None
#             if company_bot_id:
#                 try:
#                     company_bot = CompanyBot.objects.get(id=company_bot_id)
#                 except CompanyBot.DoesNotExist:
#                     pass
#
#             # Try to retrieve stored file
#             file_key = file_data.get('file_key')
#             stored_file = None
#
#             if file_key:
#                 stored_file = CacheManager.get_cached_item(file_key)
#
#             if not stored_file:
#                 return JsonResponse({
#                     'success': False,
#                     'error': 'Original file data not found. Please re-upload the file or try uploading again.'
#                 }, status=400)
#
#             # Create a file-like object from stored data
#             class StoredFile:
#                 def __init__(self, stored_data):
#                     self.name = stored_data['name']
#                     self.size = stored_data['size']
#                     self._content = stored_data['content']
#
#                 def chunks(self):
#                     chunk_size = 8192
#                     for i in range(0, len(self._content), chunk_size):
#                         yield self._content[i:i + chunk_size]
#
#             try:
#                 stored_file_obj = StoredFile(stored_file)
#                 extract_view = BatchMediaExtractView()
#                 extracted_data = extract_view.extract_file_data(
#                     file=stored_file_obj,
#                     company_bot=company_bot,
#                     file_index=file_data.get('file_index', 0),
#                     request=request
#                 )
#                 extracted_data['status'] = 'success'
#                 extracted_data['error'] = None
#                 extracted_data['session_id'] = session_id
#                 extracted_data['file_key'] = file_key
#
#                 return JsonResponse({
#                     'success': True,
#                     'data': extracted_data
#                 })
#             except Exception as e:
#                 return JsonResponse({
#                     'success': False,
#                     'error': str(e)
#                 })
#
#         except json.JSONDecodeError:
#             return JsonResponse({
#                 'success': False,
#                 'error': 'Invalid JSON data'
#             }, status=400)
#         except Exception as e:
#             return JsonResponse({
#                 'success': False,
#                 'error': f'Unexpected error: {str(e)}'
#             }, status=400)
#
#
# # Shared helper functions
# def get_media_type_from_ai_data(document_type):
#     """Map AI-detected document type to our media type choices"""
#     if isinstance(document_type, dict):
#         doc_type_text = document_type.get('type', '')
#     else:
#         doc_type_text = document_type or ''
#
#     if not doc_type_text:
#         return FileTypeChoices.TXT.value
#
#     if doc_type_text and doc_type_text != '':
#         doc_type_text = doc_type_text.lower()
#     type_mapping = {
#         'report': FileTypeChoices.PDF,
#         'spreadsheet': FileTypeChoices.XLSX,
#         'document': FileTypeChoices.DOCX,
#         'text': FileTypeChoices.TXT,
#         'csv': FileTypeChoices.CSV,
#         'excel': FileTypeChoices.XLSX,
#         'word': FileTypeChoices.DOCX,
#         'pdf': FileTypeChoices.PDF
#     }
#
#     for key, value in type_mapping.items():
#         if key in doc_type_text:
#             return value.value
#     return FileTypeChoices.TXT.value
#
#
# def process_tags(tags_data):
#     """Process tags into consistent format"""
#     processed_tags = []
#     for tag in tags_data:
#         if isinstance(tag, dict):
#             processed_tags.append(tag)
#         else:
#             processed_tags.append({'text': tag, 'source': 'extracted'})
#     return processed_tags
#
#
# def get_master_tags(company=None, other_params=None, include_description=False):
#     try:
#         if other_params:
#             try:
#                 if isinstance(other_params, str):
#                     params = json.loads(other_params)
#                 else:
#                     params = other_params
#
#                 include_description = params.get('include_description', include_description)
#             except (json.JSONDecodeError, TypeError):
#                 pass
#
#         query = Tag.objects.filter(
#             source_type__in=[TagSourceChoices.MANUAL, TagSourceChoices.AI_EXTRACTED],
#             status=TagChoices.APPROVED
#         )
#
#         # if company:
#         #     query = query.filter(company=company)
#
#         if include_description:
#             return [
#                 {
#                     'name': tag['name'],
#                     'description': tag['description'] or ''
#                 }
#                 for tag in query.values('name', 'description').distinct()
#             ]
#         else:
#             return list(query.values_list('name', flat=True).distinct())
#
#     except Exception as e:
#         print(f"Error getting master tags: {e}")
#         return []
#
#
# def extract_tag_texts(tags_data):
#     """Extract just the text from tags for subdocuments"""
#     texts = []
#     for tag in tags_data:
#         if isinstance(tag, dict) and 'text' in tag:
#             texts.append(tag['text'])
#         elif isinstance(tag, str):
#             texts.append(tag)
#     return texts
#
#
# def build_key_values(data_dict):
#     """Build key-value pairs from document data with metadata tracking"""
#     key_values = []
#     array_fields_metadata = []  # Track which fields were originally arrays
#
#     if data_dict.get('title'):
#         key_values.append({'key': 'TITLE', 'value': str(data_dict['title']), 'source': 'ai'})
#
#     organization_value = data_dict.get('organization', '')
#     key_values.append({'key': 'ORGANIZATION', 'value': str(organization_value), 'source': 'ai'})
#
#     # ADD GEOGRAPHY HANDLING
#     geography_value = data_dict.get('geography', '')
#     if geography_value:
#         key_values.append({'key': 'GEOGRAPHY', 'value': str(geography_value), 'source': 'ai'})
#
#     document_type = data_dict.get('document_type')
#     if document_type:
#         if isinstance(document_type, dict):
#             doc_type_value = document_type.get('type', '')
#             if doc_type_value:
#                 doc_type_value = doc_type_value.title()
#                 key_values.append({'key': 'DOCUMENT TYPE', 'value': str(doc_type_value), 'source': 'ai'})
#         else:
#             doc_type_value = document_type.title() if document_type else ''
#             key_values.append({'key': 'DOCUMENT TYPE', 'value': str(doc_type_value), 'source': 'ai'})
#
#     if data_dict.get('key_entities') and len(data_dict['key_entities']) > 0:
#         key_values.append({'key': 'KEY ENTITIES', 'value': ', '.join(map(str, data_dict['key_entities'])), 'source': 'ai'})
#
#     # ENHANCED: Handle structured content with proper array formatting
#     if data_dict.get('structured_content') and isinstance(data_dict['structured_content'], dict):
#         for heading, content in data_dict['structured_content'].items():
#             if heading.upper() in [
#                 'BASIC INFORMATION', 'GENERAL INFORMATION', 'TAGS', 'KEYWORDS',
#                 'CATEGORIES', 'CLASSIFICATION', 'TAGS FOR CLASSIFICATION'
#             ]:
#                 continue
#
#             key_name = heading.upper()
#
#             # Format arrays as multi-line strings with bullet points
#             if isinstance(content, list):
#                 # Track that this field was originally an array
#                 array_fields_metadata.append(key_name)
#
#                 # Ensure all list items are strings
#                 string_items = [str(item) for item in content if item is not None]
#                 formatted_content = '\n'.join([f"• {item}" for item in string_items])
#                 key_values.append({
#                     'key': key_name,
#                     'value': formatted_content,
#                     'original_type': 'array',
#                     'source': 'ai'  # Mark as AI-extracted
#                 })
#             else:
#                 # Handle text that might already be formatted
#                 content_str = str(content) if content is not None else ''
#                 key_values.append({
#                     'key': key_name,
#                     'value': content_str,
#                     'original_type': 'string',
#                     'source': 'ai'  # Mark as AI-extracted
#                 })
#
#     return key_values, array_fields_metadata
#
#
# def process_formatted_content_backend(content):
#     """Process content to maintain bullet point formatting"""
#     if not content or not isinstance(content, str):
#         return content
#
#     # Check if content has bullet points
#     if '•' in content or content.count('\n') > 0:
#         lines = content.split('\n')
#         processed_lines = []
#
#         for line in lines:
#             line = line.strip()
#             if line:
#                 # Ensure bullet point formatting
#                 if not line.startswith('•') and not line.startswith('-') and not line.startswith('*'):
#                     if len(lines) > 1:  # Multi-line content should have bullets
#                         line = f"• {line}"
#                 elif line.startswith('-') or line.startswith('*'):
#                     # Convert other bullet styles to •
#                     line = f"• {line[1:].strip()}"
#                 processed_lines.append(line)
#
#         return '\n'.join(processed_lines)
#
#     return content
#
#
# @method_decorator(staff_member_required, name='dispatch')
# class BatchMediaTaskStatusView(View):
#     """API endpoint for checking Celery task status and updating data when complete"""
#
#     def post(self, request):
#         try:
#             from celery.result import AsyncResult
#
#             # Add logging for debugging
#             print(f"BatchMediaTaskStatusView - Request received")
#             print(f"Request body: {request.body[:500]}")  # First 500 chars
#
#             try:
#                 data = json.loads(request.body)
#             except json.JSONDecodeError as e:
#                 print(f"JSON decode error: {e}")
#                 return JsonResponse({
#                     'success': False,
#                     'error': f'Invalid JSON: {str(e)}'
#                 }, status=400)
#
#             task_ids = data.get('task_ids', [])
#             print(f"Checking status for task IDs: {task_ids}")
#
#             results = {}
#             for task_id in task_ids:
#                 try:
#                     task = AsyncResult(task_id)
#                     print(f"Task {task_id} - Status: {task.status}, Ready: {task.ready()}")
#
#                     if task.ready():
#                         if task.successful():
#                             try:
#                                 ai_data = task.result
#                                 print(f"Task {task_id} successful, processing result")
#                                 print(f"Result type: {type(ai_data)}")
#
#                                 # Check if result is None
#                                 if ai_data is None:
#                                     print(f"Warning: Task {task_id} returned None")
#                                     results[task_id] = {
#                                         'status': 'ERROR',  # CHANGED FROM SUCCESS TO ERROR
#                                         'error': 'AI processing returned no data'
#                                     }
#                                 else:
#                                     processed_data = self.process_ai_extracted_data(ai_data)
#                                     results[task_id] = {
#                                         'status': 'SUCCESS',
#                                         'result': processed_data
#                                     }
#                             except Exception as process_error:
#                                 print(f"Error processing task result for {task_id}: {process_error}")
#                                 import traceback
#                                 traceback.print_exc()
#                                 results[task_id] = {
#                                     'status': 'ERROR',  # ENSURE THIS IS ERROR NOT FAILURE
#                                     'error': str(process_error)
#                                 }
#                         else:
#                             error_info = str(task.info) if task.info else 'Unknown error'
#                             print(f"Task {task_id} failed: {error_info}")
#                             results[task_id] = {
#                                 'status': 'FAILURE',
#                                 'error': error_info
#                             }
#                     else:
#                         results[task_id] = {
#                             'status': 'PENDING'
#                         }
#                 except Exception as task_error:
#                     print(f"Error checking task {task_id}: {task_error}")
#                     import traceback
#                     traceback.print_exc()
#                     results[task_id] = {
#                         'status': 'ERROR',
#                         'error': str(task_error)
#                     }
#
#             print(f"Returning results for {len(results)} tasks")
#             return JsonResponse({
#                 'success': True,
#                 'results': results
#             })
#
#         except Exception as e:
#             print(f"Unexpected error in BatchMediaTaskStatusView: {e}")
#             import traceback
#             traceback.print_exc()
#             return JsonResponse({
#                 'success': False,
#                 'error': str(e)
#             }, status=500)
#
#
#     def get_main_doc_media_type(self, ai_data):
#         """Get the correct document type for main document based on linked file, skipping failed URLs.
#         If only one failed URL exists and it's the same as the only URL, still consider it.
#         """
#         media_type = None
#         file_urls = ai_data.get('url', [])
#         failed_links = ai_data.get('failed_links', [])
#
#         # Collect failed URLs from failed_links
#         failed_urls = set()
#         if failed_links and isinstance(failed_links, list):
#             for item in failed_links:
#                 file_url = item.get('file_url')
#                 if file_url:
#                     failed_urls.add(file_url)
#
#         # Handle edge case: if only one URL and it’s the same as the single failed URL → allow it
#         if (
#                 len(file_urls) == 1
#                 and len(failed_urls) == 1
#                 and next(iter(failed_urls)) == file_urls[0]
#         ):
#             valid_urls = file_urls
#         else:
#             # Otherwise, filter out failed URLs
#             valid_urls = [url for url in file_urls if url not in failed_urls]
#
#         # Proceed only if we have at least one valid URL
#         if valid_urls:
#             source_doc_url = valid_urls[0]
#             media_type, filename, response = determine_media_type_from_url(source_doc_url, parent_media=None)
#
#         return media_type
#
#
#     def validate_tags_against_database(self, tags, company=None):
#         """
#         Filter tags to only include those that exist in the database.
#         """
#         if not tags:
#             return []
#
#         # Extract tag texts
#         tag_texts = []
#         for tag in tags:
#             if isinstance(tag, dict) and 'text' in tag:
#                 tag_texts.append(tag['text'])
#             elif isinstance(tag, str):
#                 tag_texts.append(tag)
#
#         # Query database for existing tags
#         query = Tag.objects.filter(
#             name__in=tag_texts,
#             source_type__in=[TagSourceChoices.MANUAL, TagSourceChoices.AI_EXTRACTED],
#             status=TagChoices.APPROVED
#         )
#
#         # if company:
#         #     query = query.filter(company=company)
#
#         # Get set of valid tag names
#         valid_tag_names = set(query.values_list('name', flat=True))
#
#         # Filter original tags list
#         validated_tags = []
#         for tag in tags:
#             tag_text = tag.get('text') if isinstance(tag, dict) else tag
#             if tag_text in valid_tag_names:
#                 validated_tags.append(tag)
#
#         return validated_tags
#
#     def process_ai_extracted_data(self, ai_data, original_filename=None):
#         """Process AI extracted data into format expected by frontend"""
#         if not ai_data:
#             return {
#                 'auto_tags': [],
#                 'enhanced_data': None
#             }
#
#         # *** SIMPLIFIED: Check if AI data is not a dictionary ***
#         if not isinstance(ai_data, dict):
#             error_msg = "AI processing failed - unable to extract structured data from document"
#             raise ValueError(error_msg)
#
#         # Check for explicit error from AI processing
#         if ai_data.get('error') or ai_data.get('error_type'):
#             error_msg = ai_data.get('error', 'AI processing failed with unknown error')
#             print(f"AI extraction failed: {error_msg}")
#             raise ValueError(f"{error_msg}")
#
#         def repair_structured_content(structured_content):
#             """Repair and validate structured content JSON"""
#             if not structured_content:
#                 return {}
#
#             # If it's already a dict, return as-is
#             if isinstance(structured_content, dict):
#                 return structured_content
#
#             # If it's a string, try to parse and repair
#             if isinstance(structured_content, str):
#                 import json
#                 try:
#                     # Try direct JSON parsing first
#                     return json.loads(structured_content)
#                 except json.JSONDecodeError:
#                     try:
#                         # Use JSON repair if available
#                         import json_repair
#                         return json_repair.repair_json(structured_content)
#                     except (ImportError, Exception) as e:
#                         print(f"JSON repair failed for structured_content: {e}")
#                         # Fallback: try to create a basic structure
#                         try:
#                             # Simple repair attempts
#                             repaired = structured_content.strip()
#                             if not repaired.startswith('{'):
#                                 repaired = '{' + repaired
#                             if not repaired.endswith('}'):
#                                 repaired = repaired + '}'
#                             return json.loads(repaired)
#                         except:
#                             print(f"All JSON repair attempts failed, returning empty dict")
#                             return {}
#
#             # Fallback for other types
#             return {}
#
#         # Get user's company
#         company = None
#         company_name = None
#         if hasattr(self, 'request') and self.request.user.is_authenticated:
#             try:
#                 user_profile = Profile.objects.get(email=self.request.user.email)
#                 if user_profile.company:
#                     company = user_profile.company
#                     company_name = company.name
#             except Profile.DoesNotExist:
#                 pass
#
#
#         def process_subdocument(subdoc_data):
#             """Recursively process subdocument data"""
#             if not isinstance(subdoc_data, dict):
#                 logger.warning(f"Subdocument data is not a dictionary: {type(subdoc_data)}")
#                 return None
#
#             # Set organization to company name if empty
#             if not subdoc_data.get('organization'):
#                 subdoc_data['organization'] = company_name or ''
#
#             raw_tags = extract_tag_texts(subdoc_data.get('tags', []))
#
#             tag_dicts = [{'text': tag, 'source': 'extracted'} for tag in raw_tags]
#             validated_tags = self.validate_tags_against_database(tag_dicts, company)
#
#             validated_tag_texts = [tag['text'] for tag in validated_tags]
#             document_type = subdoc_data.get('document_type', '')
#             if isinstance(document_type, dict):
#                 document_type_value = document_type.get('type', '')
#                 document_type_value = document_type_value.title() if document_type_value else ''
#             else:
#                 document_type_value = document_type.title() if document_type else ''
#
#             key_values, array_metadata = build_key_values(subdoc_data)
#             subdoc_data['array_fields_metadata'] = array_metadata
#
#             processed = {
#                 'title': subdoc_data.get('title', ''),
#                 'summary': subdoc_data.get('summary', ''),
#                 'description': subdoc_data.get('summary', ''),
#                 'exact_content': subdoc_data.get('exact_content', ''),
#                 'extracted_text': subdoc_data.get('exact_content', ''),
#                 'organization': subdoc_data.get('organization', company_name or ''),
#                 'geography': to_title_case(subdoc_data.get('geography', '')),
#                 'document_type': document_type_value,
#                 'key_entities': subdoc_data.get('key_entities', []),
#                 'url': subdoc_data.get('url', []),
#                 'file_url': subdoc_data.get('file_url', ''),
#                 'source_document': subdoc_data.get('source_document', ''),
#                 'auto_tags': validated_tag_texts,
#                 'manual_tags': [],
#                 'key_values': key_values,
#                 'images': subdoc_data.get('images', []),
#                 'media_type': subdoc_data.get(
#                     'media_type', get_media_type_from_ai_data(subdoc_data.get('document_type', ''))
#                 ),
#                 'error': subdoc_data.get('error')
#             }
#
#             # Recursively process nested subdocuments
#             if subdoc_data.get('subdocument') and isinstance(subdoc_data['subdocument'], list):
#                 processed['subdocument'] = []
#                 for nested_subdoc in subdoc_data['subdocument']:
#                     nested_processed = process_subdocument(nested_subdoc)
#                     if nested_processed:
#                         processed['subdocument'].append(nested_processed)
#
#             return processed
#
#         document_type = ai_data.get('document_type', '')
#         if isinstance(document_type, dict):
#             document_type_value = document_type.get('type', '')
#             document_type_value = document_type_value.title() if document_type_value else ''
#         else:
#             document_type_value = document_type.title() if document_type else ''
#
#         def to_title_case(text):
#             if not text:
#                 return text
#             return str(text).strip().title()
#
#         is_template = document_type_value.lower() == 'template'
#         original_filename = ai_data.get('original_filename')
#         repaired_structured_content = repair_structured_content(ai_data.get('structured_content'))
#
#         main_data = {
#             'title': original_filename if (original_filename and not is_template) else ai_data.get('title', ''),
#             'summary': ai_data.get('summary', ''),
#             'extracted_text': ai_data.get('exact_content', '') or ai_data.get('summary', ''),
#             'organization': ai_data.get('organization', '') or company_name or '',
#             'geography': to_title_case(ai_data.get('geography', '')),
#             'document_type': document_type_value,
#             'key_entities': ai_data.get('key_entities', []),
#             'structured_content': repaired_structured_content,
#             'url': ai_data.get('url', [])
#         }
#
#         # Process main tags
#         auto_tags = process_tags(ai_data.get('tags', []))
#         auto_tags = self.validate_tags_against_database(auto_tags, company)
#
#         # Build enhanced key-values for main document
#         enhanced_key_values, array_fields_metadata = build_key_values(main_data)
#         media_type_value = self.get_main_doc_media_type(ai_data)
#         main_data['array_fields_metadata'] = array_fields_metadata
#
#         # Process subdocuments recursively
#         subdocuments = []
#         if ai_data.get('subdocument') and isinstance(ai_data['subdocument'], list):
#             for subdoc in ai_data['subdocument']:
#                 processed_subdoc = process_subdocument(subdoc)
#                 if processed_subdoc:
#                     subdocuments.append(processed_subdoc)
#
#         # Process failed links
#         failed_links = []
#         if ai_data.get('failed_links') and isinstance(ai_data['failed_links'], list):
#             for failed in ai_data['failed_links']:
#                 processed_failed = process_subdocument(failed)
#                 if processed_failed:
#                     failed_links.append(processed_failed)
#
#         # Process images
#         images = ai_data.get('images', []) if isinstance(ai_data.get('images'), list) else []
#         print("ai_data: ", ai_data)
#         data = {
#             'auto_tags': auto_tags,
#             'enhanced_data': {
#                 'description': main_data['summary'],
#                 'extracted_text': main_data['extracted_text'],
#                 'organization': main_data['organization'],
#                 'enhanced_key_values': enhanced_key_values,
#                 'subdocument': subdocuments,
#                 'failed_links': failed_links,
#                 'images': images,
#                 'structured_content': repaired_structured_content,
#                 'url': ai_data.get('url', [])
#             }
#         }
#
#         if media_type_value:
#             data.get('enhanced_data', {})['media_type'] = media_type_value
#
#         print("data: ", data)
#         return data
#
#
# # Helper class for shared tag processing logic
# class TagProcessor:
#     @staticmethod
#     def process_tags_for_media(tag_names, tag_source, user_profile, company, is_manual=True):
#         """Process tags and create/update tag objects"""
#         tags = []
#
#         for tag_name in tag_names:
#             if isinstance(tag_name, dict):
#                 tag_text = tag_name.get('text', '')
#                 source = tag_name.get('source', tag_source)
#                 description = tag_name.get('description', '')
#             else:
#                 tag_text = tag_name
#                 source = tag_source
#                 description = ''
#
#             # Clean tag name
#             if tag_text.startswith('auto-'):
#                 clean_tag_name = tag_text.replace('auto-', '')
#             else:
#                 clean_tag_name = tag_text
#
#             if is_manual:
#                 tag, created = Tag.objects.get_or_create(
#                     name=clean_tag_name,
#                     defaults={
#                         'created_by': user_profile,
#                         'company': company,
#                         'status': TagChoices.APPROVED,
#                         'source_type': TagSourceChoices.MANUAL,
#                         'description': ''
#                     }
#                 )
#                 if not created and tag.source_type == TagSourceChoices.MANUAL:
#                     tag.status = TagChoices.APPROVED
#                     tag.save()
#             else:
#                 # Auto tags
#                 if source == 'extracted':
#                     source_type = TagSourceChoices.AI_EXTRACTED
#                     status = TagChoices.APPROVED
#                     desc_to_save = ''
#                 else:
#                     source_type = TagSourceChoices.AI_GENERATED
#                     status = TagChoices.PENDING
#                     desc_to_save = description
#
#                 tag, created = Tag.objects.get_or_create(
#                     name=clean_tag_name,
#                     defaults={
#                         'created_by_id': BOT_PROFILE_ID,
#                         'company': company,
#                         'status': status,
#                         'source_type': source_type,
#                         'description': desc_to_save
#                     }
#                 )
#
#             tags.append(tag)
#
#         return tags
#
#
# @method_decorator(staff_member_required, name='dispatch')
# class BatchMediaSaveView(View):
#     """API endpoint for saving batch media data with fault tolerance"""
#
#     def clean_text_to_title_case(self, text):
#         """Convert text to title case, handling common edge cases"""
#         if not text:
#             return text
#
#         # Convert to string and strip whitespace
#         text = str(text).strip()
#
#         # Handle acronyms and special cases
#         words = text.split()
#         cleaned_words = []
#
#         for word in words:
#             # Keep acronyms (all caps) as is
#             if word.isupper() and len(word) > 1:
#                 cleaned_words.append(word)
#             else:
#                 # Convert to title case
#                 cleaned_words.append(word.title())
#
#         return ' '.join(cleaned_words)
#
#
#     def get_or_create_source_document_media(self, source_doc_url, parent_media, company_bot_id, user_profile,
#                                             company_slug):
#         """
#         Download and save source document as a Media object if not already saved.
#         Returns the Media object for the source document.
#         """
#         # Use a class-level cache to track saved source documents within this batch
#         if not hasattr(self, '_source_doc_cache'):
#             self._source_doc_cache = {}
#
#         # Check if we've already processed this source document
#         if source_doc_url in self._source_doc_cache:
#             return self._source_doc_cache[source_doc_url]
#
#         try:
#             # Use the separated function to determine media type and filename
#             media_type, filename, response = determine_media_type_from_url(source_doc_url, parent_media)
#
#             if not media_type or not filename:
#                 print(f"media_type: {media_type} and filename: {filename}")
#                 print(f"Error creating source document media for {source_doc_url}: Media type or file name is null.")
#                 return None
#             print(f"Final filename: {filename}, media_type: {media_type}")
#
#             # Create Media object for source document
#             source_media = Media(
#                 name=filename,
#                 media_type=media_type,
#                 priority=parent_media.priority,
#                 company_bot_id=company_bot_id,
#                 parent=parent_media,
#                 organization=parent_media.organization,
#                 display_mode=FileDisplayMode.PRIVATE
#             )
#
#             # Save the file
#             source_media.file.save(filename, ContentFile(response.content), save=False)
#             source_media.save()
#
#             # Add reference to original URL
#             KeyValue.objects.create(
#                 media=source_media,
#                 key='ORIGINAL_URL',
#                 value=source_doc_url
#             )
#
#             KeyValue.objects.create(
#                 media=source_media,
#                 key='DOCUMENT_TYPE',
#                 value='Source Document'
#             )
#
#             # Cache the result
#             self._source_doc_cache[source_doc_url] = source_media
#
#             print(f"Created source document media: {source_media.id} - {source_media.name}")
#             return source_media
#
#         except Exception as e:
#             print(f"Error creating source document media for {source_doc_url}: {e}")
#             return None
#
#
#     def wait_for_vector_db_save_safe(self, task_id, timeout=30):
#         """Enhanced waiting with better error handling"""
#         import time
#         from celery.result import AsyncResult
#
#         try:
#             intervals = [0.1, 0.2, 0.5, 1.0, 2.0, 3.0]
#             start_time = time.time()
#             attempt = 0
#
#             while time.time() - start_time < timeout:
#                 try:
#                     task = AsyncResult(task_id)
#                     if task.ready():
#                         if task.successful():
#                             return {
#                                 'completed': True,
#                                 'successful': True,
#                                 'result': task.result,
#                                 'wait_time': time.time() - start_time
#                             }
#                         else:
#                             return {
#                                 'completed': True,
#                                 'successful': False,
#                                 'result': f'Vector DB task failed: {task.info}',
#                                 'wait_time': time.time() - start_time,
#                                 'error_type': 'VECTOR_DB_TASK_FAILED'
#                             }
#                 except Exception as poll_error:
#                     print(f"Polling error for task {task_id}: {poll_error}")
#
#                 sleep_time = intervals[min(attempt, len(intervals) - 1)]
#                 time.sleep(sleep_time)
#                 attempt += 1
#
#             return {
#                 'completed': False,
#                 'successful': False,
#                 'result': f'Vector DB save timeout after {timeout}s',
#                 'wait_time': timeout,
#                 'error_type': 'VECTOR_DB_TIMEOUT'
#             }
#
#         except Exception as wait_error:
#             return {
#                 'completed': False,
#                 'successful': False,
#                 'result': f'Wait error: {str(wait_error)}',
#                 'error_type': 'WAIT_ERROR'
#             }
#
#     def save_single_item_with_vector_db_wait_safe(self, item_data, company_bot_id, user_profile, session_id,
#                                                   bypass_similarity=False):
#         """Save a single media item with comprehensive error handling"""
#         file_key = item_data.get('file_key')
#         filename = item_data.get('filename', 'Unknown')
#         file_index = item_data.get('file_index')
#
#         # if "fail" in filename.lower():
#         #     print(f"Forced save failure for {filename}")
#         #     raise ValueError(f"Forced save failure for {filename}")
#
#         try:
#             company_bot = CompanyBot.objects.get(id=company_bot_id)
#             selected_company = None
#             if item_data.get('organization_slug'):
#                 try:
#                     selected_company = Company.objects.get(slug=item_data['organization_slug'])
#                 except Company.DoesNotExist:
#                     pass
#
#             if not selected_company and user_profile:
#                 selected_company = user_profile.company
#
#             if not selected_company:
#                 selected_company = company_bot.company
#
#             if selected_company:
#                 company_slug = selected_company.slug
#             else:
#                 company_slug = company_bot.company.slug
#             extracted_text = item_data.get('extracted_text', '')
#
#             # Step 1: Similarity check
#             if ENABLE_SIMILARITY_CHECK and not bypass_similarity:
#                 try:
#                     DuplicateDetector.check_for_duplicates(
#                         extracted_text=extracted_text,
#                         company_slug=company_slug,
#                         trigram_threshold=0,
#                         semantic_threshold=0.85,
#                         trigram_exact_threshold=0.90,
#                         semantic_exact_threshold=0.9
#                     )
#                 except Exception as similarity_error:
#                     return {
#                         'success': False,
#                         'filename': filename,
#                         'message': f'Similarity check failed: {str(similarity_error)}',
#                         'error_type': 'SIMILARITY_CHECK_FAILED',
#                         'file_index': file_index,
#                         'file_key': file_key,
#                         'session_id': session_id,
#                         'vector_db_saved': False
#                     }
#
#             # Step 2: Retrieve file from cache
#             file_content = None
#             file_name = None
#
#             if file_key:
#                 cached_file = CacheManager.get_cached_item(file_key)
#                 if cached_file:
#                     file_content = cached_file.get('content')
#                     file_name = cached_file.get('name')
#                 else:
#                     return {
#                         'success': False,
#                         'filename': filename,
#                         'message': 'File not found in cache for saving',
#                         'error_type': 'FILE_NOT_FOUND_IN_CACHE',
#                         'file_index': file_index,
#                         'file_key': file_key,
#                         'session_id': session_id,
#                         'vector_db_saved': False
#                     }
#
#             # Step 3: Create and save media
#             try:
#                 organization_instance = None
#                 if item_data.get('organization_slug'):
#                     try:
#                         organization_instance = Company.objects.get(slug=item_data['organization_slug'])
#                     except Company.DoesNotExist:
#                         print(f"Warning: Company with slug {item_data['organization_slug']} not found")
#
#                 media = Media(
#                     name=item_data['name'],
#                     media_type=item_data['media_type'],
#                     priority=item_data['priority'],
#                     description=item_data['description'],
#                     company_bot_id=company_bot_id,
#                     organization=organization_instance,
#                 )
#
#                 if file_content and file_name:
#                     from django.core.files.base import ContentFile
#                     media.file.save(file_name, ContentFile(file_content), save=False)
#
#                 # Save and get the vector DB task ID
#                 vector_task_id = media.save(company_slug=company_slug)
#
#             except Exception as media_save_error:
#                 return {
#                     'success': False,
#                     'filename': filename,
#                     'message': f'Media save failed: {str(media_save_error)}',
#                     'error_type': 'MEDIA_SAVE_FAILED',
#                     'file_index': file_index,
#                     'file_key': file_key,
#                     'session_id': session_id,
#                     'vector_db_saved': False
#                 }
#
#             # Step 4: Process tags and key-values with prioritized company
#             try:
#                 all_tags = []
#
#                 # Process manual tags with selected company (from dropdown priority)
#                 manual_tags = TagProcessor.process_tags_for_media(
#                     item_data.get('manual_tags', []),
#                     'manual',
#                     user_profile,
#                     selected_company,
#                     is_manual=True
#                 )
#                 all_tags.extend(manual_tags)
#
#                 # Process auto tags with selected company (from dropdown priority)
#                 auto_tags = TagProcessor.process_tags_for_media(
#                     item_data.get('auto_tags', []),
#                     'extracted',
#                     user_profile,
#                     selected_company,
#                     is_manual=False
#                 )
#                 all_tags.extend(auto_tags)
#
#                 if all_tags:
#                     media.tags.set(all_tags)
#
#                 # Key-value pairs - ensure organization is saved
#                 org_found = False
#                 print("item_data: ", item_data)
#                 for kv in item_data.get('key_values', []):
#                     KeyValue.objects.create(
#                         media=media,
#                         key=kv['key'],
#                         value=kv['value']
#                     )
#
#             except Exception as tag_kv_error:
#                 print(f"Warning: Tag/KV processing failed for {filename}: {tag_kv_error}")
#
#             # Step 5: Wait for vector DB save
#             vector_result = {'successful': True, 'result': 'No vector task'}
#             if vector_task_id:
#                 vector_result = self.wait_for_vector_db_save_safe(vector_task_id)
#
#                 if not vector_result['successful']:
#                     print(f"Vector DB save failed for media {media.id}: {vector_result['result']}")
#                     return {
#                         'success': False,
#                         'filename': filename,
#                         'media_id': media.id,
#                         'message': f"Saved to database but vector DB failed: {vector_result['result']}",
#                         'error_type': vector_result.get('error_type', 'VECTOR_DB_FAILED'),
#                         'file_index': file_index,
#                         'file_key': file_key,
#                         'session_id': session_id,
#                         'vector_db_saved': False,
#                         'partial_success': True,
#                         'vector_task_id': vector_task_id,
#                         'subdocument_results': [],
#                         'image_results': []
#                     }
#
#             # Step 5.5: Process source documents if no subdocuments but URLs exist
#             source_document_results = []
#             if not item_data.get('subdocument') and item_data.get('url'):
#                 print(f"Processing source documents for main document without subdocuments")
#
#                 for source_url in item_data.get('url', []):
#                     try:
#                         source_media = self.get_or_create_source_document_media(
#                             source_url,
#                             media,
#                             company_bot_id,
#                             user_profile,
#                             company_slug
#                         )
#                         if source_media:
#                             source_document_results.append({
#                                 'success': True,
#                                 'source_media_id': source_media.id,
#                                 'source_url': source_url,
#                                 'title': source_media.name
#                             })
#                             print(f"Saved source document: {source_media.name} (ID: {source_media.id})")
#                         else:
#                             source_document_results.append({
#                                 'success': False,
#                                 'error': f'Failed to create source document for {source_url}',
#                                 'source_url': source_url
#                             })
#                     except Exception as source_error:
#                         print(f"Error creating source document for {source_url}: {source_error}")
#                         source_document_results.append({
#                             'success': False,
#                             'error': str(source_error),
#                             'source_url': source_url
#                         })
#
#             # Step 6: Process subdocuments recursively
#             subdocument_results = []
#             if item_data.get('subdocument'):
#                 # Cache subdocuments before processing
#                 self._cache_subdocuments_recursive(
#                     item_data['subdocument'],
#                     session_id,
#                     file_index,
#                     ""
#                 )
#
#                 subdoc_results = self.process_subdocuments_recursive(
#                     item_data['subdocument'],
#                     media,
#                     company_bot_id,
#                     user_profile,
#                     company_slug,
#                     session_id,
#                     file_index,
#                     ""
#                 )
#                 subdocument_results.extend(subdoc_results)
#
#             # Step 7: Process images
#             image_results = []
#             if item_data.get('images'):
#                 for index, img_data in enumerate(item_data['images']):
#                     try:
#                         img_result = self.save_media_image(img_data, media, index)
#                         image_results.append(img_result)
#                     except Exception as img_error:
#                         print(f"Warning: Image save failed: {img_error}")
#                         image_results.append({
#                             'success': False,
#                             'error': str(img_error)
#                         })
#
#             # Step 8: Success - clean up cache
#             if file_key and cache.get(file_key):
#                 cache.delete(file_key)
#                 print(f"Cleaned up cache for {file_key}")
#
#             return {
#                 'success': True,
#                 'filename': filename,
#                 'media_id': media.id,
#                 'message': 'Successfully saved',
#                 'file_index': file_index,
#                 'vector_db_saved': vector_result['successful'],
#                 'vector_wait_time': vector_result.get('wait_time', 0),
#                 'vector_task_id': vector_task_id,
#                 'subdocument_results': subdocument_results,
#                 'source_document_results': source_document_results,
#                 'image_results': image_results
#             }
#
#         except Exception as unexpected_error:
#             print(f"Unexpected error processing {filename}: {unexpected_error}")
#             traceback.print_exc()
#             return {
#                 'success': False,
#                 'filename': filename,
#                 'message': f'Unexpected error: {str(unexpected_error)}',
#                 'error_type': 'UNEXPECTED_ERROR',
#                 'file_index': file_index,
#                 'file_key': file_key,
#                 'session_id': session_id,
#                 'vector_db_saved': False
#             }
#
#     def _cache_subdocuments_recursive(self, subdocuments, session_id, parent_index, parent_path):
#         """Cache subdocuments recursively for retry purposes"""
#         for i, subdoc in enumerate(subdocuments):
#             current_path = f"{parent_path}_{i}" if parent_path else str(i)
#
#             # Cache this subdocument with all its data
#             CacheManager.cache_subdocument(subdoc, session_id, parent_index, current_path)
#
#             # Recursively cache nested subdocuments
#             if subdoc.get('subdocument'):
#                 self._cache_subdocuments_recursive(
#                     subdoc['subdocument'],
#                     session_id,
#                     parent_index,
#                     current_path
#                 )
#
#     def process_subdocuments_recursive(self, subdocuments, parent_media, company_bot_id, user_profile,
#                                        company_slug, session_id, parent_index, parent_path):
#         """Recursively process subdocuments at any depth"""
#         results = []
#
#         for i, subdoc_data in enumerate(subdocuments):
#             current_path = f"{parent_path}_{i}" if parent_path else str(i)
#             subdoc_cache_key = CacheManager.get_cache_key(session_id, 'subdoc', f"{parent_index}_{current_path}")
#
#             try:
#                 subdoc_result = self.save_subdocument(
#                     subdoc_data, parent_media, company_bot_id, user_profile, company_slug
#                 )
#                 subdoc_result['cache_key'] = subdoc_cache_key
#                 subdoc_result['path'] = current_path
#
#                 # If this subdocument has nested subdocuments, process them recursively
#                 if subdoc_data.get('subdocument') and subdoc_result['success']:
#                     subdoc_media_id = subdoc_result['subdoc_media_id']
#                     subdoc_media = Media.objects.get(id=subdoc_media_id)
#
#                     nested_results = self.process_subdocuments_recursive(
#                         subdoc_data['subdocument'],
#                         subdoc_media,
#                         company_bot_id,
#                         user_profile,
#                         company_slug,
#                         session_id,
#                         parent_index,
#                         current_path
#                     )
#                     subdoc_result['nested_subdocument_results'] = nested_results
#
#                 results.append(subdoc_result)
#
#             except Exception as subdoc_error:
#                 print(f"Warning: Subdocument save failed: {subdoc_error}")
#                 results.append({
#                     'success': False,
#                     'error': str(subdoc_error),
#                     'cache_key': subdoc_cache_key,
#                     'path': current_path,
#                     'title': subdoc_data.get('title', f'Subdocument at {current_path}')
#                 })
#
#         return results
#
#     def save_subdocument(self, subdoc_data, parent_media, company_bot_id, user_profile, company_slug):
#         """Save a subdocument as a separate Media object linked to parent"""
#         try:
#             source_doc_url = subdoc_data.get('source_document')
#             actual_parent = parent_media
#
#             if source_doc_url:
#                 # Try to get or create the source document media
#                 source_media = self.get_or_create_source_document_media(
#                     source_doc_url,
#                     parent_media,
#                     company_bot_id,
#                     user_profile,
#                     company_slug
#                 )
#
#                 if source_media:
#                     # Use the source document as the parent instead
#                     actual_parent = source_media
#                     print(f"Using source document {source_media.id} as parent for subdocument")
#
#             file_url = subdoc_data.get('file_url')
#             if not file_url:
#                 raise ValueError(f"No file URL provided for subdocument")
#
#             # Validate file format based on URL extension before downloading
#             from urllib.parse import urlparse, unquote
#             parsed_url = urlparse(file_url)
#             path = unquote(parsed_url.path)
#
#             # Check if URL has an extension and validate it
#             if '.' in path:
#                 url_extension = path.rsplit('.', 1)[-1].lower()
#                 if url_extension and not FileTypeChoices.is_valid_extension(url_extension):
#                     raise ValueError(f"Unsupported file format: .{url_extension}")
#
#             print(f"Downloading file from URL: {file_url}")
#             headers = {
#                 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
#                 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
#             }
#
#             try:
#                 response = requests.get(file_url, headers=headers, timeout=30, allow_redirects=True)
#                 response.raise_for_status()
#             except requests.exceptions.RequestException as e:
#                 error_msg = f"Failed to download file from {file_url}: {str(e)}"
#                 print(f"Error: {error_msg}")
#                 raise ValueError(error_msg)
#
#             # Additional validation based on content-type
#             content_type = response.headers.get('content-type', '').lower()
#
#             # Map content types to file extensions
#             content_type_mapping = {
#                 'application/pdf': 'pdf',
#                 'application/msword': 'doc',
#                 'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
#                 'text/plain': 'txt',
#                 'text/csv': 'csv',
#                 'application/vnd.ms-excel': 'xls',
#                 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
#             }
#
#             # Check if content type is supported
#             content_extension = None
#             for mime_type, ext in content_type_mapping.items():
#                 if mime_type in content_type:
#                     content_extension = ext
#                     break
#
#             if content_extension and not FileTypeChoices.is_valid_extension(content_extension):
#                 raise ValueError(f"Unsupported content type: {content_type}")
#
#             # Determine filename from URL or content-disposition
#             filename = None
#             content_disposition = response.headers.get('content-disposition')
#             if content_disposition:
#                 import re
#                 matches = re.findall('filename="?([^"]+)"?', content_disposition)
#                 if matches:
#                     filename = matches[0]
#                     # Validate filename extension
#                     if '.' in filename:
#                         file_ext = filename.rsplit('.', 1)[-1].lower()
#                         if not FileTypeChoices.is_valid_extension(file_ext):
#                             raise ValueError(f"Unsupported file format in download: .{file_ext}")
#
#             if not filename:
#                 # Extract from URL
#                 from urllib.parse import urlparse, unquote
#                 parsed_url = urlparse(file_url)
#                 path = parsed_url.path
#                 filename = os.path.basename(unquote(path))
#
#                 # For Google Docs/Drive, create appropriate filename based on media type
#                 if 'docs.google.com' in file_url or 'drive.google.com' in file_url:
#                     base_title = subdoc_data.get('title', 'Document')
#                     media_type = subdoc_data.get('media_type', FileTypeChoices.TXT.value)
#
#                     # Get extension from media type using the enum's mapping
#                     extension_mapping = FileTypeChoices.get_extension_mapping()
#                     extension = extension_mapping.get(media_type, '.txt')
#
#                     filename = f"{slugify(base_title, allow_unicode=True)}{extension}"
#
#                 # Ensure filename has an extension
#                 if not os.path.splitext(filename)[1]:
#                     # Add extension based on media type using the enum's mapping
#                     media_type = subdoc_data.get('media_type', FileTypeChoices.TXT.value)
#                     extension_mapping = FileTypeChoices.get_extension_mapping()
#                     extension = extension_mapping.get(media_type, '.txt')
#                     filename += extension
#
#             # Use filename (without extension) as the subdocument title
#             filename_without_ext = os.path.splitext(filename)[0] if filename else ""
#
#             if filename_without_ext and len(filename_without_ext.strip()) > 0:
#                 subdoc_title = filename_without_ext
#                 print(f"Using filename as title: {subdoc_title}")
#             else:
#                 llm_title = subdoc_data.get('title', '').strip()
#                 if llm_title and len(llm_title) > 0:
#                     subdoc_title = llm_title
#                     print(f"Using LLM-extracted title: {subdoc_title}")
#                 else:
#                     # Final fallback - create a descriptive title
#                     subdoc_title = f"Document from {Path(urlparse(file_url).path).name or 'linked document'}"
#                     print(f"Using fallback title: {subdoc_title}")
#
#             print(f"Saving subdocument with title: {subdoc_title} (from filename: {filename})")
#
#             # Check for forced failure
#             # for kv in subdoc_data.get('key_values', []):
#             #     if "fail" in kv.get('value', '').lower():
#             #         print(f"Forced subdoc extraction failure for {subdoc_title}")
#             #         raise ValueError(f"Forced subdoc extraction failure for {subdoc_title}")
#
#             # Get file content
#             file_content = response.content
#             if not file_content:
#                 raise ValueError(f"Downloaded file is empty for URL: {file_url}")
#
#             # IMPORTANT FIX: Get organization from subdocument data FIRST
#             subdoc_org = subdoc_data.get('organization', '')
#
#             # If subdocument has no organization, try to get from key-values
#             if not subdoc_org:
#                 for kv in subdoc_data.get('key_values', []):
#                     if kv.get('key') == 'ORGANIZATION' and kv.get('value'):
#                         subdoc_org = kv.get('value')
#                         break
#
#             # If still no organization, get from parent media's key-values
#             if not subdoc_org:
#                 parent_kvs = KeyValue.objects.filter(media=parent_media, key='ORGANIZATION')
#                 if parent_kvs.exists():
#                     subdoc_org = parent_kvs.first().value
#
#             # Only use company name as last resort
#             if not subdoc_org and user_profile and user_profile.company:
#                 subdoc_org = user_profile.company.name
#
#             subdoc_org = self.clean_text_to_title_case(subdoc_org)
#             print(f"Subdocument organization resolved to: {subdoc_org}")
#             organization_instance = None
#             if subdoc_data.get('organization_slug'):
#                 try:
#                     organization_instance = Company.objects.get(slug=subdoc_data['organization_slug'])
#                 except Company.DoesNotExist:
#                     print(f"Warning: Company with slug {subdoc_data['organization_slug']} not found")
#
#             # Create subdocument media
#             subdoc_media = Media(
#                 name=subdoc_title,
#                 media_type=subdoc_data.get('media_type', FileTypeChoices.TXT.value),
#                 priority=parent_media.priority,
#                 description=subdoc_data.get('description', subdoc_data.get('summary', '')),
#                 company_bot_id=company_bot_id,
#                 parent=actual_parent,
#                 organization=organization_instance,
#                 display_mode=subdoc_data.get('display_mode', FileDisplayMode.VISIBLE),
#             )
#
#             # Save the file content - use the original filename
#             try:
#                 subdoc_media.file.save(filename, ContentFile(file_content), save=False)
#                 print(f"Successfully saved file: {filename}")
#             except Exception as e:
#                 error_msg = f"Failed to save file content for subdocument: {str(e)}"
#                 print(f"Error: {error_msg}")
#                 raise ValueError(error_msg)
#
#             # Save the media object
#             subdoc_media.save()
#
#             selected_company = None
#             if subdoc_data.get('organization_slug'):
#                 try:
#                     selected_company = Company.objects.get(slug=subdoc_data['organization_slug'])
#                 except Company.DoesNotExist:
#                     pass
#
#             if not selected_company and user_profile:
#                 selected_company = user_profile.company
#
#             if not selected_company:
#                 company_bot = CompanyBot.objects.get(id=company_bot_id)
#                 selected_company = company_bot.company
#
#             all_tags = []
#
#             manual_tags = subdoc_data.get('manual_tags', [])
#             if manual_tags:
#                 manual_tag_objs = TagProcessor.process_tags_for_media(
#                     manual_tags,
#                     'manual',
#                     user_profile,
#                     selected_company,
#                     is_manual=True
#                 )
#                 all_tags.extend(manual_tag_objs)
#
#             auto_tags = subdoc_data.get('auto_tags', [])
#             if auto_tags:
#                 auto_tag_objs = TagProcessor.process_tags_for_media(
#                     auto_tags,
#                     'extracted',
#                     user_profile,
#                     selected_company,
#                     is_manual=False
#                 )
#                 all_tags.extend(auto_tag_objs)
#
#             if all_tags:
#                 subdoc_media.tags.set(all_tags)
#
#             # Key-value pairs - handle organization specially
#             for kv in subdoc_data.get('key_values', []):
#                 if kv['key'] == 'DOCUMENT TYPE':
#                     doc_type_value = kv['value']
#                     if isinstance(doc_type_value, dict):
#                         actual_value = doc_type_value.get('type', '')
#                         actual_value = actual_value.title() if actual_value else ''
#                     else:
#                         actual_value = doc_type_value.title() if doc_type_value else ''
#
#                     KeyValue.objects.create(
#                         media=subdoc_media,
#                         key='DOCUMENT TYPE',
#                         value=actual_value
#                     )
#                 else:
#                     KeyValue.objects.create(
#                         media=subdoc_media,
#                         key=kv['key'],
#                         value=kv['value']
#                     )
#
#             print(f"Saved {len(subdoc_data.get('key_values', []))} key-values for subdoc: {subdoc_title}")
#
#             # Process subdocument images
#             if subdoc_data.get('images'):
#                 for index, img_data in enumerate(subdoc_data['images']):
#                     self.save_media_image(img_data, subdoc_media, index)
#
#             return {
#                 'success': True,
#                 'subdoc_media_id': subdoc_media.id,
#                 'title': subdoc_media.name
#             }
#
#         except Exception as e:
#             print(f"Error saving subdocument: {e}")
#             traceback.print_exc()
#             return {
#                 'success': False,
#                 'error': str(e),
#                 'title': subdoc_data.get('title', 'Unknown subdocument')
#             }
#
#     def save_media_image(self, img_data, media, index):
#         """Save image associated with media"""
#         try:
#             if img_data.get('base64'):
#                 try:
#                     # Extract image format from base64 string
#                     base64_str = img_data['base64']
#                     if base64_str.startswith('data:'):
#                         mime_start = base64_str.find('image/') + 6
#                         mime_end = base64_str.find(';', mime_start)
#                         image_format = base64_str[mime_start:mime_end]
#                         base64_data = base64_str.split(',')[1]
#                     else:
#                         image_format = img_data.get('format', 'png')
#                         base64_data = base64_str
#
#                     # Decode base64 to bytes
#                     image_bytes = base64.b64decode(base64_data)
#                     base_name, _ = os.path.splitext(media.name)
#                     safe_base = slugify(base_name, allow_unicode=True)
#                     file_name = f"img_{safe_base}_{index}.{image_format}"
#
#                     media_image = MediaImage(
#                         name=file_name,
#                         media=media,
#                         page=img_data.get('page'),
#                         index=img_data.get('index', index),
#                         width=img_data.get('width'),
#                         height=img_data.get('height'),
#                         base64_str=img_data.get('base64', '')
#                     )
#
#                     # Create file
#                     media_image.file.save(file_name, ContentFile(image_bytes), save=False)
#
#                     # Set media type
#                     if image_format.lower() in ['jpg', 'jpeg']:
#                         media_image.media_type = MediaTypeChoices.JPEG
#                     elif image_format.lower() == 'png':
#                         media_image.media_type = MediaTypeChoices.PNG
#                     elif image_format.lower() == 'svg':
#                         media_image.media_type = MediaTypeChoices.SVG
#                     elif image_format.lower() == 'webp':
#                         media_image.media_type = MediaTypeChoices.WEBP
#
#                     media_image.save()
#
#                     return {
#                         'success': True,
#                         'image_id': media_image.id,
#                         'page': media_image.page
#                     }
#
#                 except Exception as e:
#                     print(f"Error processing image base64: {e}")
#                     return {
#                         'success': False,
#                         'error': str(e)
#                     }
#
#         except Exception as e:
#             print(f"Error saving media image: {e}")
#             return {
#                 'success': False,
#                 'error': str(e)
#             }
#
#     def post(self, request):
#         try:
#             self._source_doc_cache = {}
#             data = json.loads(request.body)
#             company_bot_id = data.get('company_bot_id')
#             media_items = data.get('items', [])
#             session_id = data.get('session_id')
#
#             results = []
#             stats = {
#                 'total': len(media_items),
#                 'successful': 0,
#                 'failed': 0,
#                 'partial_success': 0,
#                 'timeouts': 0,
#                 'similarity_failures': 0
#             }
#
#             # Get current user's profile
#             try:
#                 user_profile = Profile.objects.get(email=request.user.email)
#             except Profile.DoesNotExist:
#                 user_profile = None
#
#             print(f"Starting batch save for {len(media_items)} files")
#
#             # Process each file with fault tolerance
#             for i, item_data in enumerate(media_items):
#                 filename = item_data.get('filename', f'File_{i}')
#                 print(f"Processing file {i + 1}/{len(media_items)}: {filename}")
#
#                 try:
#                     bypass_similarity = item_data.get('bypass_similarity', False)
#                     result = self.save_single_item_with_vector_db_wait_safe(
#                         item_data=item_data,
#                         company_bot_id=company_bot_id,
#                         user_profile=user_profile,
#                         session_id=session_id,
#                         bypass_similarity=bypass_similarity
#                     )
#
#                     # Track statistics
#                     if result['success']:
#                         stats['successful'] += 1
#                     else:
#                         stats['failed'] += 1
#                         if result.get('partial_success'):
#                             stats['partial_success'] += 1
#                         if result.get('error_type') in ['VECTOR_DB_TIMEOUT', 'WAIT_ERROR']:
#                             stats['timeouts'] += 1
#                         if result.get('error_type') == 'SIMILARITY_CHECK_FAILED':
#                             stats['similarity_failures'] += 1
#
#                     results.append(result)
#                     print(
#                         f"File {i + 1} result: {'✓' if result['success'] else '✗'} - {result.get('message', 'No message')}")
#
#                 except Exception as item_error:
#                     print(f"Critical error processing {filename}: {item_error}")
#                     stats['failed'] += 1
#                     results.append({
#                         'success': False,
#                         'filename': filename,
#                         'message': f'Critical processing error: {str(item_error)}',
#                         'error_type': 'CRITICAL_ERROR',
#                         'file_index': item_data.get('file_index', i),
#                         'file_key': item_data.get('file_key'),
#                         'session_id': session_id,
#                         'vector_db_saved': False
#                     })
#
#             # Preserve cache for failed files
#             failed_cache_keys = []
#             for r in results:
#                 if not r['success'] and r.get('file_key'):
#                     failed_cache_keys.append(r['file_key'])
#                 # Also preserve cache for failed subdocuments
#                 if r.get('subdocument_results'):
#                     for subdoc_result in r['subdocument_results']:
#                         if not subdoc_result.get('success') and subdoc_result.get('cache_key'):
#                             failed_cache_keys.append(subdoc_result['cache_key'])
#
#             if failed_cache_keys:
#                 CacheManager.extend_cache_timeout(failed_cache_keys)
#
#             # Generate summary message
#             summary_message = self.generate_batch_summary(stats)
#             print(f"Batch complete: {summary_message}")
#
#             return JsonResponse({
#                 'success': True,
#                 'results': results,
#                 'stats': stats,
#                 'summary_message': summary_message,
#                 'session_id': session_id
#             })
#
#         except json.JSONDecodeError:
#             return JsonResponse({
#                 'success': False,
#                 'error': 'Invalid JSON data'
#             }, status=400)
#         except Exception as batch_error:
#             print(f"Batch processing error: {batch_error}")
#             traceback.print_exc()
#             return JsonResponse({
#                 'success': False,
#                 'error': f'Batch processing failed: {str(batch_error)}'
#             }, status=500)
#
#     def generate_batch_summary(self, stats):
#         """Generate human-readable batch summary"""
#         total = stats['total']
#         successful = stats['successful']
#         failed = stats['failed']
#
#         if successful == total:
#             return f"All {total} files processed successfully!"
#         elif successful == 0:
#             return f"All {total} files failed to process."
#         else:
#             message_parts = [f"{successful}/{total} files successful"]
#             if failed > 0:
#                 message_parts.append(f"{failed} failed")
#             if stats['timeouts'] > 0:
#                 message_parts.append(f"{stats['timeouts']} timed out")
#             if stats['similarity_failures'] > 0:
#                 message_parts.append(f"{stats['similarity_failures']} similarity check failures")
#             if stats['partial_success'] > 0:
#                 message_parts.append(f"{stats['partial_success']} partial successes")
#
#             return ", ".join(message_parts) + "."
#
#
# @method_decorator(staff_member_required, name='dispatch')
# class BatchMediaRetrySaveView(View):
#     """API endpoint for retrying save of a single media item"""
#
#     def post(self, request):
#         try:
#             data = json.loads(request.body)
#             item_data = data.get('item_data')
#             company_bot_id = data.get('company_bot_id')
#             session_id = data.get('session_id')
#             bypass_similarity = data.get('bypass_similarity', False)
#             is_subdocument = data.get('is_subdocument', False)
#             parent_media_id = data.get('parent_media_id')
#
#             # Get current user's profile
#             try:
#                 user_profile = Profile.objects.get(email=request.user.email)
#             except Profile.DoesNotExist:
#                 user_profile = None
#
#             if is_subdocument and parent_media_id:
#                 # Retry subdocument save
#                 try:
#                     parent_media = Media.objects.get(id=parent_media_id)
#                     company_bot = CompanyBot.objects.get(id=company_bot_id)
#                     company_slug = company_bot.company.slug
#
#                     save_view = BatchMediaSaveView()
#                     result = save_view.save_subdocument(
#                         subdoc_data=item_data,
#                         parent_media=parent_media,
#                         company_bot_id=company_bot_id,
#                         user_profile=user_profile,
#                         company_slug=company_slug
#                     )
#
#                     return JsonResponse({
#                         'success': True,
#                         'result': result
#                     })
#                 except Exception as e:
#                     print(f"Subdocument retry error: {e}")
#                     traceback.print_exc()
#                     return JsonResponse({
#                         'success': False,
#                         'error': str(e)
#                     }, status=400)
#             else:
#                 # Retry main document save
#                 save_view = BatchMediaSaveView()
#                 result = save_view.save_single_item_with_vector_db_wait_safe(
#                     item_data=item_data,
#                     company_bot_id=company_bot_id,
#                     user_profile=user_profile,
#                     session_id=session_id,
#                     bypass_similarity=bypass_similarity
#                 )
#
#                 return JsonResponse({
#                     'success': True,
#                     'result': result
#                 })
#
#         except Exception as e:
#             print(f"Unexpected error in retry save: {e}")
#             traceback.print_exc()
#             return JsonResponse({
#                 'success': False,
#                 'error': str(e)
#             }, status=400)
#
#
# @method_decorator(staff_member_required, name='dispatch')
# class VectorDBTaskStatusView(View):
#     """Check status of vector DB save task"""
#
#     def post(self, request):
#         try:
#             from celery.result import AsyncResult
#             data = json.loads(request.body)
#             task_id = data.get('task_id')
#
#             if not task_id:
#                 return JsonResponse({'success': False, 'error': 'No task_id provided'})
#
#             task = AsyncResult(task_id)
#
#             return JsonResponse({
#                 'success': True,
#                 'status': task.status,
#                 'ready': task.ready(),
#                 'successful': task.successful() if task.ready() else None,
#                 'result': task.result if task.ready() else None
#             })
#
#         except Exception as e:
#             return JsonResponse({'success': False, 'error': str(e)}, status=400)
