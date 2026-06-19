import re
import traceback
from pathlib import Path
import requests
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator
from django.http import JsonResponse
from django.views import View
from chatbot.models import Media, KeyValue, Profile, FileTypeChoices, CompanyBot, Company, FileDisplayMode
from chatbot.models.media_models import MediaImage, MediaTypeChoices
import json
import os
from django.core.cache import cache

from chatbot.utils.knowledge_service.auto_tag_utils import TagProcessor
from chatbot.utils.knowledge_service.base_task_utils import determine_media_type_from_url
from chatbot.utils.knowledge_service.cache_manager import CacheManager
from chatbot.utils.knowledge_service.duplicate_detector import DuplicateDetector
from django.core.files.base import ContentFile
import base64
from django.utils.text import slugify
from django.conf import settings

ENABLE_SIMILARITY_CHECK = getattr(settings, 'BATCH_UPLOAD_ENABLE_SIMILARITY_CHECK', False)
CACHE_TIMEOUT = getattr(settings, 'BATCH_UPLOAD_CACHE_TIMEOUT', 7200)


@method_decorator(staff_member_required, name='dispatch')
class BatchMediaSaveView(View):
    """API endpoint for saving batch media data with fault tolerance"""

    def clean_text_to_title_case(self, text):
        """Convert text to title case, handling common edge cases"""
        if not text:
            return text

        # Convert to string and strip whitespace
        text = str(text).strip()

        # Handle acronyms and special cases
        words = text.split()
        cleaned_words = []

        for word in words:
            # Keep acronyms (all caps) as is
            if word.isupper() and len(word) > 1:
                cleaned_words.append(word)
            else:
                # Convert to title case
                cleaned_words.append(word.title())

        return ' '.join(cleaned_words)


    def clean_key_for_ordered_list(self, key):
        """
        Remove leading numbers, dots, and special characters from keys
        that will be displayed in ordered lists on the frontend.
        Examples:
            "1. THEORY OF CHANGE" -> "THEORY OF CHANGE"
            "2.1 Design Philosophy" -> "Design Philosophy"
        """
        if not key:
            return key

        cleaned = re.sub(r'^\d+\.?\s*', '', key.strip())

        return cleaned

    def get_or_create_source_document_media(self, source_doc_url, parent_media, company_bot_id, markdown_content):
        """
        Download and save source document as a Media object if not already saved.
        Returns the Media object for the source document.
        """
        # Use a class-level cache to track saved source documents within this batch
        if not hasattr(self, '_source_doc_cache'):
            self._source_doc_cache = {}

        # Check if we've already processed this source document
        if source_doc_url in self._source_doc_cache:
            return self._source_doc_cache[source_doc_url]

        try:
            # Use the separated function to determine media type and filename
            media_type, filename, response = determine_media_type_from_url(source_doc_url, parent_media)

            if not media_type or not filename:
                print(f"media_type: {media_type} and filename: {filename}")
                print(f"Error creating source document media for {source_doc_url}: Media type or file name is null.")
                return None
            print(f"Final filename: {filename}, media_type: {media_type}")

            # Create Media object for source document
            source_media = Media(
                name=filename,
                media_type=media_type,
                priority=parent_media.priority,
                company_bot_id=company_bot_id,
                parent=parent_media,
                organization=parent_media.organization,
                display_mode=FileDisplayMode.PRIVATE
            )

            file_content = response.content

            # Save the main file
            if file_content:
                # Create a fresh ContentFile for the main file
                file_content_file = ContentFile(file_content)
                source_media.file.save(filename, file_content_file, save=False)
                print(f"Saved main file: {filename} ({len(file_content)} bytes)")

            # Save the markdown file if content exists
            if markdown_content:
                base_filename = os.path.splitext(filename)[0]  # Remove extension
                markdown_filename = f"Markdown_{base_filename}.md"

                # Ensure markdown content is properly encoded
                if isinstance(markdown_content, str):
                    markdown_content_bytes = markdown_content.encode('utf-8')
                else:
                    markdown_content_bytes = markdown_content

                # Create a fresh ContentFile for the markdown
                markdown_content_file = ContentFile(markdown_content_bytes)
                source_media.markdown_file.save(markdown_filename, markdown_content_file, save=False)
                print(f"Saved markdown file: {markdown_filename} ({len(markdown_content_bytes)} bytes)")

            source_media.save()

            # Add reference to original URL
            KeyValue.objects.create(
                media=source_media,
                key='ORIGINAL_URL',
                value=source_doc_url
            )

            KeyValue.objects.create(
                media=source_media,
                key='DOCUMENT_TYPE',
                value='Source Document'
            )

            # Cache the result
            self._source_doc_cache[source_doc_url] = source_media

            print(f"Created source document media: {source_media.id} - {source_media.name}")
            return source_media

        except Exception as e:
            print(f"Error creating source document media for {source_doc_url}: {e}")
            traceback.print_exc()
            return None

    def wait_for_vector_db_save_safe(self, task_id, timeout=30):
        """Enhanced waiting with better error handling"""
        import time
        from celery.result import AsyncResult

        try:
            intervals = [0.1, 0.2, 0.5, 1.0, 2.0, 3.0]
            start_time = time.time()
            attempt = 0

            while time.time() - start_time < timeout:
                try:
                    task = AsyncResult(task_id)
                    if task.ready():
                        if task.successful():
                            return {
                                'completed': True,
                                'successful': True,
                                'result': task.result,
                                'wait_time': time.time() - start_time
                            }
                        else:
                            return {
                                'completed': True,
                                'successful': False,
                                'result': f'Vector DB task failed: {task.info}',
                                'wait_time': time.time() - start_time,
                                'error_type': 'VECTOR_DB_TASK_FAILED'
                            }
                except Exception as poll_error:
                    print(f"Polling error for task {task_id}: {poll_error}")

                sleep_time = intervals[min(attempt, len(intervals) - 1)]
                time.sleep(sleep_time)
                attempt += 1

            return {
                'completed': False,
                'successful': False,
                'result': f'Vector DB save timeout after {timeout}s',
                'wait_time': timeout,
                'error_type': 'VECTOR_DB_TIMEOUT'
            }

        except Exception as wait_error:
            return {
                'completed': False,
                'successful': False,
                'result': f'Wait error: {str(wait_error)}',
                'error_type': 'WAIT_ERROR'
            }

    def save_single_item_with_vector_db_wait_safe(self, item_data, company_bot_id, user_profile, session_id,
                                                  bypass_similarity=False):
        """Save a single media item with comprehensive error handling"""
        file_key = item_data.get('file_key')
        filename = item_data.get('filename', 'Unknown')
        file_index = item_data.get('file_index')

        # if "fail" in filename.lower():
        #     print(f"Forced save failure for {filename}")
        #     raise ValueError(f"Forced save failure for {filename}")

        try:
            company_bot = CompanyBot.objects.get(id=company_bot_id)
            company_slug = None
            selected_company = None
            if item_data.get('organization_slug'):
                try:
                    selected_company = Company.objects.get(slug=item_data['organization_slug'])
                    if selected_company:
                        company_slug = selected_company.slug
                except Company.DoesNotExist:
                    pass

            extracted_text = item_data.get('extracted_text', '')

            # Step 1: Similarity check
            if ENABLE_SIMILARITY_CHECK and not bypass_similarity:
                try:
                    DuplicateDetector.check_for_duplicates(
                        extracted_text=extracted_text,
                        company_slug=company_slug,
                        trigram_threshold=0,
                        semantic_threshold=0.85,
                        trigram_exact_threshold=0.90,
                        semantic_exact_threshold=0.9
                    )
                except Exception as similarity_error:
                    return {
                        'success': False,
                        'filename': filename,
                        'message': f'Similarity check failed: {str(similarity_error)}',
                        'error_type': 'SIMILARITY_CHECK_FAILED',
                        'file_index': file_index,
                        'file_key': file_key,
                        'session_id': session_id,
                        'vector_db_saved': False
                    }

            # Step 2: Retrieve file from cache
            file_content = None
            file_name = None

            if file_key:
                cached_file = CacheManager.get_cached_item(file_key)
                if cached_file:
                    file_content = cached_file.get('content')
                    file_name = cached_file.get('name')
                else:
                    return {
                        'success': False,
                        'filename': filename,
                        'message': 'File not found in cache for saving',
                        'error_type': 'FILE_NOT_FOUND_IN_CACHE',
                        'file_index': file_index,
                        'file_key': file_key,
                        'session_id': session_id,
                        'vector_db_saved': False
                    }

            # Step 3: Create and save media
            try:
                fallback_description = f"Extracted from {filename}" if filename else ''
                description = (
                    item_data.get('summary')
                    or item_data.get('description')
                    or fallback_description
                )

                organization_instance = None
                if item_data.get('organization_slug'):
                    try:
                        organization_instance = Company.objects.get(slug=item_data['organization_slug'])
                    except Company.DoesNotExist:
                        print(f"Warning: Company with slug {item_data['organization_slug']} not found")

                media = Media(
                    name=item_data.get('title') or item_data.get('name') or filename,
                    media_type=item_data.get('media_type', FileTypeChoices.TXT.value),
                    priority=item_data.get('priority', 'P1'),
                    description=description,
                    company_bot_id=company_bot_id,
                    organization=organization_instance,
                )

                if file_content and file_name:
                    from django.core.files.base import ContentFile
                    media.file.save(file_name, ContentFile(file_content), save=False)

                # Create and save markdown file if extracted_text exists
                if extracted_text and extracted_text.strip():
                    base_name = file_name if file_name else item_data['name']
                    if base_name and '.' in base_name:
                        base_name = os.path.splitext(base_name)[0]
                    markdown_filename = f"Markdown_{base_name}.md"
                    # Ensure .md extension
                    if not markdown_filename.endswith('.md'):
                        markdown_filename = f"{markdown_filename}.md"
                    markdown_content = extracted_text.encode('utf-8')
                    media.markdown_file.save(markdown_filename, ContentFile(markdown_content), save=False)

                # Save and get the vector DB task ID
                vector_task_id = media.save()

            except Exception as media_save_error:
                return {
                    'success': False,
                    'filename': filename,
                    'message': f'Media save failed: {str(media_save_error)}',
                    'error_type': 'MEDIA_SAVE_FAILED',
                    'file_index': file_index,
                    'file_key': file_key,
                    'session_id': session_id,
                    'vector_db_saved': False
                }

            # Step 4: Process tags and key-values with prioritized company
            try:
                all_tags = []

                # Process manual tags with selected company (from dropdown priority)
                manual_tags = TagProcessor.process_tags_for_media(
                    item_data.get('manual_tags', []),
                    'manual',
                    user_profile,
                    selected_company,
                    is_manual=True
                )
                all_tags.extend(manual_tags)

                # Process auto tags with selected company (from dropdown priority)
                auto_tags = TagProcessor.process_tags_for_media(
                    item_data.get('auto_tags', []),
                    'extracted',
                    user_profile,
                    selected_company,
                    is_manual=False
                )
                all_tags.extend(auto_tags)

                if all_tags:
                    media.tags.set(all_tags)

                # Key-value pairs - ensure organization is saved
                org_found = False
                print("item_data: ", item_data)
                for kv in item_data.get('key_values', []):
                    cleaned_key = self.clean_key_for_ordered_list(kv['key'])
                    KeyValue.objects.create(
                        media=media,
                        key=cleaned_key,
                        value=kv['value']
                    )

            except Exception as tag_kv_error:
                print(f"Warning: Tag/KV processing failed for {filename}: {tag_kv_error}")

            # Step 5: Wait for vector DB save
            vector_result = {'successful': True, 'result': 'No vector task'}
            if vector_task_id:
                vector_result = self.wait_for_vector_db_save_safe(vector_task_id)

                if not vector_result['successful']:
                    print(f"Vector DB save failed for media {media.id}: {vector_result['result']}")
                    return {
                        'success': False,
                        'filename': filename,
                        'media_id': media.id,
                        'message': f"Saved to database but vector DB failed: {vector_result['result']}",
                        'error_type': vector_result.get('error_type', 'VECTOR_DB_FAILED'),
                        'file_index': file_index,
                        'file_key': file_key,
                        'session_id': session_id,
                        'vector_db_saved': False,
                        'partial_success': True,
                        'vector_task_id': vector_task_id,
                        'subdocument_results': [],
                        'image_results': []
                    }

            # Step 5.5: Process source documents if no subdocuments but source_documents exist
            source_document_results = []
            source_documents = item_data.get('source_documents', [])

            if not item_data.get('subdocument') and source_documents:
                print(f"Processing {len(source_documents)} source documents for main document without subdocuments")

                for source_doc in source_documents:
                    # source_doc is an object with 'url' and 'exact_content'
                    source_url = source_doc.get('url') if isinstance(source_doc, dict) else source_doc

                    if not source_url:
                        print(f"Skipping source document with no URL: {source_doc}")
                        continue
                    markdown_content = source_doc.get('exact_content', '')
                    try:
                        source_media = self.get_or_create_source_document_media(
                            source_url,
                            media,
                            company_bot_id,
                            markdown_content
                        )
                        if source_media:
                            source_document_results.append({
                                'success': True,
                                'source_media_id': source_media.id,
                                'source_url': source_url,
                                'title': source_media.name
                            })
                            print(f"Saved source document: {source_media.name} (ID: {source_media.id})")
                        else:
                            source_document_results.append({
                                'success': False,
                                'error': f'Failed to create source document for {source_url}',
                                'source_url': source_url
                            })
                    except Exception as source_error:
                        print(f"Error creating source document for {source_url}: {source_error}")
                        source_document_results.append({
                            'success': False,
                            'error': str(source_error),
                            'source_url': source_url
                        })

            # Step 6: Process subdocuments recursively
            subdocument_results = []
            if item_data.get('subdocument'):
                # Cache subdocuments before processing
                self._cache_subdocuments_recursive(
                    item_data['subdocument'],
                    session_id,
                    file_index,
                    ""
                )

                subdoc_results = self.process_subdocuments_recursive(
                    item_data['subdocument'],
                    media,
                    company_bot_id,
                    user_profile,
                    company_slug,
                    session_id,
                    file_index,
                    "",
                    item_data
                )
                subdocument_results.extend(subdoc_results)

            # Step 7: Process images
            image_results = []
            if item_data.get('images'):
                for index, img_data in enumerate(item_data['images']):
                    try:
                        img_result = self.save_media_image(img_data, media, index)
                        image_results.append(img_result)
                    except Exception as img_error:
                        print(f"Warning: Image save failed: {img_error}")
                        image_results.append({
                            'success': False,
                            'error': str(img_error)
                        })

            # Step 8: Success - clean up cache
            if file_key and cache.get(file_key):
                cache.delete(file_key)
                print(f"Cleaned up cache for {file_key}")

            return {
                'success': True,
                'filename': filename,
                'media_id': media.id,
                'message': 'Successfully saved',
                'file_index': file_index,
                'vector_db_saved': vector_result['successful'],
                'vector_wait_time': vector_result.get('wait_time', 0),
                'vector_task_id': vector_task_id,
                'subdocument_results': subdocument_results,
                'source_document_results': source_document_results,
                'image_results': image_results
            }

        except Exception as unexpected_error:
            print(f"Unexpected error processing {filename}: {unexpected_error}")
            traceback.print_exc()
            return {
                'success': False,
                'filename': filename,
                'message': f'Unexpected error: {str(unexpected_error)}',
                'error_type': 'UNEXPECTED_ERROR',
                'file_index': file_index,
                'file_key': file_key,
                'session_id': session_id,
                'vector_db_saved': False
            }

    def _cache_subdocuments_recursive(self, subdocuments, session_id, parent_index, parent_path):
        """Cache subdocuments recursively for retry purposes"""
        for i, subdoc in enumerate(subdocuments):
            current_path = f"{parent_path}_{i}" if parent_path else str(i)

            # Cache this subdocument with all its data
            CacheManager.cache_subdocument(subdoc, session_id, parent_index, current_path)

            # Recursively cache nested subdocuments
            if subdoc.get('subdocument'):
                self._cache_subdocuments_recursive(
                    subdoc['subdocument'],
                    session_id,
                    parent_index,
                    current_path
                )

    def process_subdocuments_recursive(self, subdocuments, parent_media, company_bot_id, user_profile,
                                       company_slug, session_id, parent_index, parent_path,
                                       source_doc):  # Add source_doc parameter
        """Recursively process subdocuments at any depth"""
        results = []

        for i, subdoc_data in enumerate(subdocuments):
            current_path = f"{parent_path}_{i}" if parent_path else str(i)
            subdoc_cache_key = CacheManager.get_cache_key(session_id, 'subdoc', f"{parent_index}_{current_path}")

            try:
                # Pass source_doc to save_subdocument
                subdoc_result = self.save_subdocument(
                    subdoc_data, parent_media, company_bot_id, user_profile, company_slug, source_doc
                )
                subdoc_result['cache_key'] = subdoc_cache_key
                subdoc_result['path'] = current_path

                # If this subdocument has nested subdocuments, process them recursively
                if subdoc_data.get('subdocument') and subdoc_result['success']:
                    subdoc_media_id = subdoc_result['subdoc_media_id']
                    subdoc_media = Media.objects.get(id=subdoc_media_id)

                    nested_results = self.process_subdocuments_recursive(
                        subdoc_data['subdocument'],
                        subdoc_media,
                        company_bot_id,
                        user_profile,
                        company_slug,
                        session_id,
                        parent_index,
                        current_path,
                        source_doc  # Pass source_doc to nested calls
                    )
                    subdoc_result['nested_subdocument_results'] = nested_results

                results.append(subdoc_result)

            except Exception as subdoc_error:
                print(f"Warning: Subdocument save failed: {subdoc_error}")
                results.append({
                    'success': False,
                    'error': str(subdoc_error),
                    'cache_key': subdoc_cache_key,
                    'path': current_path,
                    'title': subdoc_data.get('title', f'Subdocument at {current_path}')
                })

        return results

    def save_subdocument(self, subdoc_data, parent_media, company_bot_id, user_profile, company_slug, source_doc):
        """Save a subdocument as a separate Media object linked to parent"""
        try:
            source_doc_url = subdoc_data.get('source_document')
            actual_parent = parent_media

            print("=" * 50)
            print("source_doc_url: ", source_doc_url)
            print("source_doc: ", source_doc)
            print("=" * 50)

            if source_doc_url:
                source_documents = source_doc.get('source_documents', [])
                markdown_content = ''
                for source_document in source_documents:
                    if source_document.get('url') == source_doc_url:
                        print("URL MATCHED")
                        markdown_content = source_document.get('exact_content', '')
                        break

                print("found markdown content: ", markdown_content)
                # Try to get or create the source document media
                source_media = self.get_or_create_source_document_media(
                    source_doc_url,
                    parent_media,
                    company_bot_id,
                    markdown_content
                )

                if source_media:
                    # Use the source document as the parent instead
                    actual_parent = source_media
                    print(f"Using source document {source_media.id} as parent for subdocument")

            file_url = subdoc_data.get('file_url')
            if not file_url:
                raise ValueError(f"No file URL provided for subdocument")

            # Validate file format based on URL extension before downloading
            from urllib.parse import urlparse, unquote
            parsed_url = urlparse(file_url)
            path = unquote(parsed_url.path)

            # Check if URL has an extension and validate it
            if '.' in path:
                url_extension = path.rsplit('.', 1)[-1].lower()
                if url_extension and not FileTypeChoices.is_valid_extension(url_extension):
                    raise ValueError(f"Unsupported file format: .{url_extension}")

            print(f"Downloading file from URL: {file_url}")
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
            }

            try:
                response = requests.get(file_url, headers=headers, timeout=30, allow_redirects=True)
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                error_msg = f"Failed to download file from {file_url}: {str(e)}"
                print(f"Error: {error_msg}")
                raise ValueError(error_msg)

            # Additional validation based on content-type
            content_type = response.headers.get('content-type', '').lower()

            # Map content types to file extensions
            content_type_mapping = {
                'application/pdf': 'pdf',
                'application/msword': 'doc',
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
                'text/plain': 'txt',
                'text/csv': 'csv',
                'application/vnd.ms-excel': 'xls',
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
            }

            # Check if content type is supported
            content_extension = None
            for mime_type, ext in content_type_mapping.items():
                if mime_type in content_type:
                    content_extension = ext
                    break

            if content_extension and not FileTypeChoices.is_valid_extension(content_extension):
                raise ValueError(f"Unsupported content type: {content_type}")

            # Determine filename from URL or content-disposition
            filename = None
            content_disposition = response.headers.get('content-disposition')
            if content_disposition:
                import re
                matches = re.findall('filename="?([^"]+)"?', content_disposition)
                if matches:
                    filename = matches[0]
                    # Validate filename extension
                    if '.' in filename:
                        file_ext = filename.rsplit('.', 1)[-1].lower()
                        if not FileTypeChoices.is_valid_extension(file_ext):
                            raise ValueError(f"Unsupported file format in download: .{file_ext}")

            if not filename:
                # Extract from URL
                from urllib.parse import urlparse, unquote
                parsed_url = urlparse(file_url)
                path = parsed_url.path
                filename = os.path.basename(unquote(path))

                # For Google Docs/Drive, create appropriate filename based on media type
                if 'docs.google.com' in file_url or 'drive.google.com' in file_url:
                    base_title = subdoc_data.get('title', 'Document')
                    media_type = subdoc_data.get('media_type', FileTypeChoices.TXT.value)

                    # Get extension from media type using the enum's mapping
                    extension_mapping = FileTypeChoices.get_extension_mapping()
                    extension = extension_mapping.get(media_type, '.txt')

                    filename = f"{slugify(base_title, allow_unicode=True)}{extension}"

                # Ensure filename has an extension
                if not os.path.splitext(filename)[1]:
                    # Add extension based on media type using the enum's mapping
                    media_type = subdoc_data.get('media_type', FileTypeChoices.TXT.value)
                    extension_mapping = FileTypeChoices.get_extension_mapping()
                    extension = extension_mapping.get(media_type, '.txt')
                    filename += extension

            # Use filename (without extension) as the subdocument title
            filename_without_ext = os.path.splitext(filename)[0] if filename else ""

            if filename_without_ext and len(filename_without_ext.strip()) > 0:
                subdoc_title = filename_without_ext
                print(f"Using filename as title: {subdoc_title}")
            else:
                llm_title = subdoc_data.get('title', '').strip()
                if llm_title and len(llm_title) > 0:
                    subdoc_title = llm_title
                    print(f"Using LLM-extracted title: {subdoc_title}")
                else:
                    # Final fallback - create a descriptive title
                    subdoc_title = f"Document from {Path(urlparse(file_url).path).name or 'linked document'}"
                    print(f"Using fallback title: {subdoc_title}")

            print(f"Saving subdocument with title: {subdoc_title} (from filename: {filename})")

            # Check for forced failure
            # for kv in subdoc_data.get('key_values', []):
            #     if "fail" in kv.get('value', '').lower():
            #         print(f"Forced subdoc extraction failure for {subdoc_title}")
            #         raise ValueError(f"Forced subdoc extraction failure for {subdoc_title}")

            # Get file content
            file_content = response.content
            if not file_content:
                raise ValueError(f"Downloaded file is empty for URL: {file_url}")

            # IMPORTANT FIX: Get organization from subdocument data FIRST
            subdoc_org = subdoc_data.get('organization', '')

            # If subdocument has no organization, try to get from key-values
            if not subdoc_org:
                for kv in subdoc_data.get('key_values', []):
                    if kv.get('key') == 'ORGANIZATION' and kv.get('value'):
                        subdoc_org = kv.get('value')
                        break

            # If still no organization, get from parent media's key-values
            if not subdoc_org:
                parent_kvs = KeyValue.objects.filter(media=parent_media, key='ORGANIZATION')
                if parent_kvs.exists():
                    subdoc_org = parent_kvs.first().value

            # Only use company name as last resort
            if not subdoc_org and user_profile and user_profile.company:
                subdoc_org = user_profile.company.name

            subdoc_org = self.clean_text_to_title_case(subdoc_org)
            print(f"Subdocument organization resolved to: {subdoc_org}")
            organization_instance = None
            if subdoc_data.get('organization_slug'):
                try:
                    organization_instance = Company.objects.get(slug=subdoc_data['organization_slug'])
                except Company.DoesNotExist:
                    print(f"Warning: Company with slug {subdoc_data['organization_slug']} not found")

            # Get extracted_text for subdocument
            subdoc_extracted_text = subdoc_data.get('extracted_text', '')

            # Create subdocument media
            subdoc_media = Media(
                name=subdoc_data.get('title') or subdoc_title or filename,
                media_type=subdoc_data.get('media_type', FileTypeChoices.TXT.value),
                priority=parent_media.priority,
                description=subdoc_data.get('summary') or subdoc_data.get('description') or '',
                company_bot_id=company_bot_id,
                parent=actual_parent,
                organization=organization_instance,
                display_mode=subdoc_data.get('display_mode', FileDisplayMode.VISIBLE),
            )

            # Save the file content - use the original filename
            try:
                subdoc_media.file.save(filename, ContentFile(file_content), save=False)
                print(f"Successfully saved file: {filename}")
            except Exception as e:
                error_msg = f"Failed to save file content for subdocument: {str(e)}"
                print(f"Error: {error_msg}")
                raise ValueError(error_msg)

            # Create and save markdown file if extracted_text exists
            if subdoc_extracted_text and subdoc_extracted_text.strip():
                base_filename = os.path.splitext(filename)[0]
                markdown_filename = f"Markdown_{base_filename}.md"

                # Ensure .md extension
                if not markdown_filename.endswith('.md'):
                    markdown_filename = f"{markdown_filename}.md"
                markdown_content = subdoc_extracted_text.encode('utf-8')
                subdoc_media.markdown_file.save(markdown_filename, ContentFile(markdown_content), save=False)

            # Save the media object
            subdoc_media.save()

            selected_company = None
            if subdoc_data.get('organization_slug'):
                try:
                    selected_company = Company.objects.get(slug=subdoc_data['organization_slug'])
                except Company.DoesNotExist:
                    pass

            if not selected_company and user_profile:
                selected_company = user_profile.company

            if not selected_company:
                company_bot = CompanyBot.objects.get(id=company_bot_id)
                selected_company = company_bot.company

            all_tags = []

            manual_tags = subdoc_data.get('manual_tags', [])
            if manual_tags:
                manual_tag_objs = TagProcessor.process_tags_for_media(
                    manual_tags,
                    'manual',
                    user_profile,
                    selected_company,
                    is_manual=True
                )
                all_tags.extend(manual_tag_objs)

            auto_tags = subdoc_data.get('auto_tags', [])
            if auto_tags:
                auto_tag_objs = TagProcessor.process_tags_for_media(
                    auto_tags,
                    'extracted',
                    user_profile,
                    selected_company,
                    is_manual=False
                )
                all_tags.extend(auto_tag_objs)

            if all_tags:
                subdoc_media.tags.set(all_tags)

            # Key-value pairs - handle organization specially
            for kv in subdoc_data.get('key_values', []):
                cleaned_key = self.clean_key_for_ordered_list(kv['key'])
                if cleaned_key == 'DOCUMENT_TYPE':
                    doc_type_value = kv['value']
                    if isinstance(doc_type_value, dict):
                        actual_value = doc_type_value.get('type', '')
                        actual_value = actual_value.title() if actual_value else ''
                    else:
                        actual_value = doc_type_value.title() if doc_type_value else ''

                    KeyValue.objects.create(
                        media=subdoc_media,
                        key='DOCUMENT_TYPE',
                        value=actual_value
                    )
                else:
                    KeyValue.objects.create(
                        media=subdoc_media,
                        key=cleaned_key,
                        value=kv['value']
                    )

            print(f"Saved {len(subdoc_data.get('key_values', []))} key-values for subdoc: {subdoc_title}")

            # Process subdocument images
            if subdoc_data.get('images'):
                for index, img_data in enumerate(subdoc_data['images']):
                    self.save_media_image(img_data, subdoc_media, index)

            return {
                'success': True,
                'subdoc_media_id': subdoc_media.id,
                'title': subdoc_media.name
            }

        except Exception as e:
            print(f"Error saving subdocument: {e}")
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e),
                'title': subdoc_data.get('title', 'Unknown subdocument')
            }

    def save_media_image(self, img_data, media, index):
        """Save image associated with media"""
        try:
            if img_data.get('base64'):
                try:
                    # Extract image format from base64 string
                    base64_str = img_data['base64']
                    if base64_str.startswith('data:'):
                        mime_start = base64_str.find('image/') + 6
                        mime_end = base64_str.find(';', mime_start)
                        image_format = base64_str[mime_start:mime_end]
                        base64_data = base64_str.split(',')[1]
                    else:
                        image_format = img_data.get('format', 'png')
                        base64_data = base64_str

                    # Decode base64 to bytes
                    image_bytes = base64.b64decode(base64_data)
                    base_name, _ = os.path.splitext(media.name)
                    safe_base = slugify(base_name, allow_unicode=True)
                    file_name = f"img_{safe_base}_{index}.{image_format}"

                    media_image = MediaImage(
                        name=file_name,
                        media=media,
                        page=img_data.get('page'),
                        index=img_data.get('index', index),
                        width=img_data.get('width'),
                        height=img_data.get('height'),
                        base64_str=img_data.get('base64', '')
                    )

                    # Create file
                    media_image.file.save(file_name, ContentFile(image_bytes), save=False)

                    # Set media type
                    if image_format.lower() in ['jpg', 'jpeg']:
                        media_image.media_type = MediaTypeChoices.JPEG
                    elif image_format.lower() == 'png':
                        media_image.media_type = MediaTypeChoices.PNG
                    elif image_format.lower() == 'svg':
                        media_image.media_type = MediaTypeChoices.SVG
                    elif image_format.lower() == 'webp':
                        media_image.media_type = MediaTypeChoices.WEBP

                    media_image.save()

                    return {
                        'success': True,
                        'image_id': media_image.id,
                        'page': media_image.page
                    }

                except Exception as e:
                    print(f"Error processing image base64: {e}")
                    return {
                        'success': False,
                        'error': str(e)
                    }

        except Exception as e:
            print(f"Error saving media image: {e}")
            return {
                'success': False,
                'error': str(e)
            }

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
                    results.append({
                        'success': False,
                        'filename': filename,
                        'message': f'Critical processing error: {str(item_error)}',
                        'error_type': 'CRITICAL_ERROR',
                        'file_index': item_data.get('file_index', i),
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

    def generate_batch_summary(self, stats):
        """Generate human-readable batch summary"""
        total = stats['total']
        successful = stats['successful']
        failed = stats['failed']

        if successful == total:
            return f"All {total} files processed successfully!"
        elif successful == 0:
            return f"All {total} files failed to process."
        else:
            message_parts = [f"{successful}/{total} files successful"]
            if failed > 0:
                message_parts.append(f"{failed} failed")
            if stats['timeouts'] > 0:
                message_parts.append(f"{stats['timeouts']} timed out")
            if stats['similarity_failures'] > 0:
                message_parts.append(f"{stats['similarity_failures']} similarity check failures")
            if stats['partial_success'] > 0:
                message_parts.append(f"{stats['partial_success']} partial successes")

            return ", ".join(message_parts) + "."


@method_decorator(staff_member_required, name='dispatch')
class BatchMediaRetrySaveView(View):
    """API endpoint for retrying save of a single media item"""

    def post(self, request):
        try:
            data = json.loads(request.body)
            item_data = data.get('item_data')
            company_bot_id = data.get('company_bot_id')
            session_id = data.get('session_id')
            bypass_similarity = data.get('bypass_similarity', False)
            is_subdocument = data.get('is_subdocument', False)
            parent_media_id = data.get('parent_media_id')

            # Get current user's profile
            try:
                user_profile = Profile.objects.get(email=request.user.email)
            except Profile.DoesNotExist:
                user_profile = None

            if is_subdocument and parent_media_id:
                # Retry subdocument save
                try:
                    parent_media = Media.objects.get(id=parent_media_id)
                    company_bot = CompanyBot.objects.get(id=company_bot_id)
                    company_slug = company_bot.company.slug

                    save_view = BatchMediaSaveView()
                    result = save_view.save_subdocument(
                        subdoc_data=item_data,
                        parent_media=parent_media,
                        company_bot_id=company_bot_id,
                        user_profile=user_profile,
                        company_slug=company_slug,
                        source_doc=data.get('source_document', {})
                    )

                    return JsonResponse({
                        'success': True,
                        'result': result
                    })
                except Exception as e:
                    print(f"Subdocument retry error: {e}")
                    traceback.print_exc()
                    return JsonResponse({
                        'success': False,
                        'error': str(e)
                    }, status=400)
            else:
                # Retry main document save
                save_view = BatchMediaSaveView()
                result = save_view.save_single_item_with_vector_db_wait_safe(
                    item_data=item_data,
                    company_bot_id=company_bot_id,
                    user_profile=user_profile,
                    session_id=session_id,
                    bypass_similarity=bypass_similarity
                )

                return JsonResponse({
                    'success': True,
                    'result': result
                })

        except Exception as e:
            print(f"Unexpected error in retry save: {e}")
            traceback.print_exc()
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)