import json
import traceback
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from chatbot.models import Media, KeyValue, CompanyBot, Company, FileTypeChoices, FileDisplayMode
from shikshalokam.models.enums import PriorityChoices
from django.core.files.base import ContentFile


@method_decorator(csrf_exempt, name='dispatch')
class DocumentUploadView(View):
    """
    API endpoint for uploading documents to the knowledge base
    POST /api/v1/documents
    """

    def post(self, request):
        """
        Handle document upload with multipart/form-data
        
        Required Fields:
        - file: File to upload (PDF, TXT, DOCX, MD, etc.)
        
        Optional Fields:
        - priority: string (default: "P1") - "P1", "P2", "P3"
        - source_id: string - External source identifier
        - company_id: string - Company slug/identifier
        - title: string - Document title
        - summary: string - Document summary
        - metadata: string (JSON) - Additional metadata as JSON string
        - tags: string (JSON array OR CSV) - Tags as JSON array or comma-separated
        """
        try:
            # Validate file upload
            if 'file' not in request.FILES:
                return JsonResponse({
                    'success': False,
                    'error': 'No file provided',
                    'message': 'File is required'
                }, status=400)

            uploaded_file = request.FILES['file']
            
            # Validate file type
            file_extension = uploaded_file.name.split('.')[-1].lower() if '.' in uploaded_file.name else None
            if file_extension and not FileTypeChoices.is_valid_extension(file_extension):
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid file type',
                    'message': f'File type .{file_extension} is not supported'
                }, status=400)

            # Extract optional fields
            priority = request.POST.get('priority', PriorityChoices.P1)
            source_id = request.POST.get('source_id', None)
            company_id = request.POST.get('company_id', None)
            title = request.POST.get('title', None)
            summary = request.POST.get('summary', None)
            metadata_str = request.POST.get('metadata', None)
            tags_str = request.POST.get('tags', None)

            # Validate priority
            valid_priorities = [choice[0] for choice in PriorityChoices.choices]
            if priority not in valid_priorities:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid priority',
                    'message': f'Priority must be one of: {", ".join(valid_priorities)}'
                }, status=400)

            # Parse metadata (JSON string)
            metadata = {}
            if metadata_str:
                try:
                    metadata = json.loads(metadata_str)
                    if not isinstance(metadata, dict):
                        return JsonResponse({
                            'success': False,
                            'error': 'Invalid metadata format',
                            'message': 'Metadata must be a valid JSON object'
                        }, status=400)
                except json.JSONDecodeError as e:
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid metadata JSON',
                        'message': f'Failed to parse metadata: {str(e)}'
                    }, status=400)

            # Parse tags (JSON array OR CSV)
            tags = []
            if tags_str:
                try:
                    # Try parsing as JSON array first
                    parsed_tags = json.loads(tags_str)
                    if isinstance(parsed_tags, list):
                        tags = [str(tag).strip() for tag in parsed_tags if tag]
                    else:
                        return JsonResponse({
                            'success': False,
                            'error': 'Invalid tags format',
                            'message': 'Tags must be a JSON array or comma-separated string'
                        }, status=400)
                except json.JSONDecodeError:
                    # Fallback to CSV parsing
                    tags = [tag.strip() for tag in tags_str.split(',') if tag.strip()]

            # Get or validate company
            company = None
            if company_id:
                try:
                    company = Company.objects.get(slug=company_id)
                except Company.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'error': 'Company not found',
                        'message': f'Company with ID "{company_id}" does not exist'
                    }, status=404)

            # Get default company bot (you may need to adjust this logic based on your requirements)
            # For now, we'll get the first available company bot for the company
            company_bot = None
            if company:
                company_bot = CompanyBot.objects.filter(company=company).first()
            
            if not company_bot:
                # Fallback to any available company bot
                company_bot = CompanyBot.objects.first()
                
            if not company_bot:
                return JsonResponse({
                    'success': False,
                    'error': 'No company bot available',
                    'message': 'Please configure a company bot first'
                }, status=400)

            # Determine media type from file extension
            media_type = FileTypeChoices.TXT  # default
            if file_extension:
                mime_type = FileTypeChoices.get_mime_from_extension(file_extension)
                if mime_type:
                    media_type = mime_type

            # Use title or filename as the media name
            media_name = title if title else uploaded_file.name

            # Create Media object
            media = Media(
                name=media_name,
                media_type=media_type,
                priority=priority,
                description=summary,
                company_bot=company_bot,
                organization=company,
                display_mode=FileDisplayMode.VISIBLE
            )

            # Save the uploaded file
            file_content = uploaded_file.read()
            media.file.save(uploaded_file.name, ContentFile(file_content), save=False)

            # Save media and trigger vector DB save
            company_slug = company.slug if company else (company_bot.company.slug if company_bot.company else None)
            vector_task_id = media.save(company_slug=company_slug)

            # Save source_id as key-value if provided
            if source_id:
                KeyValue.objects.create(
                    media=media,
                    key='SOURCE_ID',
                    value=source_id
                )

            # Save title as key-value if provided
            if title:
                KeyValue.objects.create(
                    media=media,
                    key='TITLE',
                    value=title
                )

            # Save metadata as key-value pairs
            for key, value in metadata.items():
                KeyValue.objects.create(
                    media=media,
                    key=key.upper(),
                    value=str(value)
                )

            # Save tags
            if tags:
                from chatbot.models import Tag
                tag_objects = []
                for tag_name in tags:
                    tag, created = Tag.objects.get_or_create(
                        name=tag_name,
                        defaults={'company': company or company_bot.company}
                    )
                    tag_objects.append(tag)
                media.tags.set(tag_objects)

            # Prepare response
            response_data = {
                'success': True,
                'message': 'Document uploaded successfully',
                'data': {
                    'media_id': media.id,
                    'name': media.name,
                    'media_type': media.media_type,
                    'priority': media.priority,
                    'source_id': source_id,
                    'company_id': company_slug,
                    'title': title,
                    'summary': summary,
                    'tags': tags,
                    'metadata': metadata,
                    'vector_task_id': vector_task_id,
                    'created_at': media.created_at.isoformat() if media.created_at else None,
                    'file_url': media.get_s3_url() if hasattr(media, 'get_s3_url') else None
                }
            }

            return JsonResponse(response_data, status=201)

        except Exception as e:
            print(f"Error uploading document: {e}")
            traceback.print_exc()
            return JsonResponse({
                'success': False,
                'error': 'Internal server error',
                'message': str(e)
            }, status=500)

    def get(self, request):
        """Return API documentation"""
        return JsonResponse({
            'endpoint': 'POST /api/v1/documents',
            'description': 'Upload a document to the knowledge base',
            'request_type': 'multipart/form-data',
            'required_fields': {
                'file': {
                    'type': 'File',
                    'description': 'File to upload (PDF, TXT, DOCX, MD, etc.)'
                }
            },
            'optional_fields': {
                'priority': {
                    'type': 'string',
                    'default': 'P1',
                    'format': 'Plain text',
                    'example': 'P1, P2, P3'
                },
                'source_id': {
                    'type': 'string',
                    'default': None,
                    'format': 'Plain text',
                    'example': 'doc_12345'
                },
                'company_id': {
                    'type': 'string',
                    'default': None,
                    'format': 'Plain text',
                    'example': 'company_abc'
                },
                'title': {
                    'type': 'string',
                    'default': None,
                    'format': 'Plain text',
                    'example': 'Q4 Financial Report'
                },
                'summary': {
                    'type': 'string',
                    'default': None,
                    'format': 'Plain text',
                    'example': 'Summary of Q4 results'
                },
                'metadata': {
                    'type': 'string',
                    'default': None,
                    'format': 'JSON string',
                    'example': '{"author": "John", "department": "Finance"}'
                },
                'tags': {
                    'type': 'string',
                    'default': None,
                    'format': 'JSON array OR CSV',
                    'example': '["finance", "report"] OR "finance, report"'
                }
            },
            'example_curl': '''
curl -X POST "http://your-api.com/api/v1/documents" \\
  -F "file=@/path/to/document.pdf" \\
  -F "priority=P1" \\
  -F "source_id=doc_12345" \\
  -F "company_id=company_abc" \\
  -F "title=Q4 Financial Report" \\
  -F "summary=Quarterly financial summary" \\
  -F 'metadata={"author": "John", "department": "Finance"}' \\
  -F 'tags=["finance", "report", "Q4"]'
            '''
        })
