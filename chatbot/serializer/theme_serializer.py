from pathlib import Path
from xml.etree.ElementTree import ParseError, TreeBuilder, XMLParser, fromstring
from django.core.files.storage import FileSystemStorage
from django.db import transaction
from django.utils.text import slugify
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from chatbot.models.theme_models import ResourceTheme


class ResourceThemeSerializer(serializers.Serializer):
    """Public list fields for resource themes."""

    id = serializers.IntegerField(read_only=True)
    code = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    media_count = serializers.IntegerField(read_only=True)
    icon = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    def get_icon(self, obj):
        if not obj.icon:
            return None

        stored_path = obj.icon.lstrip('/')
        for prefix in ('chatbot/static/portal/', 'static/portal/'):
            if stored_path.startswith(prefix):
                relative_path = stored_path[len(prefix):]
                break
        else:
            return None

        portal = (Path(__file__).resolve().parents[1] / 'static' / 'portal').resolve()
        try:
            icon_path = (portal / relative_path).resolve()
            icon_path.relative_to(portal)
            if icon_path.suffix.lower() != '.svg':
                return None
            return icon_path.read_text(encoding='utf-8')
        except (OSError, ValueError, UnicodeError):
            return None


class SvgTreeBuilder(TreeBuilder):
    def doctype(self, name, pubid, system):
        raise ValueError('SVG document types are not allowed.')


class ThemeIconUploadField(serializers.FileField):
    def to_internal_value(self, data):
        upload = super().to_internal_value(data)
        if Path(upload.name).suffix.lower() != '.svg':
            raise serializers.ValidationError('Only SVG files are allowed.')
        try:
            root = fromstring(upload.read(), parser=XMLParser(target=SvgTreeBuilder()))
        except (ParseError, ValueError):
            raise serializers.ValidationError('Upload a valid SVG file.')
        finally:
            upload.seek(0)
        if root.tag not in ('svg', '{http://www.w3.org/2000/svg}svg'):
            raise serializers.ValidationError('Upload a valid SVG file.')
        for element in root.iter():
            tag = element.tag.rsplit('}', 1)[-1].lower()
            if tag in ('script', 'foreignobject', 'iframe', 'animate', 'set', 'animatetransform', 'animatemotion'):
                raise serializers.ValidationError('SVG icons must not contain active content.')
            for attribute, value in element.attrib.items():
                attribute = attribute.rsplit('}', 1)[-1].lower()
                if attribute.startswith('on') or (attribute == 'href' and not value.startswith('#')):
                    raise serializers.ValidationError('SVG icons must not contain scripts or external references.')
        return upload

    def to_representation(self, value):
        return value


class ResourceThemeCreateSerializer(serializers.ModelSerializer):
    icon = ThemeIconUploadField(required=False, allow_null=True)

    name = serializers.CharField(
        max_length=255,
        validators=[UniqueValidator(
            queryset=ResourceTheme.objects.all(),
            lookup='iexact',
            message='A theme with this name already exists.',
        )],
    )

    class Meta:
        model = ResourceTheme
        fields = (
            'id', 'code', 'name', 'description', 'is_primary', 'status',
            'media_count', 'icon',
            'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')


    @transaction.atomic
    def create(self, validated_data):
        upload = validated_data.pop('icon', None)
        instance = super().create(validated_data)
        if upload is not None:
            instance.icon = self._store_icon(upload, instance.name, instance.pk)
            instance.save(update_fields=['icon'])
        return instance

    def update(self, instance, validated_data):
        upload = validated_data.get('icon')
        if upload is None:
            return super().update(instance, validated_data)

        validated_data['icon'] = self._store_icon(
            upload, validated_data.get('name', instance.name), instance.pk,
        )
        return super().update(instance, validated_data)

    @staticmethod
    def _store_icon(upload, theme_name, theme_id):
        storage = FileSystemStorage(
            location=Path(__file__).resolve().parents[1] / 'static' / 'portal',
            allow_overwrite=True,
        )
        name = slugify(theme_name) or f'theme-{theme_id}'
        storage.save(f'{name}.svg', upload)
        return f'/chatbot/static/portal/{name}.svg'


class ResourceThemeUpdateSerializer(ResourceThemeCreateSerializer):
    class Meta(ResourceThemeCreateSerializer.Meta):
        read_only_fields = ('id', 'code', 'created_at', 'updated_at')

    def validate(self, attrs):
        if 'code' in self.initial_data or 'theme-code' in self.initial_data:
            raise serializers.ValidationError({'code': 'Theme code cannot be updated.'})
        return super().validate(attrs)
