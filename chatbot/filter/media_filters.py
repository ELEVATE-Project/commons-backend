import django_filters
from django.db.models import Q
from chatbot.models.media_models import Media, FileTypeChoices, PriorityChoices


class MediaFilter(django_filters.FilterSet):
    # Text search across multiple fields
    search = django_filters.CharFilter(method='search_filter', label='Search')

    # Exact filters
    media_type = django_filters.ChoiceFilter(choices=FileTypeChoices.choices)
    priority = django_filters.ChoiceFilter(choices=PriorityChoices.choices)

    # Related filters
    tag = django_filters.CharFilter(method='tag_filter', label='Tag name')
    key = django_filters.CharFilter(method='key_filter', label='Key-Value key')
    value = django_filters.CharFilter(method='value_filter', label='Key-Value value')
    key_value = django_filters.CharFilter(method='key_value_filter', label='Key-Value pair (key:value)')

    # Date filters
    created_after = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')

    # Parent/child filters
    parent_id = django_filters.NumberFilter(field_name='parent__id')
    has_parent = django_filters.BooleanFilter(method='has_parent_filter')
    has_children = django_filters.BooleanFilter(method='has_children_filter')

    # Company bot filter
    company_bot = django_filters.NumberFilter(field_name='company_bot__id')

    class Meta:
        model = Media
        fields = ['media_type', 'priority', 'company_bot']

    def search_filter(self, queryset, name, value):
        """Full-text search across name, description, and extracted_text"""
        if not value:
            return queryset

        return queryset.filter(
            Q(name__icontains=value) |
            Q(description__icontains=value) |
            Q(extracted_text__icontains=value)
        )

    def tag_filter(self, queryset, name, value):
        """Filter by tag name"""
        if not value:
            return queryset
        return queryset.filter(tags__name__icontains=value).distinct()

    def key_filter(self, queryset, name, value):
        """Filter by key in key-value pairs"""
        if not value:
            return queryset
        return queryset.filter(keyvalue__key__icontains=value).distinct()

    def value_filter(self, queryset, name, value):
        """Filter by value in key-value pairs"""
        if not value:
            return queryset
        return queryset.filter(keyvalue__value__icontains=value).distinct()

    def key_value_filter(self, queryset, name, value):
        """Filter by key:value pair"""
        if not value or ':' not in value:
            return queryset

        key, val = value.split(':', 1)
        return queryset.filter(
            keyvalue__key__icontains=key.strip(),
            keyvalue__value__icontains=val.strip()
        ).distinct()

    def has_parent_filter(self, queryset, name, value):
        """Filter media with/without parent"""
        if value:
            return queryset.exclude(parent__isnull=True)
        return queryset.filter(parent__isnull=True)

    def has_children_filter(self, queryset, name, value):
        """Filter media with/without children"""
        if value:
            return queryset.filter(media_set__isnull=False).distinct()
        return queryset.filter(media_set__isnull=True)
