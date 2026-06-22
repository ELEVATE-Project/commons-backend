from rest_framework import serializers
from django.db.models import Q
from chatbot.models import Media, KeyValue, Tag, FileDisplayMode, FileTypeChoices
from chatbot.models.media_models import MediaImage
import ast
import json
import os

media_base_url = os.getenv("MEDIA_BASE_URL")

class S3UrlMixin:
    def resolve_s3_url(self, obj):
        linked_file = obj.subdocuments.filter(
            key_values__key__iregex=r'^document[ _]type$',
            key_values__value__icontains="source document"
        ).first()

        if linked_file:
            return linked_file.get_s3_url()

        if obj.parent:
            parent_kv = obj.parent.key_values.filter(key__iregex=r'^document[ _]type$').first()
            parent_doc_type = parent_kv.value.lower() if parent_kv and parent_kv.value else None
            if parent_doc_type in ["template", "source document"]:
                return obj.get_s3_url()

        return obj.get_s3_url()

    def resolve_thumbnail_url(self, obj):
        linked_file = obj.subdocuments.filter(
            key_values__key__iregex=r'^document[ _]type$',
            key_values__value__icontains="source document"
        ).first()

        if linked_file:
            if linked_file.thumbnail:
                return linked_file.get_thumbnail_s3_url()
            return None

        if obj.parent:
            parent_kv = obj.parent.key_values.filter(key__iregex=r'^document[ _]type$').first()
            parent_doc_type = parent_kv.value.lower() if parent_kv and parent_kv.value else None
            if parent_doc_type in ["template", "source document"]:
                if obj.thumbnail:
                    return obj.get_thumbnail_s3_url()
                return None

        if obj.thumbnail:
            return obj.get_thumbnail_s3_url()
        return None


class KeyValueSerializer(serializers.ModelSerializer):
    value = serializers.SerializerMethodField()

    class Meta:
        model = KeyValue
        fields = ['id', 'key', 'value']

    def get_value(self, obj):
        value = obj.value

        if isinstance(value, str) and value.strip().startswith('[') and value.strip().endswith(']'):
            try:
                parsed_value = ast.literal_eval(value)
                if isinstance(parsed_value, list):
                    return parsed_value
            except (ValueError, SyntaxError):
                try:
                    parsed_value = json.loads(value)
                    if isinstance(parsed_value, list):
                        return parsed_value
                except (json.JSONDecodeError, TypeError):
                    pass
        return value


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'name', 'status', 'source_type', 'description']


class MediaImageSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = MediaImage
        fields = ['id', 'name', 'media_type', 'page', 'width', 'height', 'file_url', 'created_at']

    def get_file_url(self, obj):
        if obj.file:
            return obj.file.url
        return None


class MediaSearchResultSerializer(serializers.Serializer, S3UrlMixin):

    def to_representation(self, instance):
        metadata = instance.get('metadata', {})

        url = metadata.get('url', '')
        company = metadata.get('company', '')
        created_at = metadata.get('created_at', '')
        updated_at = metadata.get('updated_at', '')
        priority = metadata.get('priority', 'P1')

        source_id = instance.get('source_id', '')

        try:
            media_id = int(source_id) if source_id else None
        except (ValueError, TypeError):
            media_id = source_id

        title = metadata.get('TITLE', instance.get('title', ''))

        tags = metadata.get('tags', [])

        document_type = None
        for key in ['DOCUMENT_TYPE', 'document_type', 'Document Type', 'DOCUMENT TYPE']:
            if key in metadata:
                document_type = metadata[key]
                break

        file_size = None
        organization_url = None
        org_logo = None
        key_entities = None
        display_mode = None
        display_mode_display = None
        description = None
        db_priority = None
        db_media_type = None
        db_media_type_display = None
        thumbnail_url = None
        view_count = 0
        download_count = 0

        if media_id:
            try:
                from chatbot.models.media_models import Media
                media_obj = Media.objects.select_related('organization').prefetch_related(
                    'key_values',
                    'subdocuments',
                    'subdocuments__key_values'
                ).only(
                    'id', 'file', 'media_type', 'organization__url', 'organization__logo', 'display_mode',
                    'description', 'thumbnail', 'priority'
                ).get(id=media_id)

                source_child = media_obj.subdocuments.filter(
                    key_values__key__iregex=r'^document[ _]type$',
                    key_values__value__icontains='source document'
                ).first()

                if source_child:
                    db_media_type = source_child.media_type
                    db_media_type_display = source_child.get_media_type_display()
                else:
                    db_media_type = media_obj.media_type
                    db_media_type_display = media_obj.get_media_type_display()

                if media_obj.file:
                    file_size = getattr(media_obj.file, "size", None)

                thumbnail_url = self.resolve_thumbnail_url(media_obj)

                if media_obj.organization:
                    organization_url = media_obj.organization.url

                    if media_obj.organization.logo:
                        org_logo = media_obj.organization.get_public_url()

                key_entities_kv = media_obj.key_values.filter(key__iexact='KEY ENTITIES').first()
                if key_entities_kv:
                    key_entities = key_entities_kv.value

                display_mode = media_obj.display_mode
                display_mode_display = media_obj.get_display_mode_display()

                description = media_obj.description

                db_priority = media_obj.priority

                view_count = media_obj.view_count if media_obj.view_count else 0
                download_count = media_obj.download_count if media_obj.download_count else 0

            except Exception as e:
                file_size = metadata.get('file_size', None)
                organization_url = metadata.get('organization_url', None)

        if key_entities is None:
            for key in ['KEY ENTITIES', 'key_entities', 'Key Entities', 'KEY_ENTITIES', 'keyEntities']:
                if key in metadata:
                    key_entities = metadata[key]
                    break

        if db_media_type is None:
            metadata_file_type = metadata.get('type', '')
            if metadata_file_type:
                db_media_type = metadata_file_type
                db_media_type_display = self._get_media_type_display(metadata_file_type)
            else:
                db_media_type = ''
                db_media_type_display = ''

        final_description = description if description is not None else instance.get('summary', '')
        final_priority = db_priority if db_priority is not None else priority

        return {
            'id': media_id,
            'name': title,
            'description': final_description,
            'priority': final_priority,
            'priority_display': final_priority,
            'media_type': db_media_type,
            'media_type_display': db_media_type_display,
            'created_at': created_at,
            'updated_at': updated_at,
            's3_url': url,
            'thumbnail_url': thumbnail_url,
            'file': url,
            'tag_names': tags,
            'title': title,
            'organization': company,
            'document_type': document_type,
            'key_entities': key_entities,
            'file_size': file_size,
            'organization_url': organization_url,
            'org_logo': org_logo,
            'display_mode': display_mode,
            'display_mode_display': display_mode_display,
            'vector_id': instance.get('id'),
            'score': instance.get('score', 0),
            'field_scores': instance.get('field_scores', {}),
            'view_count': view_count,
            'download_count': download_count,
        }

    def _get_media_type_display(self, file_type):
        if not file_type:
            return ''

        file_type_lower = file_type.lower().strip()

        mime_type = FileTypeChoices.get_mime_from_extension(file_type_lower)
        if mime_type:
            for choice_value, choice_display in FileTypeChoices.choices:
                if choice_value == mime_type:
                    return choice_display

        for choice_value, choice_display in FileTypeChoices.choices:
            if choice_value == file_type_lower:
                return choice_display

        additional_extension_to_display = {
            'ppt': 'PPT',
            'pptx': 'PPTX',
            'jpeg': 'JPEG',
            'jpg': 'JPEG',
            'png': 'PNG',
            'gif': 'GIF',
            'mp4': 'MP4',
            'mp3': 'MP3',
            'html': 'HTML',
            'htm': 'HTML',
            'xml': 'XML',
            'json': 'JSON',
            'zip': 'ZIP',
            'rar': 'RAR',
            'tar': 'TAR',
            'gz': 'GZ',
            '7z': '7Z',
        }

        if file_type_lower in additional_extension_to_display:
            return additional_extension_to_display[file_type_lower]

        if file_type_lower.startswith('.'):
            clean_ext = file_type_lower[1:]
            if clean_ext in additional_extension_to_display:
                return additional_extension_to_display[clean_ext]

        additional_mime_to_display = {
            'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'PPTX',
            'application/vnd.ms-powerpoint': 'PPT',
            'text/html': 'HTML',
            'text/xml': 'XML',
            'application/xml': 'XML',
            'application/json': 'JSON',
            'image/jpeg': 'JPEG',
            'image/png': 'PNG',
            'image/gif': 'GIF',
            'image/bmp': 'BMP',
            'image/svg+xml': 'SVG',
            'video/mp4': 'MP4',
            'video/mpeg': 'MPEG',
            'video/quicktime': 'MOV',
            'video/x-msvideo': 'AVI',
            'audio/mpeg': 'MP3',
            'audio/mp3': 'MP3',
            'audio/wav': 'WAV',
            'audio/x-wav': 'WAV',
            'application/zip': 'ZIP',
            'application/x-rar-compressed': 'RAR',
            'application/x-tar': 'TAR',
            'application/gzip': 'GZ',
            'application/x-7z-compressed': '7Z',
        }

        if file_type_lower in additional_mime_to_display:
            return additional_mime_to_display[file_type_lower]

        if file_type.isupper() and len(file_type) <= 5:
            return file_type

        return file_type.upper() if file_type else ''


class MediaListSerializer(serializers.ModelSerializer, S3UrlMixin):
    s3_url = serializers.SerializerMethodField()
    file = serializers.SerializerMethodField()
    tag_names = serializers.SerializerMethodField()
    media_type = serializers.SerializerMethodField()
    media_type_display = serializers.SerializerMethodField()
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    display_mode_display = serializers.CharField(source='get_display_mode_display', read_only=True)
    title = serializers.SerializerMethodField()
    organization = serializers.SerializerMethodField()
    organization_url = serializers.SerializerMethodField()
    org_logo = serializers.SerializerMethodField()
    document_type = serializers.SerializerMethodField()
    key_entities = serializers.SerializerMethodField()
    file_size = serializers.SerializerMethodField()

    keyword_coverage = serializers.IntegerField(read_only=True)
    total_matching_fields = serializers.IntegerField(read_only=True)
    avg_relevance_score = serializers.FloatField(read_only=True)
    max_similarity = serializers.FloatField(read_only=True)
    match_reason = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = Media
        fields = [
            'id', 'name', 'description', 'priority', 'priority_display',
            'media_type', 'media_type_display', 'created_at', 'updated_at',
            's3_url', 'file', 'tag_names', 'title', 'organization',
            'document_type', 'key_entities', 'file_size', 'organization_url', 'org_logo',
            'display_mode', 'display_mode_display',
            'keyword_coverage', 'total_matching_fields', 'avg_relevance_score', 'max_similarity',
            'match_reason', 'thumbnail_url'
        ]

    def get_match_reason(self, obj):
        request = self.context.get('request')
        similarity_threshold = 0.3
        if request:
            similarity_threshold = float(request.query_params.get('similarity_threshold', 0.3))

        if getattr(obj, "exact_title_match_flag", 0) == 1:
            return "Exact title match found."

        if getattr(obj, "trigram_match", 0) == 1:
            max_sim = getattr(obj, "max_similarity", 0)
            if max_sim >= similarity_threshold:
                return f"Fuzzy string similarity match found (similarity: {max_sim:.2f}, threshold: {similarity_threshold})."

        if getattr(obj, "icontains_match", 0) == 1:
            return "Direct text match found in one or more fields."

        if getattr(obj, "keyword_coverage", 0) > 0:
            return "This result matched your search keywords."

        if getattr(obj, "max_similarity", 0) > 0:
            max_sim = getattr(obj, "max_similarity", 0)
            return f"Fuzzy string similarity found (similarity: {max_sim:.2f})."

        return "Match found through search criteria."

    def get_s3_url(self, obj):
        return self.resolve_s3_url(obj)

    def get_thumbnail_url(self, obj):
        return self.resolve_thumbnail_url(obj)

    def get_file(self, obj):
        return obj.get_s3_url() if hasattr(obj, 'get_s3_url') else None

    def get_tag_names(self, obj):
        return list(obj.tags.values_list("name", flat=True))

    def get_metadata_field(self, obj, key_name):
        kv = obj.key_values.filter(key__iexact=key_name).first()
        return kv.value if kv else None

    def get_title(self, obj):
        return self.get_metadata_field(obj, 'TITLE')

    def get_organization(self, obj):
        if obj.organization:
            return obj.organization.name
        return None

    def get_organization_url(self, obj):
        if obj.organization:
            return obj.organization.url
        return None

    def get_org_logo(self, obj):
        if obj.organization and obj.organization.logo:
            return obj.organization.get_public_url()
        return None

    def get_document_type(self, obj):
        document_type = obj.key_values.filter(key__iregex=r'^document[ _]type$').first()
        return document_type.value if document_type else None

    def get_key_entities(self, obj):
        return self.get_metadata_field(obj, 'KEY ENTITIES')

    def get_file_size(self, obj):
        return getattr(obj.file, "size", None) if obj.file else None

    def get_media_type(self, obj):
        if hasattr(obj, "overridden_media_type"):
            return obj.overridden_media_type

        source_child = obj.subdocuments.filter(
            key_values__key__iregex=r'^document[ _]type$',
            key_values__value__icontains='source document'
        ).first()

        if source_child:
            return source_child.media_type

        return obj.media_type

    def get_media_type_display(self, obj):
        if hasattr(obj, "overridden_media_type_display"):
            return obj.overridden_media_type_display

        source_child = obj.subdocuments.filter(
            key_values__key__iregex=r'^document[ _]type$',
            key_values__value__icontains='source document'
        ).first()

        if source_child:
            return source_child.get_media_type_display()

        return obj.get_media_type_display()

class MediaDetailSerializer(serializers.ModelSerializer, S3UrlMixin):
    s3_url = serializers.SerializerMethodField()
    file = serializers.SerializerMethodField()
    tags = TagSerializer(many=True, read_only=True)
    key_values = serializers.SerializerMethodField()
    images = MediaImageSerializer(many=True, read_only=True)
    parent_info = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()
    media_type = serializers.SerializerMethodField()
    media_type_display = serializers.SerializerMethodField()
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    display_mode_display = serializers.CharField(source='get_display_mode_display', read_only=True)
    title = serializers.SerializerMethodField()
    organization = serializers.SerializerMethodField()
    org_logo = serializers.SerializerMethodField()
    document_type = serializers.SerializerMethodField()
    key_entities = serializers.SerializerMethodField()
    file_size = serializers.SerializerMethodField()
    size = serializers.SerializerMethodField()

    class Meta:
        model = Media
        fields = [
            'id', 'name', 'description', 'priority', 'priority_display',
            'media_type', 'media_type_display', 'extracted_text',
            'file', 'url', 'company_bot',
            'parent', 'parent_info', 'created_at', 'updated_at',
            's3_url', 'tags', 'title', 'organization', 'org_logo', 'document_type',
            'key_entities', 'key_values', 'images', 'children',
            'file_size', 'size', 'display_mode', 'display_mode_display',
        ]

    def get_s3_url(self, obj):
        return self.resolve_s3_url(obj)

    def get_file(self, obj):
        return obj.get_s3_url() if hasattr(obj, 'get_s3_url') else None

    def get_key_values(self, obj):
        basic_info = []

        title = obj.key_values.filter(key__iexact='TITLE').first()
        organization_name = None
        if obj.organization:
            organization_name = obj.organization.name

        geography = obj.key_values.filter(key__iexact='GEOGRAPHY').first()
        document_type = obj.key_values.filter(key__iregex=r'^document[ _]type$').first()

        if title and title.value:
            basic_info.append(f"<div><b>Title:</b> {title.value}</div>")

        if organization_name:
            organization_url = obj.organization.url if obj.organization and obj.organization.url else "#"
            basic_info.append(
                f'<div><b>Organization:</b> <a class="text-blue-600 underline underline-offset-2" '
                f'href="{organization_url}" target="_blank" rel="noopener noreferrer">{organization_name}</a></div>')
        if geography and geography.value:
            basic_info.append(f"<div><b>Geography:</b> {geography.value}</div>")

        if document_type and document_type.value:
            basic_info.append(f"<div><b>Document Type:</b> {document_type.value}</div>")

        filtered_kvs = obj.key_values.exclude(
            Q(key__in=['TITLE', 'ORGANIZATION', 'KEY ENTITIES', 'GEOGRAPHY',
                       'ORIGINAL_FILE_URL', 'FOUND_IN_DOCUMENT', 'DOCUMENT TYPE REASON']) |
            Q(key__iregex=r'^document[ _]type$') |
            Q(key__isnull=True, value__isnull=True) |
            Q(key='', value='')
        )

        key_values_data = KeyValueSerializer(filtered_kvs, many=True).data

        if basic_info:
            basic_info_kv = {
                'id': None,
                'key': 'Basic Information',
                'value': basic_info
            }
            key_values_data.insert(0, basic_info_kv)

        if not filtered_kvs.exists() and not basic_info:
            metadata_kvs = obj.key_values.filter(
                Q(key__in=['TITLE', 'KEY ENTITIES', 'GEOGRAPHY']) |
                Q(key__iregex=r'^document[ _]type$')
            ).exclude(
                Q(key__isnull=True, value__isnull=True) |
                Q(key='', value='')
            )
            key_values_data = KeyValueSerializer(metadata_kvs, many=True).data

            if organization_name:
                org_kv = {
                    'id': None,
                    'key': 'ORGANIZATION',
                    'value': organization_name
                }
                key_values_data.append(org_kv)

        if obj.tags.exists():
            tag_names = list(obj.tags.values_list("name", flat=True))
            tags_classification_kv = {
                'id': None,
                'key': 'Tags for Classification',
                'value': tag_names
            }
            key_values_data.append(tags_classification_kv)

        references_html = self._get_references_and_associated_documents(obj)
        if references_html:
            references_kv = {
                'id': None,
                'key': 'References and Associated Documents',
                'value': references_html
            }
            key_values_data.append(references_kv)

        return key_values_data

    def _get_references_and_associated_documents(self, obj):
        references_html = []
        children = obj.subdocuments.all()

        for child in children:
            child_doc_type_kv = child.key_values.filter(key__iregex=r'^document[ _]type$').first()
            is_source_doc = False

            if child_doc_type_kv and child_doc_type_kv.value:
                is_source_doc = 'source document' in child_doc_type_kv.value.lower()

            if is_source_doc:
                if child.subdocuments.filter(display_mode=FileDisplayMode.VISIBLE).exists():
                    grandchildren = child.subdocuments.filter(display_mode=FileDisplayMode.VISIBLE)
                    for grandchild in grandchildren:
                        grandchild_title_kv = grandchild.key_values.filter(key__iexact='TITLE').first()
                        grandchild_title = grandchild_title_kv.value if grandchild_title_kv and grandchild_title_kv.value else grandchild.name

                        references_html.append(
                            f'<div><a class="text-blue-600 underline underline-offset-2" '
                            f'href="{media_base_url}{grandchild.id}" target="_blank" '
                            f'rel="noopener noreferrer">{grandchild_title}</a></div>'
                        )
            else:
                child_title_kv = child.key_values.filter(key__iexact='TITLE').first()
                child_title = child_title_kv.value if child_title_kv and child_title_kv.value else child.name

                references_html.append(
                    f'<div><a class="text-blue-600 underline underline-offset-2" '
                    f'href="{media_base_url}{child.id}" target="_blank" '
                    f'rel="noopener noreferrer">{child_title}</a></div>'
                )

        return references_html

    def get_parent_info(self, obj):
        if obj.parent:
            return {
                'id': obj.parent.id,
                'name': obj.parent.name,
                'media_type': obj.parent.media_type
            }
        return None

    def get_children(self, obj):
        children = obj.subdocuments.all()
        return MediaListSerializer(children, many=True).data if children.exists() else []

    def get_metadata_field(self, obj, key_name):
        kv = obj.key_values.filter(key__iexact=key_name).first()
        return kv.value if kv else None

    def get_title(self, obj):
        return self.get_metadata_field(obj, 'TITLE')

    def get_organization(self, obj):
        if obj.organization:
            return obj.organization.name
        return None

    def get_org_logo(self, obj):
        if obj.organization and obj.organization.logo:
            return obj.organization.get_public_url()
        return None

    def get_document_type(self, obj):
        document_type = obj.key_values.filter(key__iregex=r'^document[ _]type$').first()
        return document_type.value if document_type else None

    def get_key_entities(self, obj):
        return self.get_metadata_field(obj, 'KEY ENTITIES')

    def get_file_size(self, obj):
        try:
            if obj.file and hasattr(obj.file, 'size'):
                return obj.file.size
            return None
        except (ValueError, AttributeError):
            return None

    def get_size(self, obj):
        try:
            if obj.file and hasattr(obj.file, 'size'):
                size = obj.file.size
                if size is None:
                    return None

                for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                    if size < 1024.0:
                        return f"{size:.1f} {unit}"
                    size /= 1024.0
                return f"{size:.1f} PB"
            return None
        except (ValueError, AttributeError):
            return None

    def get_media_type(self, obj):
        return getattr(obj, "overridden_media_type", obj.media_type)

    def get_media_type_display(self, obj):
        if hasattr(obj, "overridden_media_type_display"):
            return obj.overridden_media_type_display
        return obj.get_media_type_display()
