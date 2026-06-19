import logging
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator
from django.http import JsonResponse
from django.views import View
from chatbot.models import Tag, Profile, TagSourceChoices, TagChoices
import json
from chatbot.utils.knowledge_service.auto_tag_utils import TagProcessor
from chatbot.utils.knowledge_service.base_task_utils import determine_media_type_from_url
from chatbot.utils.knowledge_service.media_utils import get_media_type_from_ai_data, build_key_values

logger = logging.getLogger('django')


@method_decorator(staff_member_required, name='dispatch')
class BatchMediaTaskStatusView(View):
    """API endpoint for checking Celery task status and updating data when complete"""

    def post(self, request):
        try:
            from celery.result import AsyncResult

            # Add logging for debugging
            print(f"BatchMediaTaskStatusView - Request received")
            print(f"Request body: {request.body[:500]}")  # First 500 chars

            try:
                data = json.loads(request.body)
            except json.JSONDecodeError as e:
                print(f"JSON decode error: {e}")
                return JsonResponse({
                    'success': False,
                    'error': f'Invalid JSON: {str(e)}'
                }, status=400)

            task_ids = data.get('task_ids', [])
            print(f"Checking status for task IDs: {task_ids}")

            results = {}
            for task_id in task_ids:
                try:
                    task = AsyncResult(task_id)
                    print(f"Task {task_id} - Status: {task.status}, Ready: {task.ready()}")

                    if task.ready():
                        if task.successful():
                            try:
                                ai_data = task.result
                                print(f"Task {task_id} successful, processing result")
                                print(f"Result type: {type(ai_data)}")

                                # Check if result is None
                                if ai_data is None:
                                    print(f"Warning: Task {task_id} returned None")
                                    results[task_id] = {
                                        'status': 'ERROR',  # CHANGED FROM SUCCESS TO ERROR
                                        'error': 'AI processing returned no data'
                                    }
                                else:
                                    processed_data = self.process_ai_extracted_data(ai_data)
                                    results[task_id] = {
                                        'status': 'SUCCESS',
                                        'result': processed_data
                                    }
                            except Exception as process_error:
                                print(f"Error processing task result for {task_id}: {process_error}")
                                import traceback
                                traceback.print_exc()
                                results[task_id] = {
                                    'status': 'ERROR',  # ENSURE THIS IS ERROR NOT FAILURE
                                    'error': str(process_error)
                                }
                        else:
                            error_info = str(task.info) if task.info else 'Unknown error'
                            print(f"Task {task_id} failed: {error_info}")
                            results[task_id] = {
                                'status': 'FAILURE',
                                'error': error_info
                            }
                    else:
                        results[task_id] = {
                            'status': 'PENDING'
                        }
                except Exception as task_error:
                    print(f"Error checking task {task_id}: {task_error}")
                    import traceback
                    traceback.print_exc()
                    results[task_id] = {
                        'status': 'ERROR',
                        'error': str(task_error)
                    }

            print(f"Returning results for {len(results)} tasks")
            return JsonResponse({
                'success': True,
                'results': results
            })

        except Exception as e:
            print(f"Unexpected error in BatchMediaTaskStatusView: {e}")
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)


    def is_excel_file(self, url_or_filename, media_type=None):
        """Check if the file is an Excel file (.xlsx or .xls) by extension or media type"""
        # Check by media type first (for Google Sheets and other sources)
        if media_type:
            excel_media_types = [
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  # .xlsx
                'application/vnd.ms-excel',  # .xls
                'application/vnd.google-apps.spreadsheet'  # Google Sheets
            ]
            if media_type in excel_media_types:
                return True

        # Check by file extension
        if url_or_filename:
            url_or_filename_lower = str(url_or_filename).lower()
            if url_or_filename_lower.endswith('.xlsx') or url_or_filename_lower.endswith('.xls'):
                return True

        return False

    def get_main_doc_media_type(self, ai_data):
        if 'media_type' in ai_data and ai_data['media_type']:
            return ai_data['media_type']

    def validate_tags_against_database(self, tags, company=None):
        """
        Filter tags to only include those that exist in the database.
        """
        if not tags:
            return []

        # Extract tag texts
        tag_texts = []
        for tag in tags:
            if isinstance(tag, dict) and 'text' in tag:
                tag_texts.append(tag['text'])
            elif isinstance(tag, str):
                tag_texts.append(tag)

        # Query database for existing tags
        query = Tag.objects.filter(
            name__in=tag_texts,
            source_type__in=[TagSourceChoices.MANUAL, TagSourceChoices.AI_EXTRACTED],
            status=TagChoices.APPROVED
        )

        # if company:
        #     query = query.filter(company=company)

        # Get set of valid tag names
        valid_tag_names = set(query.values_list('name', flat=True))

        # Filter original tags list
        validated_tags = []
        for tag in tags:
            tag_text = tag.get('text') if isinstance(tag, dict) else tag
            if tag_text in valid_tag_names:
                validated_tags.append(tag)

        return validated_tags

    def process_ai_extracted_data(self, ai_data, original_filename=None):
        """Process AI extracted data into format expected by frontend"""
        if not ai_data:
            return {
                'auto_tags': [],
                'enhanced_data': None
            }

        # *** SIMPLIFIED: Check if AI data is not a dictionary ***
        if not isinstance(ai_data, dict):
            error_msg = "AI processing failed - unable to extract structured data from document"
            raise ValueError(error_msg)

        # Check for explicit error from AI processing
        if ai_data.get('error') or ai_data.get('error_type'):
            error_msg = ai_data.get('error', 'AI processing failed with unknown error')
            print(f"AI extraction failed: {error_msg}")
            raise ValueError(f"{error_msg}")

        def repair_structured_content(structured_content):
            """Repair and validate structured content JSON"""
            if not structured_content:
                return {}

            # If it's already a dict, return as-is
            if isinstance(structured_content, dict):
                return structured_content

            # If it's a string, try to parse and repair
            if isinstance(structured_content, str):
                import json
                try:
                    # Try direct JSON parsing first
                    return json.loads(structured_content)
                except json.JSONDecodeError:
                    try:
                        # Use JSON repair if available
                        import json_repair
                        return json_repair.repair_json(structured_content)
                    except (ImportError, Exception) as e:
                        print(f"JSON repair failed for structured_content: {e}")
                        # Fallback: try to create a basic structure
                        try:
                            # Simple repair attempts
                            repaired = structured_content.strip()
                            if not repaired.startswith('{'):
                                repaired = '{' + repaired
                            if not repaired.endswith('}'):
                                repaired = repaired + '}'
                            return json.loads(repaired)
                        except:
                            print(f"All JSON repair attempts failed, returning empty dict")
                            return {}

            # Fallback for other types
            return {}

        # Get user's company
        company = None
        company_name = None
        if hasattr(self, 'request') and self.request.user.is_authenticated:
            try:
                user_profile = Profile.objects.get(email=self.request.user.email)
                if user_profile.company:
                    company = user_profile.company
                    company_name = company.name
            except Profile.DoesNotExist:
                pass


        def process_subdocument(subdoc_data):
            """Recursively process subdocument data"""
            if not isinstance(subdoc_data, dict):
                logger.warning(f"Subdocument data is not a dictionary: {type(subdoc_data)}")
                return None

            # Set organization to company name if empty
            if not subdoc_data.get('organization'):
                subdoc_data['organization'] = company_name or ''

            raw_tags = TagProcessor.extract_tag_texts(subdoc_data.get('tags', []))

            tag_dicts = [{'text': tag, 'source': 'extracted'} for tag in raw_tags]
            validated_tags = self.validate_tags_against_database(tag_dicts, company)

            validated_tag_texts = [tag['text'] for tag in validated_tags]
            document_type = subdoc_data.get('document_type', '')
            if isinstance(document_type, dict):
                document_type_value = document_type.get('type', '')
                document_type_value = document_type_value.title() if document_type_value else ''
            else:
                document_type_value = document_type.title() if document_type else ''

            key_values, array_metadata = build_key_values(subdoc_data)
            subdoc_data['array_fields_metadata'] = array_metadata

            # Check if subdocument is Excel file - only set extracted_text for Excel files
            subdoc_file_url = subdoc_data.get('file_url', '')
            subdoc_urls = subdoc_data.get('url', [])
            subdoc_url = subdoc_urls[0] if subdoc_urls else ''
            subdoc_media_type = subdoc_data.get('media_type')
            is_subdoc_excel = self.is_excel_file(subdoc_file_url, subdoc_media_type) or self.is_excel_file(subdoc_url, subdoc_media_type)

            processed = {
                'title': subdoc_data.get('title', ''),
                'summary': subdoc_data.get('summary', ''),
                'description': subdoc_data.get('summary', ''),
                'exact_content': subdoc_data.get('exact_content', ''),
                'extracted_text': subdoc_data.get('exact_content', '') if is_subdoc_excel else '',
                'organization': subdoc_data.get('organization', company_name or ''),
                'geography': to_title_case(subdoc_data.get('geography', '')),
                'document_type': document_type_value,
                'key_entities': subdoc_data.get('key_entities', []),
                'url': subdoc_data.get('url', []),
                'file_url': subdoc_data.get('file_url', ''),
                'source_document': subdoc_data.get('source_document', ''),
                'auto_tags': validated_tag_texts,
                'manual_tags': [],
                'key_values': key_values,
                'images': subdoc_data.get('images', []),
                'media_type': subdoc_data.get(
                    'media_type', get_media_type_from_ai_data(subdoc_data.get('document_type', ''))
                ),
                'error': subdoc_data.get('error')
            }

            # Recursively process nested subdocuments
            if subdoc_data.get('subdocument') and isinstance(subdoc_data['subdocument'], list):
                processed['subdocument'] = []
                for nested_subdoc in subdoc_data['subdocument']:
                    nested_processed = process_subdocument(nested_subdoc)
                    if nested_processed:
                        processed['subdocument'].append(nested_processed)

            return processed

        document_type = ai_data.get('document_type', '')
        if isinstance(document_type, dict):
            document_type_value = document_type.get('type', '')
            document_type_value = document_type_value.title() if document_type_value else ''
        else:
            document_type_value = document_type.title() if document_type else ''

        def to_title_case(text):
            if not text:
                return text
            return str(text).strip().title()

        is_template = document_type_value.lower() == 'template'
        original_filename = ai_data.get('original_filename')
        repaired_structured_content = repair_structured_content(ai_data.get('structured_content'))

        # Get media type first to check if it's Excel
        media_type_value = self.get_main_doc_media_type(ai_data)

        # Check if main document is Excel file - only set extracted_text for Excel files
        main_urls = ai_data.get('url', [])
        main_url = main_urls[0] if main_urls else ''
        is_main_excel = self.is_excel_file(original_filename, media_type_value) or self.is_excel_file(main_url, media_type_value)
        print("AI DATA ------->", ai_data)
        main_data = {
            'title': original_filename if (original_filename and not is_template) else ai_data.get('title', ''),
            'summary': ai_data.get('summary', ''),
            'extracted_text': ai_data.get('exact_content', '') if is_main_excel else '',
            'organization': ai_data.get('organization', '') or company_name or '',
            'geography': to_title_case(ai_data.get('geography', '')),
            'document_type': document_type_value,
            'key_entities': ai_data.get('key_entities', []),
            'structured_content': repaired_structured_content,
            'url': ai_data.get('url', []),
            'source_documents': ai_data.get('source_document', []),
        }

        # Process main tags
        auto_tags = TagProcessor.process_tags(ai_data.get('tags', []))
        auto_tags = self.validate_tags_against_database(auto_tags, company)

        # Build enhanced key-values for main document
        enhanced_key_values, array_fields_metadata = build_key_values(main_data)
        main_data['array_fields_metadata'] = array_fields_metadata

        # Process subdocuments recursively
        subdocuments = []
        if ai_data.get('subdocument') and isinstance(ai_data['subdocument'], list):
            for subdoc in ai_data['subdocument']:
                processed_subdoc = process_subdocument(subdoc)
                if processed_subdoc:
                    subdocuments.append(processed_subdoc)

        # Process failed links
        failed_links = []
        if ai_data.get('failed_links') and isinstance(ai_data['failed_links'], list):
            for failed in ai_data['failed_links']:
                processed_failed = process_subdocument(failed)
                if processed_failed:
                    failed_links.append(processed_failed)

        # Process images
        images = ai_data.get('images', []) if isinstance(ai_data.get('images'), list) else []
        print("ai_data: ", ai_data)
        data = {
            'auto_tags': auto_tags,
            'enhanced_data': {
                'description': main_data['summary'],
                'extracted_text': main_data['extracted_text'],
                'organization': main_data['organization'],
                'enhanced_key_values': enhanced_key_values,
                'subdocument': subdocuments,
                'failed_links': failed_links,
                'images': images,
                'structured_content': repaired_structured_content,
                'url': ai_data.get('url', []),
                'source_documents': ai_data.get('source_document', []),
            }
        }

        if media_type_value:
            data.get('enhanced_data', {})['media_type'] = media_type_value

        print("data: ", data)
        return data


@method_decorator(staff_member_required, name='dispatch')
class VectorDBTaskStatusView(View):
    """Check status of vector DB save task"""

    def post(self, request):
        try:
            from celery.result import AsyncResult
            data = json.loads(request.body)
            task_id = data.get('task_id')

            if not task_id:
                return JsonResponse({'success': False, 'error': 'No task_id provided'})

            task = AsyncResult(task_id)

            return JsonResponse({
                'success': True,
                'status': task.status,
                'ready': task.ready(),
                'successful': task.successful() if task.ready() else None,
                'result': task.result if task.ready() else None
            })

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
