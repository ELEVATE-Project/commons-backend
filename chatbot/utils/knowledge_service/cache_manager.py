import traceback
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator
from django.http import JsonResponse
from django.views import View
from chatbot.models import Profile, FileTypeChoices
import json
from django.core.cache import cache
from django.conf import settings


CACHE_TIMEOUT = getattr(settings, 'BATCH_UPLOAD_CACHE_TIMEOUT', 7200)


class CacheManager:
    """Centralized cache management for batch upload"""

    @staticmethod
    def get_cache_key(session_id, item_type, item_id):
        """Generate consistent cache keys with proper sanitization"""
        import re

        # Sanitize all components to ensure memcached compatibility
        sanitized_session_id = re.sub(r'[^a-zA-Z0-9\-_.]', '_', str(session_id))
        sanitized_item_type = re.sub(r'[^a-zA-Z0-9\-_.]', '_', str(item_type))
        sanitized_item_id = re.sub(r'[^a-zA-Z0-9\-_.]', '_', str(item_id))

        # Remove multiple consecutive underscores
        sanitized_session_id = re.sub(r'_+', '_', sanitized_session_id)
        sanitized_item_type = re.sub(r'_+', '_', sanitized_item_type)
        sanitized_item_id = re.sub(r'_+', '_', sanitized_item_id)

        # Generate the cache key
        cache_key = f"batch_upload_{sanitized_session_id}_{sanitized_item_type}_{sanitized_item_id}"

        # Final length check
        if len(cache_key) > 240:
            import hashlib
            key_hash = hashlib.md5(cache_key.encode('utf-8')).hexdigest()
            cache_key = f"batch_upload_{sanitized_session_id}_{sanitized_item_type}_{key_hash[:16]}"

        # Final sanitization pass
        cache_key = re.sub(r'[^a-zA-Z0-9\-_.]', '_', cache_key)

        return cache_key

    @staticmethod
    def cache_file(file, session_id, file_index):
        """Cache uploaded file content with sanitized cache key"""
        try:
            import re
            import hashlib

            file_content = b''
            for chunk in file.chunks():
                file_content += chunk

            # More aggressive sanitization for memcached compatibility
            # Remove all non-alphanumeric characters except dots, hyphens, underscores
            sanitized_name = re.sub(r'[^a-zA-Z0-9\-_.]', '_', file.name)
            # Remove multiple consecutive underscores
            sanitized_name = re.sub(r'_+', '_', sanitized_name)
            # Remove leading/trailing underscores
            sanitized_name = sanitized_name.strip('_')
            # Ensure reasonable length (memcached has 250 char limit for keys)
            if len(sanitized_name) > 30:
                # Keep first 30 chars and add hash of full name for uniqueness
                name_hash = hashlib.md5(file.name.encode('utf-8')).hexdigest()[:8]
                sanitized_name = sanitized_name[:22] + '_' + name_hash

            # Generate cache key with additional validation
            cache_key_suffix = f"{file_index}_{sanitized_name}"
            # Ensure the final cache key component doesn't have problematic characters
            cache_key_suffix = re.sub(r'[^a-zA-Z0-9\-_.]', '_', cache_key_suffix)

            cache_key = CacheManager.get_cache_key(session_id, 'file', cache_key_suffix)

            # Additional validation: ensure cache key is memcached compatible
            # Total length should be under 250 chars and contain only safe characters
            if len(cache_key) > 240:  # Leave some buffer
                # If still too long, use a hash-based approach
                key_hash = hashlib.md5(cache_key.encode('utf-8')).hexdigest()
                cache_key = f"batch_upload_{session_id}_file_{file_index}_{key_hash[:16]}"

            # Final validation - ensure only safe characters
            cache_key = re.sub(r'[^a-zA-Z0-9\-_.]', '_', cache_key)

            cache_data = {
                'content': file_content,
                'name': file.name,  # Keep original name
                'size': file.size,
                'type': 'file',
                'file_index': file_index
            }

            cache.set(cache_key, cache_data, timeout=CACHE_TIMEOUT)
            print(f"Cached file: {cache_key} (original: {file.name})")
            return cache_key
        except Exception as e:
            print(f"Error caching file {file.name}: {e}")
            import traceback
            traceback.print_exc()
            return None

    @staticmethod
    def cache_subdocument(subdoc_data, session_id, parent_index, subdoc_path):
        """Cache subdocument data for retry purposes - with all fields"""
        try:
            cache_key = CacheManager.get_cache_key(session_id, 'subdoc', f"{parent_index}_{subdoc_path}")

            # Ensure all subdocument fields are included
            complete_subdoc_data = {
                'title': subdoc_data.get('title', ''),
                'summary': subdoc_data.get('summary', ''),
                'description': subdoc_data.get('description', subdoc_data.get('summary', '')),
                'media_type': subdoc_data.get('media_type', FileTypeChoices.TXT.value),
                'priority': subdoc_data.get('priority', 'P1'),
                'extracted_text': subdoc_data.get('extracted_text', subdoc_data.get('exact_content', '')),
                'exact_content': subdoc_data.get('exact_content', ''),
                'organization': subdoc_data.get('organization', ''),
                'document_type': subdoc_data.get('document_type', ''),
                'key_entities': subdoc_data.get('key_entities', []),
                'manual_tags': subdoc_data.get('manual_tags', []),
                'auto_tags': subdoc_data.get('auto_tags', []),
                'tags': subdoc_data.get('tags', []),
                'key_values': subdoc_data.get('key_values', []),
                'images': subdoc_data.get('images', []),
                'subdocument': subdoc_data.get('subdocument', []),
                'url': subdoc_data.get('url', [])
            }

            cache_data = {
                'data': complete_subdoc_data,
                'parent_index': parent_index,
                'path': subdoc_path,
                'type': 'subdocument'
            }

            cache.set(cache_key, cache_data, timeout=CACHE_TIMEOUT)
            print(f"Cached subdocument: {cache_key} with data: {complete_subdoc_data.get('title', 'No title')}")
            return cache_key
        except Exception as e:
            print(f"Error caching subdocument: {e}")
            traceback.print_exc()
            return None

    @staticmethod
    def get_cached_item(cache_key):
        """Retrieve item from cache with Redis-specific debugging"""
        import time
        from django.core.cache import cache

        max_retries = 2
        retry_delay = 0.1

        for attempt in range(max_retries + 1):
            try:
                # Add timing to detect slow Redis responses
                start_time = time.time()
                cached_data = cache.get(cache_key)
                response_time = time.time() - start_time

                if cached_data:
                    print(f"✓ Cache HIT: {cache_key} (attempt {attempt + 1}, {response_time:.3f}s)")
                    return cached_data
                else:
                    print(f"✗ Cache MISS: {cache_key} (attempt {attempt + 1}, {response_time:.3f}s)")

                    # For Redis, try to get connection info
                    try:
                        from django.core.cache import cache
                        if hasattr(cache, '_cache') and hasattr(cache._cache, 'get_client'):
                            redis_client = cache._cache.get_client()
                            connection_info = redis_client.connection_pool.connection_kwargs
                            print(f"Redis connection: {connection_info.get('host')}:{connection_info.get('port')}")

                            # Check Redis connection
                            redis_client.ping()
                            print("Redis ping successful")

                            # Check if key actually exists
                            exists = redis_client.exists(cache_key)
                            print(f"Redis key exists check: {exists}")

                    except Exception as redis_debug_error:
                        print(f"Redis debug error: {redis_debug_error}")

                    # If not last attempt, wait and retry
                    if attempt < max_retries:
                        print(f"Retrying cache get in {retry_delay}s...")
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                        continue
                    else:
                        return None

            except Exception as e:
                print(f"Cache retrieval error for {cache_key} (attempt {attempt + 1}): {e}")
                if attempt < max_retries:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                else:
                    return None

        return None

    @staticmethod
    def extend_cache_timeout(cache_keys, additional_timeout=None):
        """Extend cache timeout for failed items"""
        timeout = additional_timeout or CACHE_TIMEOUT
        for cache_key in cache_keys:
            cached_item = cache.get(cache_key)
            if cached_item:
                cache.set(cache_key, cached_item, timeout=timeout)
                print(f"Extended cache timeout for: {cache_key}")


@method_decorator(staff_member_required, name='dispatch')
class GetCachedItemView(View):
    """API endpoint to retrieve cached items"""

    def post(self, request):
        try:
            self._source_doc_cache = {}
            data = json.loads(request.body)
            company_bot_id = data.get('company_bot_id')
            media_items = data.get('items', [])
            session_id = data.get('session_id')

            results = []
            stats = {
                'total': len(media_items),
                'successful': 0,
                'failed': 0,
                'partial_success': 0,
                'timeouts': 0,
                'similarity_failures': 0
            }

            # Get current user's profile
            try:
                user_profile = Profile.objects.get(email=request.user.email)
            except Profile.DoesNotExist:
                user_profile = None

            print(f"Starting batch save for {len(media_items)} files")

            # Process each file with fault tolerance
            for i, item_data in enumerate(media_items):
                filename = item_data.get('filename', f'File_{i}')
                print(f"Processing file {i + 1}/{len(media_items)}: {filename}")

                try:
                    bypass_similarity = item_data.get('bypass_similarity', False)

                    # CRITICAL FIX: Use the file_index from item_data, not the loop index
                    # The file_index in item_data corresponds to the actual index used during caching
                    actual_file_index = item_data.get('file_index', i)
                    print(f"Using file_index {actual_file_index} for {filename} (loop index: {i})")

                    # Ensure the item_data has the correct file_index for cache lookup
                    item_data['file_index'] = actual_file_index

                    result = self.save_single_item_with_vector_db_wait_safe(
                        item_data=item_data,
                        company_bot_id=company_bot_id,
                        user_profile=user_profile,
                        session_id=session_id,
                        bypass_similarity=bypass_similarity
                    )

                    # Track statistics
                    if result['success']:
                        stats['successful'] += 1
                    else:
                        stats['failed'] += 1
                        if result.get('partial_success'):
                            stats['partial_success'] += 1
                        if result.get('error_type') in ['VECTOR_DB_TIMEOUT', 'WAIT_ERROR']:
                            stats['timeouts'] += 1
                        if result.get('error_type') == 'SIMILARITY_CHECK_FAILED':
                            stats['similarity_failures'] += 1

                    results.append(result)
                    print(
                        f"File {i + 1} result: {'✓' if result['success'] else '✗'} - {result.get('message', 'No message')}")

                except Exception as item_error:
                    print(f"Critical error processing {filename}: {item_error}")
                    stats['failed'] += 1

                    # Use the actual file_index for error reporting too
                    actual_file_index = item_data.get('file_index', i)

                    results.append({
                        'success': False,
                        'filename': filename,
                        'message': f'Critical processing error: {str(item_error)}',
                        'error_type': 'CRITICAL_ERROR',
                        'file_index': actual_file_index,
                        'file_key': item_data.get('file_key'),
                        'session_id': session_id,
                        'vector_db_saved': False
                    })

            # Preserve cache for failed files
            failed_cache_keys = []
            for r in results:
                if not r['success'] and r.get('file_key'):
                    failed_cache_keys.append(r['file_key'])
                # Also preserve cache for failed subdocuments
                if r.get('subdocument_results'):
                    for subdoc_result in r['subdocument_results']:
                        if not subdoc_result.get('success') and subdoc_result.get('cache_key'):
                            failed_cache_keys.append(subdoc_result['cache_key'])

            if failed_cache_keys:
                CacheManager.extend_cache_timeout(failed_cache_keys)

            # Generate summary message
            summary_message = self.generate_batch_summary(stats)
            print(f"Batch complete: {summary_message}")

            return JsonResponse({
                'success': True,
                'results': results,
                'stats': stats,
                'summary_message': summary_message,
                'session_id': session_id
            })

        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data'
            }, status=400)
        except Exception as batch_error:
            print(f"Batch processing error: {batch_error}")
            traceback.print_exc()
            return JsonResponse({
                'success': False,
                'error': f'Batch processing failed: {str(batch_error)}'
            }, status=500)