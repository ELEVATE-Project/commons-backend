import json_repair
import logging
import re
from dataclasses import dataclass, field
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from django.db import models
from urllib.parse import urlencode
from chatbot.models import Tag, FileTypeChoices, FileDisplayMode, TagChoices, TagSourceChoices
from chatbot.models.media_models import Media, KeyValue
from chatbot.serializer.media_serializer import (
    MediaListSerializer, MediaDetailSerializer, MediaSearchResultSerializer
)
from chatbot.filter.media_filters import MediaFilter
from chatbot.utils.chat_query_handler import query_database_with_metadata
from chatbot.utils.search_filter_resolver import (
    clean_search_text,
    included_values,
    resolve_query_exact,
    to_response_dict,
)
from django.contrib.postgres.search import TrigramSimilarity
from django.db.models import (
    Count, Q, Value, FloatField, OuterRef, Subquery, TextField,
    CharField, IntegerField, Case, When, F
)
from django.db.models.functions import Greatest, Coalesce, Lower

logger = logging.getLogger('django')


@dataclass
class FuzzyFilterResult:
    """
    What the deterministic (RapidFuzz) resolver returns.

    Shared contract between the deterministic resolver and the LLM step, so the
    two can land independently. ``None`` for a filter means "no opinion" and
    leaves the field open for the LLM; ``candidates`` holds the near-misses that
    were not confident enough to use directly but are still worth showing the
    model, as ``{field: [value, ...]}``.
    """
    organizations: list = None
    media_types: list = None
    exclude_organizations: list = None
    exclude_media_types: list = None
    query: str = None
    confidence: float = 0.0
    candidates: dict = field(default_factory=dict)


@dataclass
class ResolvedFilters:
    """
    What the search should actually run with, plus how each part was decided.

    ``diagnostics`` is the internal debug trail. Named for what it is rather
    than "metadata", which already means the Qdrant payload elsewhere in search.

    The ``exclude_*`` lists are negated conditions ("except Shikshalokam").
    They are a separate axis from the positive lists, not the absence of one.

    ``any_of`` holds FilterBlocks OR'ed with each other and AND'ed with
    everything above — for an OR that joins two different fields. Empty is the
    normal case and means the flat fields are the whole filter.
    """
    query: str
    organizations: list = field(default_factory=list)
    media_types: list = field(default_factory=list)
    exclude_organizations: list = field(default_factory=list)
    exclude_media_types: list = field(default_factory=list)
    any_of: list = field(default_factory=list)
    diagnostics: dict = field(default_factory=dict)


def any_of(lookup, values):
    """OR the values into one Q, for use with .filter() or .exclude()."""
    conditions = Q()
    for value in values:
        conditions |= Q(**{lookup: value})
    return conditions


class FetchThemeView(APIView):
    def get(self, request):
        filters = {
            'source_type__in': [TagSourceChoices.MANUAL, TagSourceChoices.AI_EXTRACTED],
            'status': TagChoices.APPROVED,
        }
        is_theme_param = request.query_params.get('is_theme')
        if is_theme_param is not None:
            filters['is_theme'] = is_theme_param.lower() in ['1', 'true', 'yes']

        tags = (
            Tag.objects
            .filter(**filters)
            .annotate(resource_count=Count('medias', distinct=True))
            .order_by('name')
        )

        themes = [
            {
                'title': tag.name,
                'icon': tag.icon or '',
                'description': tag.description or '',
                'resource_count': tag.resource_count
            }
            for tag in tags
        ]

        return Response({
            'success': True,
            'count': len(themes),
            'themes': themes
        })


class MediaViewSet(viewsets.ReadOnlyModelViewSet):
    filter_backends = [
        DjangoFilterBackend,
        filters.OrderingFilter,
        filters.SearchFilter
    ]
    filterset_class = MediaFilter
    ordering_fields = [
        'id', 'name', 'created_at', 'updated_at', 'priority',
        'media_type', 'organization', 'title'
    ]
    ordering = ['-created_at']
    search_fields = ['name', 'description', 'extracted_text']

    def filter_queryset(self, queryset):
        # Skip OrderingFilter when search is active
        search_text = self.request.query_params.get('q', '').strip()

        if search_text and len(search_text) >= 3:
            for backend in self.filter_backends:
                if backend != filters.OrderingFilter:
                    queryset = backend().filter_queryset(
                        self.request, queryset, self
                    )
            return queryset
        else:
            return super().filter_queryset(queryset)

    def get_queryset(self):
        # Only show visible media
        queryset = Media.objects.filter(
            display_mode=FileDisplayMode.VISIBLE
        )

        title_subquery = KeyValue.objects.filter(
            media=OuterRef('pk'),
            key__iexact='TITLE'
        ).values('value')[:1]

        queryset = queryset.annotate(
            title=Subquery(title_subquery, output_field=CharField()),
            organization_name=Coalesce(
                'organization__name',
                Value('', output_field=CharField())
            ),
            media_type_display=Case(
                *[
                    When(media_type=choice[0], then=Value(str(choice[1])))
                    for choice in FileTypeChoices.choices
                ],
                default=Value(''),
                output_field=CharField()
            )
        )

        source_child_qs = Media.objects.filter(
            parent=OuterRef('pk'),
            key_values__key__iregex=r'^document[_ ]type$',
            key_values__value__icontains='source document'
        ).order_by('id')

        child_media_type_sq = Subquery(
            source_child_qs.values('media_type')[:1]
        )

        queryset = queryset.annotate(
            overridden_media_type=Coalesce(child_media_type_sq, F("media_type"))
        )

        queryset = queryset.annotate(
            overridden_media_type_display=Case(
                *[
                    When(overridden_media_type=choice[0], then=Value(str(choice[1])))
                    for choice in FileTypeChoices.choices
                ],
                default=Value(""),
                output_field=CharField()
            )
        )

        search_text = self.request.query_params.get('q', '').strip()
        similarity_threshold = float(
            self.request.query_params.get('similarity_threshold', 0.3)
        )

        if search_text and len(search_text) >= 3:
            # Search mode: apply ranking
            queryset = self._apply_enhanced_multi_keyword_search(
                queryset, search_text, similarity_threshold
            )
            queryset = self._apply_custom_filters(queryset)
        else:
            # Non-search mode: add default annotations
            queryset = queryset.annotate(
                keyword_coverage=Value(0, output_field=IntegerField()),
                total_matching_fields=Value(
                    0, output_field=IntegerField()
                ),
                avg_relevance_score=Value(
                    0.0, output_field=FloatField()
                ),
                max_similarity=Value(0.0, output_field=FloatField()),
                exact_title_match_flag=Value(
                    0, output_field=IntegerField()
                ),
                trigram_match=Value(0, output_field=IntegerField()),
                icontains_match=Value(0, output_field=IntegerField())
            )
            queryset = self._apply_custom_filters(queryset)

        # Optimize queries based on action
        if self.action == 'list':
            queryset = self._apply_content_exclusion_filter(queryset)
            queryset = queryset.select_related(
                'organization', 'parent'
            ).prefetch_related('tags')
        elif self.action == 'retrieve':
            queryset = queryset.select_related(
                'organization', 'parent'
            ).prefetch_related(
                'tags', 'key_values', 'images', 'subdocuments'
            )

        return queryset.distinct()

    def _apply_content_exclusion_filter(self, queryset):
        # Exclude "Source Document" media
        source_document_media = KeyValue.objects.annotate(
            norm_key=Lower('key', output_field=TextField())
        ).filter(
            norm_key__iregex=r'^document[_ ]type$',
            value__icontains='source document'
        ).values_list('media_id', flat=True)

        return queryset.exclude(id__in=source_document_media)

    def _apply_enhanced_multi_keyword_search(
        self, queryset, search_text, similarity_threshold
    ):
        # Multi-keyword search with ranking:
        # 1. Exact title matches
        # 2. Trigram similarity
        # 3. Substring fallback
        keywords = [
            kw.strip().lower() for kw in search_text.split()
            if kw.strip()
        ]
        if not keywords:
            return queryset.annotate(
                keyword_coverage=Value(0, output_field=IntegerField()),
                total_matching_fields=Value(
                    0, output_field=IntegerField()
                ),
                avg_relevance_score=Value(
                    0.0, output_field=FloatField()
                ),
                max_similarity=Value(0.0, output_field=FloatField()),
                exact_title_match_flag=Value(
                    0, output_field=IntegerField()
                ),
                trigram_match=Value(0, output_field=IntegerField()),
                icontains_match=Value(0, output_field=IntegerField())
            )

        doc_type_subquery = KeyValue.objects.filter(
            media=OuterRef('pk'),
            key__iregex=r'^document[_ ]type$'
        ).values('value')[:1]

        queryset = queryset.annotate(
            doc_type=Subquery(doc_type_subquery, output_field=CharField()),
            exact_title_match=Case(
                When(title__iexact=search_text.strip(), then=Value(1)),
                default=Value(0),
                output_field=IntegerField()
            )
        )

        keyword_annotations = {}
        for i, keyword in enumerate(keywords):
            keyword_annotations.update({
                f'title_sim_{i}': Coalesce(
                    TrigramSimilarity('title', keyword),
                    Value(0.0, output_field=FloatField())
                ),
                f'org_sim_{i}': Coalesce(
                    TrigramSimilarity('organization_name', keyword),
                    Value(0.0, output_field=FloatField())
                ),
                f'doc_type_sim_{i}': Coalesce(
                    TrigramSimilarity('doc_type', keyword),
                    Value(0.0, output_field=FloatField())
                ),
                f'tag_sim_{i}': Coalesce(
                    Subquery(
                        Tag.objects.filter(
                            medias=OuterRef('pk')
                        ).annotate(
                            similarity=TrigramSimilarity('name', keyword)
                        ).values('similarity').order_by('-similarity')[:1]
                    ),
                    Value(0.0, output_field=FloatField())
                ),
                f'media_type_display_sim_{i}': Coalesce(
                    TrigramSimilarity('media_type_display', keyword),
                    Value(0.0, output_field=FloatField())
                )
            })

        queryset = queryset.annotate(**keyword_annotations)

        # Aggregate scores across keywords
        total_matching_fields = Value(
            0, output_field=IntegerField()
        )
        total_relevance_score = Value(
            0.0, output_field=FloatField()
        )
        max_similarity_overall = Value(
            0.0, output_field=FloatField()
        )
        keyword_coverage_score = Value(
            0, output_field=IntegerField()
        )

        for i, keyword in enumerate(keywords):
            keyword_matching_fields = (
                Case(
                    When(
                        **{f'title_sim_{i}__gte': similarity_threshold},
                        then=Value(1)
                    ),
                    default=Value(0),
                    output_field=IntegerField()
                ) +
                Case(
                    When(
                        **{f'org_sim_{i}__gte': similarity_threshold},
                        then=Value(1)
                    ),
                    default=Value(0),
                    output_field=IntegerField()
                ) +
                Case(
                    When(
                        **{f'doc_type_sim_{i}__gte': similarity_threshold},
                        then=Value(1)
                    ),
                    default=Value(0),
                    output_field=IntegerField()
                ) +
                Case(
                    When(
                        **{f'tag_sim_{i}__gte': similarity_threshold},
                        then=Value(1)
                    ),
                    default=Value(0),
                    output_field=IntegerField()
                ) +
                Case(
                    When(
                        **{
                            f'media_type_display_sim_{i}__gte':
                            similarity_threshold
                        },
                        then=Value(1)
                    ),
                    default=Value(0),
                    output_field=IntegerField()
                )
            )

            # Weighted relevance score
            keyword_relevance = (
                2.0 * F(f'title_sim_{i}') +
                1.8 * F(f'tag_sim_{i}') +
                1.6 * F(f'doc_type_sim_{i}') +
                1.4 * F(f'org_sim_{i}') +
                1.2 * F(f'media_type_display_sim_{i}')
            )

            keyword_max_sim = Greatest(
                f'title_sim_{i}',
                f'org_sim_{i}',
                f'doc_type_sim_{i}',
                f'tag_sim_{i}',
                f'media_type_display_sim_{i}'
            )

            keyword_has_match = Case(
                When(
                    Q(
                        **{f'title_sim_{i}__gte': similarity_threshold}
                    ) |
                    Q(
                        **{f'org_sim_{i}__gte': similarity_threshold}
                    ) |
                    Q(
                        **{f'doc_type_sim_{i}__gte': similarity_threshold}
                    ) |
                    Q(
                        **{f'tag_sim_{i}__gte': similarity_threshold}
                    ) |
                    Q(
                        **{
                            f'media_type_display_sim_{i}__gte':
                            similarity_threshold
                        }
                    ),
                    then=Value(1)
                ),
                default=Value(0),
                output_field=IntegerField()
            )

            total_matching_fields = (
                total_matching_fields + keyword_matching_fields
            )
            total_relevance_score = (
                total_relevance_score + keyword_relevance
            )
            max_similarity_overall = Greatest(
                max_similarity_overall, keyword_max_sim
            )
            keyword_coverage_score = (
                keyword_coverage_score + keyword_has_match
            )

        queryset = queryset.annotate(
            keyword_coverage=keyword_coverage_score,
            total_matching_fields=total_matching_fields,
            avg_relevance_score=total_relevance_score / len(keywords),
            max_similarity=max_similarity_overall
        )

        exact_title_condition = Q(title__iexact=search_text.strip())
        trigram_condition = Q(max_similarity__gte=similarity_threshold)

        # Substring fallback
        icontains_condition = (
            Q(title__icontains=search_text) |
            Q(organization_name__icontains=search_text) |
            Q(doc_type__icontains=search_text) |
            Q(media_type_display__icontains=search_text)
        )

        # Add tags substring check
        tag_icontains_condition = Q(
            id__in=Subquery(
                Tag.objects.filter(
                    medias=OuterRef('pk'),
                    name__icontains=search_text
                ).values('medias__id')
            )
        )
        icontains_condition |= tag_icontains_condition

        queryset = queryset.annotate(
            exact_title_match_flag=Case(
                When(exact_title_condition, then=Value(1)),
                default=Value(0),
                output_field=IntegerField()
            ),
            trigram_match=Case(
                When(trigram_condition, then=Value(1)),
                default=Value(0),
                output_field=IntegerField()
            ),
            icontains_match=Case(
                When(icontains_condition, then=Value(1)),
                default=Value(0),
                output_field=IntegerField()
            )
        )

        # Filter and order by ranking
        queryset = queryset.filter(
            Q(exact_title_match_flag=1) |
            Q(trigram_match=1) |
            Q(icontains_match=1)
        )

        return queryset.order_by(
            '-exact_title_match_flag',
            '-keyword_coverage',
            '-total_matching_fields',
            '-avg_relevance_score',
            '-max_similarity',
            '-trigram_match',
            '-icontains_match'
        )

    def _apply_custom_filters(self, queryset):
        # Extract filter parameters
        tags_param = self.request.query_params.get(
            'tags', ''
        ).strip()
        key_values_param = self.request.query_params.get(
            'key_values', ''
        ).strip()
        organization = self.request.query_params.get(
            'organizations', ''
        ).strip()
        media_type = self.request.query_params.get(
            'media_types', ''
        ).strip()
        resource_type = self.request.query_params.get(
            'resource_types', ''
        ).strip()
        priority = self.request.query_params.get(
            'priorities', ''
        ).strip()

        filter_conditions = Q()

        if tags_param:
            tags_list = [
                t.strip() for t in tags_param.split(",")
                if t.strip()
            ]
            if tags_list:
                tag_conditions = Q()
                for tag in tags_list:
                    tag_conditions |= Q(
                        id__in=Subquery(
                            Tag.objects.filter(
                                medias=OuterRef('pk'),
                                name__icontains=tag
                            ).values('medias__id')
                        )
                    )
                filter_conditions &= tag_conditions

        if key_values_param:
            kv_pairs = {}
            for kv in key_values_param.split(","):
                if ":" in kv:
                    k, v = kv.split(":", 1)
                    kv_pairs[k.strip()] = v.strip()

            for key, value in kv_pairs.items():
                filter_conditions &= Q(
                    id__in=Subquery(
                        KeyValue.objects.filter(
                            media=OuterRef('pk'),
                            key__iexact=key,
                            value__icontains=value
                        ).values('media__id')
                    )
                )

        if organization:
            organizations_list = [
                org.strip() for org in organization.split(",")
                if org.strip()
            ]
            if organizations_list:
                org_conditions = Q()
                for org in organizations_list:
                    # The frontend passes organization slugs, so match on slug.
                    org_conditions |= Q(
                        organization__slug__iexact=org
                    )
                filter_conditions &= org_conditions

        if resource_type:
            resource_types_list = [
                rt.strip() for rt in resource_type.split(",")
                if rt.strip()
            ]
            if resource_types_list:
                rt_conditions = Q()
                for rt in resource_types_list:
                    rt_conditions |= Q(
                        id__in=Subquery(
                            KeyValue.objects.filter(
                                media=OuterRef('pk'),
                                key__iregex=r'^document[_ ]type$',
                                value__icontains=rt
                            ).values('media__id')
                        )
                    )
                filter_conditions &= rt_conditions

        if media_type:
            requested_types = [
                mt.strip() for mt in media_type.split(",")
                if mt.strip()
            ]
            media_types_list = self._resolve_media_types(
                requested_types
            )
            if media_types_list:
                filter_conditions &= Q(
                    media_type__in=media_types_list
                )

        if priority:
            filter_conditions &= Q(priority=priority)

        if filter_conditions:
            queryset = queryset.filter(filter_conditions)

        return queryset

    def get_serializer_class(self):
        if self.action == 'list':
            return MediaListSerializer
        return MediaDetailSerializer

    def _resolve_keyword_to_mime_types(self, keyword):
        # Convert file extension to MIME type
        from chatbot.models import FileTypeChoices

        keyword_lower = keyword.lower().strip()
        resolved_types = []

        mime_type = FileTypeChoices.get_mime_from_extension(
            keyword_lower
        )
        if mime_type:
            resolved_types.append(mime_type)
            return resolved_types

        valid_extensions = FileTypeChoices.get_valid_extensions()
        if keyword_lower in valid_extensions:
            mime_type = FileTypeChoices.get_mime_from_extension(
                keyword_lower
            )
            if mime_type:
                resolved_types.append(mime_type)
                return resolved_types

        # Fallback: partial matches
        for choice in FileTypeChoices.choices:
            mime_type = choice[0]
            display_name = choice[1] if len(choice) > 1 else mime_type

            if (keyword_lower in mime_type.lower() or
                keyword_lower in display_name.lower() or
                mime_type.lower().endswith(f'/{keyword_lower}') or
                mime_type.lower().startswith(f'{keyword_lower}/')):
                resolved_types.append(mime_type)

        return resolved_types if resolved_types else None

    def _resolve_media_types(self, requested_types):
        resolved_types = []

        for requested_type in requested_types:
            requested_lower = requested_type.lower().strip()

            if '/' in requested_type:
                resolved_types.append(requested_type)
                continue

            mime_type = FileTypeChoices.get_mime_from_extension(
                requested_lower
            )
            if mime_type:
                resolved_types.append(mime_type)
                continue

            matches = []
            for choice in FileTypeChoices.choices:
                mime_type = choice[0]
                display_name = (
                    choice[1] if len(choice) > 1 else mime_type
                )

                if (requested_lower in mime_type.lower() or
                    requested_lower in display_name.lower() or
                    mime_type.lower().endswith(
                        f'/{requested_lower}'
                    ) or
                    mime_type.lower().startswith(
                        f'{requested_lower}/'
                    )):
                    matches.append(mime_type)

            resolved_types.extend(matches)

            if not matches and requested_type not in resolved_types:
                resolved_types.append(requested_type)

        return list(dict.fromkeys(resolved_types))

    @action(detail=False, methods=['get'])
    def master_list(self, request):
        # Return master list of filters
        from chatbot.models import PriorityChoices

        queryset = self.filter_queryset(self.get_queryset())

        organizations_data = (
            queryset
            .exclude(organization__slug__isnull=True)
            .exclude(organization__slug='')
            .values('organization__name', 'organization__slug')
            .annotate(
                name=F('organization__name'),
                slug=F('organization__slug')
            )
            .distinct()
        )

        organizations = []
        seen_slugs = set()
        for org in organizations_data:
            if org['slug'] and org['slug'] not in seen_slugs:
                organizations.append({
                    'name': (
                        org['name'] if org['name']
                        else org['slug'].title()
                    ),
                    'slug': org['slug']
                })
                seen_slugs.add(org['slug'])

        organizations = sorted(
            organizations, key=lambda x: x['name'].lower()
        )

        media_types = []
        media_type_counts = dict(
            queryset.values_list('media_type')
            .annotate(count=Count('id'))
            .values_list('media_type', 'count')
        )

        for choice in FileTypeChoices.choices:
            mime_type = choice[0]
            display_name = choice[1]
            count = media_type_counts.get(mime_type, 0)
            if count > 0:
                media_types.append({
                    'value': mime_type,
                    'display': display_name,
                    'count': count
                })

        resource_types = []
        document_type_data = (
            KeyValue.objects
            .filter(
                key__iregex=r'^document[_ ]type$',
                media__in=queryset
            )
            .values('value')
            .annotate(count=Count('media', distinct=True))
            .order_by('value')
        )

        for item in document_type_data:
            document_type_value = item['value']
            count = item['count']

            if document_type_value and count > 0:
                display_name = document_type_value.replace(
                    '_', ' '
                ).title()
                resource_types.append({
                    'value': document_type_value,
                    'display': display_name,
                    'count': count
                })

        priorities = []
        priority_counts = dict(
            queryset.values_list('priority')
            .annotate(count=Count('id'))
            .values_list('priority', 'count')
        )

        for choice in PriorityChoices.choices:
            priority_value = choice[0]
            count = priority_counts.get(priority_value, 0)
            if count > 0:
                priorities.append({
                    'value': priority_value,
                    'display': (
                        choice[1] if len(choice) > 1
                        else priority_value
                    ),
                    'count': count
                })

        tags = list(
            Tag.objects
            .filter(medias__in=queryset)
            .values('id', 'name')
            .annotate(count=Count('medias'))
            .order_by('name')
            .distinct()
        )

        return Response({
            'total_count': queryset.count(),
            'organizations': organizations,
            'media_types': media_types,
            'resource_types': resource_types,
            'priorities': priorities,
            'tags': tags
        })

    @action(detail=True, methods=['get'])
    def related_media(self, request, pk=None):
        # Return related media (siblings and similar tags)
        media = self.get_object()

        siblings = Media.objects.none()
        if media.parent:
            siblings = Media.objects.filter(
                parent=media.parent,
                display_mode=FileDisplayMode.VISIBLE
            ).exclude(id=media.id)

        similar_tags = Media.objects.none()
        if media.tags.exists():
            tag_ids = media.tags.values_list('id', flat=True)
            similar_tags = Media.objects.filter(
                tags__in=tag_ids,
                display_mode=FileDisplayMode.VISIBLE
            ).exclude(id=media.id).distinct()

        related = (siblings | similar_tags).distinct()[:20]

        serializer = MediaListSerializer(related, many=True, context={'request': request})
        return Response({
            'media_id': media.id,
            'related_count': related.count(),
            'related_media': serializer.data
        })


class MediaSearchV2View(APIView):
    # Vector database search API
    VALID_ORDERING_FIELDS = [
        'id', 'name', 'created_at', 'updated_at', 'priority',
        'media_type', 'organization', 'title', 'score'
    ]
    
    def get(self, request, format=None):
        query = request.query_params.get('q', '').strip()
        vector_search_requested = bool(query)
        
        try:
            # Change default from 1 billion to a safe number like 100
            limit = int(request.query_params.get('limit', 100))
            offset = int(request.query_params.get('offset', 0))
        except ValueError:
            return Response({
                "error": "Invalid limit or offset parameter",
                "count": 0,
                "next": None,
                "previous": None,
                "results": []
            }, status=status.HTTP_400_BAD_REQUEST)
            
        # Reject negative offsets or zero/negative limits
        if limit < 1 or offset < 0:
            return Response({
                "error": "Limit must be at least 1 and offset must be 0 or greater.",
                "count": 0,
                "next": None,
                "previous": None,
                "results": []
            }, status=status.HTTP_400_BAD_REQUEST)
            
        # Cap limit to a maximum of 1000 to prevent server memory exhaustion
        if limit > 1000:
            limit = 1000
        
        # Reject negative offsets or zero/negative limits
        if limit < 1 or offset < 0:
            return Response({
                "error": "Limit must be at least 1 and offset must be 0 or greater.",
                "count": 0,
                "next": None,
                "previous": None,
                "results": []
            }, status=status.HTTP_400_BAD_REQUEST)
            
        # Cap limit to a maximum of 1000 to prevent server memory exhaustion
        if limit > 1000:
            limit = 1000

        # Extract filter parameters (with backward compatibility)
        tags = self._parse_list_param(
            request.query_params.get('tags', '')
        )
        if not tags:
            tags = self._parse_list_param(
                request.query_params.get('categories', '')
            )
        
        organizations = self._parse_list_param(
            request.query_params.get('organizations', '')
        )
        
        resource_types = self._parse_list_param(
            request.query_params.get('resource_types', '')
        )
        if not resource_types:
            resource_types = self._parse_list_param(
                request.query_params.get('resource_type', '')
            )
        
        media_types = self._parse_list_param(
            request.query_params.get('media_types', '')
        )
        if not media_types:
            media_types = self._parse_list_param(
                request.query_params.get('file_type', '')
            )
        media_types = self._normalize_media_types(media_types)

        fuzzy = None
        any_of = []
        resolved_filters = self._resolve_query_filters(query) if query else None
        if resolved_filters:
            print(
                "[MediaSearchV2View] Resolved search filters:::::::::::::",
                to_response_dict(query, resolved_filters),
            )
            any_of = self._build_any_of_filters(query)
            if not any_of:
                if not tags:
                    tags = included_values(resolved_filters.theme)
                if not resource_types:
                    resource_types = included_values(
                        resolved_filters.resource_type
                    )
            fuzzy = self._fuzzy_result_from_resolved_filters(
                resolved_filters,
                include_flat_filters=not any_of,
                raw_query=query,
                semantic_query=(
                    self._search_text_from_any_of_clauses(query)
                    if any_of else resolved_filters.search_text
                ),
            )
        
        # Determine ordering: score for search, user choice otherwise
        ordering_param = request.query_params.get(
            'ordering', ''
        ).strip()
        
        if vector_search_requested or query:
            # Use score-based ordering for search queries
            ordering = 'score'
        else:
            # Use user's ordering or default to newest first
            ordering = ordering_param if ordering_param else '-created_at'
        
        ordering_field, ordering_reverse = self._parse_ordering(ordering)

        if vector_search_requested or query:
            return self._get_vector_search_response(
                request=request,
                query=query,
                limit=limit,
                offset=offset,
                ordering=ordering,
                ordering_param=ordering_param,
                tags=tags,
                organizations=organizations,
                resource_types=resource_types,
                media_types=media_types,
                fuzzy=fuzzy,
                any_of=any_of,
            )

        # Normalize score ordering (only valid for search) to created_at for database queries
        if ordering_field == 'score':
            ordering_field = 'created_at'
            ordering_reverse = True
            ordering = '-created_at'

        return self._get_database_list_response(
            request=request,
            limit=limit,
            offset=offset,
            ordering=ordering,
            ordering_field=ordering_field,
            ordering_reverse=ordering_reverse,
            tags=tags,
            organizations=organizations,
            resource_types=resource_types,
            media_types=media_types,
        )

    def _get_vector_search_response(
        self,
        request,
        query,
        limit,
        offset,
        ordering,
        ordering_param,
        tags,
        organizations,
        resource_types,
        media_types,
        fuzzy=None,
        any_of=None,
    ):
        # Fetch large batch for proper sorting and pagination
        top_k = max(1000, offset + limit * 2)
        from chatbot.models import CompanyBot
        company_bot = CompanyBot.objects.filter(route='/sg_search_bot').first()
        filter_score = company_bot.filter_score if company_bot else 0

        other_params = (
            company_bot.other_params
            if company_bot and company_bot.other_params else {}
        )
        if other_params and isinstance(other_params, str):
            other_params = json_repair.repair_json(other_params, return_objects=True)
        detail_filter_score = other_params.get("detail_filter_score", None)

        resolved = self._resolve_search_filters(
            query,
            fuzzy=fuzzy,
            explicit_filters={
                'organizations': organizations,
                'media_types': media_types,
            },
        )
        # Not `resolved.query or query`: an empty residual is meaningful and
        # becomes a filters-only listing below.
        query = resolved.query
        if not query:
            ordering = ordering_param if ordering_param else '-created_at'
        organizations = resolved.organizations
        media_types = resolved.media_types
        exclude_organizations = list(resolved.exclude_organizations)
        exclude_media_types = list(resolved.exclude_media_types)
        resolved_any_of = list(resolved.any_of or [])
        deterministic_any_of = list(any_of or [])
        # One source, never both: the splitter resolves each clause in isolation
        # and so misses a qualifier stated once before the OR, and OR'ing its
        # looser branch in would swallow the correct one. The model's answer
        # wins; the splitter is the fallback for when there is no answer.
        combined_any_of = resolved_any_of or deterministic_any_of

        print(f"[MediaSearchV2View] resolved query: {query!r}")
        print(f"[MediaSearchV2View] resolved organizations: {organizations}")
        print(f"[MediaSearchV2View] resolved media_types: {media_types}")
        print(f"[MediaSearchV2View] filter_resolution diagnostics: {resolved.diagnostics}")

        # Nothing left to embed once the query reduced to filters only, so serve
        # it from the same PostgreSQL path a filters-only request uses.
        # Exclusions and alternatives count too: "all files except PDF" leaves no
        # residual query, and is a filter-only listing, not an unfiltered search.
        filters_present = bool(
            tags or organizations or resource_types or media_types
            or exclude_organizations or exclude_media_types or combined_any_of)
        if not query and filters_present:
            # Ordering is 'score' here, which is meaningless without a query.
            db_ordering = ordering_param if ordering_param else '-created_at'
            db_field, db_reverse = self._parse_ordering(db_ordering)
            return self._get_database_list_response(
                request=request,
                limit=limit,
                offset=offset,
                ordering=db_ordering,
                ordering_field=db_field,
                ordering_reverse=db_reverse,
                tags=tags,
                organizations=organizations,
                resource_types=resource_types,
                media_types=media_types,
                exclude_organizations=exclude_organizations,
                exclude_media_types=exclude_media_types,
                any_of_blocks=combined_any_of,
                diagnostics=resolved.diagnostics,
            )

        # Imported locally, like the AI-search chain elsewhere in this view, so a
        # broken import degrades one search instead of the whole media API.
        from chatbot.services.search.vocabularies import (
            expand_aliases, file_type_vocabulary)

        # Widened to every spelling the payload uses: metadata.type holds both
        # 'application/pdf' and a bare 'pdf' depending on how a doc was ingested.
        type_vocabulary = file_type_vocabulary()
        qdrant_file_types = expand_aliases(media_types, type_vocabulary)
        qdrant_exclude_file_types = expand_aliases(exclude_media_types, type_vocabulary)
        # Each alternative needs the same widening; named any_of_blocks because
        # any_of is already the Q-builder at the top of this module. Driven off
        # the same combined_any_of the PostgreSQL branch uses, so the two
        # backends can never be handed a different set of alternatives.
        any_of_blocks = []
        for block in combined_any_of:
            expanded_block = dict(self._filter_block_payload(block))
            for key in ("file_type", "exclude_file_type"):
                values = expanded_block.get(key)
                if values:
                    expanded_block[key] = expand_aliases(values, type_vocabulary)
            any_of_blocks.append(expanded_block)

        # Query vector database
        vector_response = query_database_with_metadata(
            query=query if query else None,
            top_k=top_k,
            filter_score=filter_score,
            detail_filter_score=detail_filter_score,
            categories=tags if tags else None,
            organizations=organizations if organizations else None,
            resource_type=resource_types if resource_types else None,
            file_type=qdrant_file_types if qdrant_file_types else None,
            exclude_organizations=exclude_organizations if exclude_organizations else None,
            exclude_file_type=qdrant_exclude_file_types if qdrant_exclude_file_types else None,
            any_of=any_of_blocks if any_of_blocks else None
        )

        print(f"[MediaSearchV2View] vector_response error: {vector_response.get('error')}")
        print(f"[MediaSearchV2View] vector_response result count: {len(vector_response.get('results', []))}")

        if vector_response.get('error'):
            error_status = vector_response.get('status_code', 500)
            return Response({
                "error": vector_response.get(
                    'message', 'Vector database error'
                ),
                "count": 0,
                "next": None,
                "previous": None,
                "results": [],
                # Tells "vector service is down" apart from "filter matched
                # nothing" — both return zero results.
                "search_metadata": {
                    "query": query,
                    "vector_db_error": True,
                },
            }, status=error_status)

        all_results = vector_response.get('results', [])
        all_results = self._apply_content_exclusion_filter_v2(all_results)

        if media_types:
            all_results = self._apply_media_type_filter(all_results, media_types)

        total_results = len(all_results)

        if ordering and all_results:
            all_results = self._apply_ordering(
                all_results, *self._parse_ordering(ordering)
            )

        paginated_results = (
            all_results[offset:offset + limit]
            if offset < len(all_results) else []
        )

        serializer = MediaSearchResultSerializer(
            paginated_results, many=True
        )
        
        # Build pagination URLs
        base_url = request.build_absolute_uri(request.path)
        next_url = None
        previous_url = None
        
        next_url, previous_url = self._build_pagination_urls(
            request=request,
            limit=limit,
            offset=offset,
            total_results=total_results,
            ordering=ordering_param if ordering_param else '',
        )

        return Response({
            "count": total_results,
            "next": next_url,
            "previous": previous_url,
            "results": serializer.data,
            "search_metadata": {
                "query": query,
                # Vector path only — the test scripts detect the backend by
                # whether this key exists. Never add it to the DB response.
                "top_k": top_k,
                "offset": offset,
                "limit": limit,
                "ordering": ordering,
                "returned_results": len(serializer.data),
                "search_config": vector_response.get('search_config', {}),
                # How each filter was decided. Without it, "LLM was skipped" and
                # "LLM found nothing" look identical from the results alone.
                "filter_resolution": resolved.diagnostics,
                # What was actually sent to Qdrant, after alias expansion.
                # Differs from filter_resolution when expansion changed a value.
                "applied_filters": self.get_applied_search_filters(
                    tags=tags,
                    organizations=organizations,
                    resource_types=resource_types,
                    file_types=qdrant_file_types,
                    exclude_organizations=exclude_organizations,
                    exclude_file_types=qdrant_exclude_file_types,
                    any_of_blocks=any_of_blocks,
                ),
            },
        }, status=status.HTTP_200_OK)

    def _resolve_search_filters(self, raw_query, fuzzy=None, explicit_filters=None):
        """
        Resolve the filters and query for one search.

        Decides whether the LLM is needed — from the configured mode, the
        deterministic resolver's confidence, and the confidence threshold —
        before calling it. ``_resolve_llm_filters`` does the actual gateway
        call and is only invoked once that decision says to run it.

        ``fuzzy`` is a FuzzyFilterResult from the deterministic resolver, or None
        while that work is still landing — the LLM path is designed to run
        without it. Explicit UI-selected filters are never overridden.

        Never raises on account of the LLM: any failure returns exactly what the
        search would have used with the LLM turned off.
        """
        explicit = explicit_filters or {}
        explicit_orgs = explicit.get('organizations') or []
        explicit_types = explicit.get('media_types') or []

        # No fuzzy result means zero confidence.
        fuzzy = fuzzy or FuzzyFilterResult()

        # getattr, not attribute access: the deterministic resolver may not carry
        # exclusions yet, and an absent field must read as "found none".
        resolved = ResolvedFilters(
            query=getattr(fuzzy, 'query', None) if fuzzy.query is not None else raw_query,
            organizations=explicit_orgs or (fuzzy.organizations or []),
            media_types=explicit_types or (fuzzy.media_types or []),
            exclude_organizations=getattr(fuzzy, 'exclude_organizations', None) or [],
            exclude_media_types=getattr(fuzzy, 'exclude_media_types', None) or [],
            diagnostics={
                'llm_used': False,
                # Named for its source: it is the deterministic matcher's score,
                # and it sits beside the threshold it is compared against.
                'fuzzy_confidence': fuzzy.confidence,
                'organizations_source': 'explicit' if explicit_orgs else (
                    'fuzzy' if fuzzy.organizations else 'none'),
                'media_types_source': 'explicit' if explicit_types else (
                    'fuzzy' if fuzzy.media_types else 'none'),
                'organizations': explicit_orgs or (fuzzy.organizations or []),
                'media_types': explicit_types or (fuzzy.media_types or []),
                'exclude_organizations': getattr(fuzzy, 'exclude_organizations', None) or [],
                'exclude_media_types': getattr(fuzzy, 'exclude_media_types', None) or [],
                'semantic_query': getattr(fuzzy, 'query', None) if fuzzy.query is not None else raw_query,
                'candidates': fuzzy.candidates,
            },
        )

        # Everything below is best-effort. The broad except is deliberate: the
        # LLM path can fail in ways that are not gateway errors at all — a
        # missing bot row, a malformed tool_context, an unmapped provider, a
        # cache problem, a bug in the vocabulary builder — and none of them
        # should turn a search that works today into a 500.
        try:
            # Imported here, inside the guard, so a broken import in the
            # AI-search chain degrades this one search instead of taking the
            # whole media API down at module load.
            from chatbot.services.search.config import get_search_llm_setting
            from chatbot.services.search.prompts import get_search_bot

            bot = get_search_bot()
            mode = get_search_llm_setting(bot, 'llm_mode')
            threshold = get_search_llm_setting(bot, 'llm_confidence_threshold')
            all_explicit = bool(explicit_orgs and explicit_types)

            should_call, reason = self._should_call_llm(
                mode, fuzzy.confidence, threshold, all_explicit)

            # llm_decision records which branch was taken, for both outcomes. It
            # is deliberately not called llm_skipped: on failure the reason
            # survives into the except below, and "skipped: mode_always"
            # alongside an error would describe the opposite of what happened.
            resolved.diagnostics.update({
                'llm_mode': mode,
                'llm_confidence_threshold': threshold,
                'llm_decision': reason,
            })

            if should_call:
                self._resolve_llm_filters(
                    raw_query, fuzzy, bot, resolved, explicit_orgs, explicit_types)

        except Exception as exc:
            logger.exception(
                'ai_search: LLM filter extraction failed, '
                'using deterministic filters only')
            resolved.diagnostics.update({
                'llm_used': False,
                'llm_error': type(exc).__name__,
                'llm_error_code': getattr(exc, 'code', None),
            })

        return resolved

    def _should_call_llm(self, mode, confidence, threshold, all_explicit):
        """Return whether LLM should run and why."""
        from chatbot.services.search.config import MODE_ALWAYS, MODE_OFF

        if mode == MODE_OFF:
            return False, 'mode_off'
        if mode == MODE_ALWAYS:
            return True, 'mode_always'
        if all_explicit:
            return False, 'filters_explicit'
        if confidence >= threshold:
            return False, 'confidence_met'
        return True, 'low_confidence'

    def _resolve_llm_filters(
        self, raw_query, fuzzy, bot, resolved, explicit_orgs, explicit_types,
    ):
        """Resolve filters with the LLM and merge the result."""
        from chatbot.services.search import llm_extractor

        llm = llm_extractor.extract_search_filters(
            raw_query=raw_query,
            candidates=fuzzy.candidates,
            bot=bot,
        )
        if llm is None:
            resolved.diagnostics['llm_decision'] = 'no_answer'
            cooldown = llm_extractor.cooldown_reason()
            if cooldown:
                resolved.diagnostics['llm_cooldown'] = cooldown
            return

        self._apply_llm_filters(resolved, llm, explicit_orgs, explicit_types)

    def _remove_unconfirmed_fuzzy_values(self, resolved, field_name):
        """
        Drop the fuzzy guesses the model was shown and chose not to confirm.

        Only fuzzy matches become candidates, so an exact match is never
        dropped. Values are subtracted rather than cleared, so a query that
        mixes an exact match with a bad guess keeps the exact one.
        """
        resolved_values = getattr(resolved, field_name) or []
        fuzzy_candidate_values = set(
            (resolved.diagnostics.get('candidates') or {}).get(field_name) or [])
        if not resolved_values or not fuzzy_candidate_values:
            return resolved_values

        confirmed_values = [
            value for value in resolved_values
            if value not in fuzzy_candidate_values
        ]
        if len(confirmed_values) != len(resolved_values):
            resolved.diagnostics[f'{field_name}_source'] = 'fuzzy_unconfirmed'
            resolved.diagnostics[field_name] = confirmed_values
        return confirmed_values

    def _apply_llm_filters(self, resolved, llm, explicit_orgs, explicit_types):
        """Merge LLM filters without overriding explicit UI filters."""
        resolved.diagnostics.update({
            'llm_used': True,
            'llm_bot_route': llm.bot_route,
            'llm_latency_ms': llm.latency_ms,
        })

        if llm.rejected:
            resolved.diagnostics['llm_rejected'] = llm.rejected

        if not explicit_orgs and llm.organizations is not None:
            resolved.organizations = llm.organizations
            resolved.diagnostics['organizations_source'] = 'llm'
            resolved.diagnostics['organizations'] = llm.organizations
        elif not explicit_orgs:
            resolved.organizations = self._remove_unconfirmed_fuzzy_values(
                resolved, 'organizations')

        if not explicit_types and llm.media_types is not None:
            resolved.media_types = llm.media_types
            resolved.diagnostics['media_types_source'] = 'llm'
            resolved.diagnostics['media_types'] = llm.media_types
        elif not explicit_types:
            resolved.media_types = self._remove_unconfirmed_fuzzy_values(
                resolved, 'media_types')

        # Exclusions have no explicit-UI counterpart, so there is nothing to
        # outrank them; None still means the model gave no opinion.
        if llm.exclude_organizations is not None:
            resolved.exclude_organizations = llm.exclude_organizations
        if llm.exclude_media_types is not None:
            resolved.exclude_media_types = llm.exclude_media_types

        # Alternatives need no explicit-UI guard either: they are AND'ed with
        # the fields above, so an explicit UI selection still applies in full
        # and can only be narrowed, never overridden.
        if llm.any_of:
            resolved.any_of = llm.any_of
            resolved.diagnostics['any_of'] = [
                block.as_payload() for block in llm.any_of]

        resolved.diagnostics['exclude_organizations'] = resolved.exclude_organizations
        resolved.diagnostics['exclude_media_types'] = resolved.exclude_media_types

        resolved.query = self._clean_filter_search_text(llm.semantic_query)
        resolved.diagnostics['semantic_query'] = resolved.query

    def _get_database_list_response(
        self,
        request,
        limit,
        offset,
        ordering,
        ordering_field,
        ordering_reverse,
        tags,
        organizations,
        resource_types,
        media_types,
        exclude_organizations=None,
        exclude_media_types=None,
        any_of_blocks=None,
        diagnostics=None,
    ):
        queryset = self._build_database_queryset()
        queryset = self._apply_database_filters(
            queryset,
            tags=tags,
            organizations=organizations,
            resource_types=resource_types,
            media_types=media_types,
            exclude_organizations=exclude_organizations,
            exclude_media_types=exclude_media_types,
            any_of_blocks=any_of_blocks,
        )

        # Built once, then logged and returned, so the two can never disagree.
        applied_filters = self.get_applied_search_filters(
            tags=tags,
            organizations=organizations,
            resource_types=resource_types,
            file_types=media_types,
            exclude_organizations=exclude_organizations,
            exclude_file_types=exclude_media_types,
            any_of_blocks=any_of_blocks,
        )
        print("[MediaSearchV2View] database filters: " + str(applied_filters))

        total_results = queryset.count()

        if ordering_field:
            queryset = self._apply_database_ordering(
                queryset=queryset,
                field=ordering_field,
                reverse=ordering_reverse,
            )

        paginated_results = queryset[offset:offset + limit]

        print(f"[MediaSearchV2View] database page: ordering={ordering} "
              f"limit={limit} offset={offset} count={total_results}")

        serializer = MediaListSerializer(paginated_results, many=True, context={'request': request})

        next_url, previous_url = self._build_pagination_urls(
            request=request,
            limit=limit,
            offset=offset,
            total_results=total_results,
            ordering=ordering,
        )

        return Response({
            "count": total_results,
            "next": next_url,
            "previous": previous_url,
            "results": serializer.data,
            "search_metadata": {
                # Always empty: this path only runs when nothing is left to
                # embed. No top_k either — its absence marks the DB backend.
                "query": '',
                "offset": offset,
                "limit": limit,
                "ordering": ordering,
                "returned_results": len(serializer.data),
                # Empty for a plain listing, which resolves no filters at all.
                "filter_resolution": diagnostics or {},
                "applied_filters": applied_filters,
            },
        }, status=status.HTTP_200_OK)

    def _build_database_queryset(self):
        queryset = Media.objects.filter(
            display_mode=FileDisplayMode.VISIBLE
        ).exclude(
            key_values__key__iregex=r'^document[_ ]type$',
            key_values__value__icontains='source document'
        )

        title_subquery = KeyValue.objects.filter(
            media=OuterRef('pk'),
            key__iexact='TITLE'
        ).values('value')[:1]

        queryset = queryset.annotate(
            title=Subquery(title_subquery, output_field=CharField()),
            organization_name=Coalesce(
                'organization__name',
                Value('', output_field=CharField())
            )
        )

        source_child_qs = Media.objects.filter(
            parent=OuterRef('pk'),
            key_values__key__iregex=r'^document[_ ]type$',
            key_values__value__icontains='source document'
        ).order_by('id')

        queryset = queryset.annotate(
            overridden_media_type=Coalesce(
                Subquery(source_child_qs.values('media_type')[:1]),
                F('media_type')
            )
        )

        queryset = queryset.annotate(
            overridden_media_type_display=Case(
                *[
                    When(
                        overridden_media_type=choice[0],
                        then=Value(str(choice[1]))
                    )
                    for choice in FileTypeChoices.choices
                ],
                default=Value(""),
                output_field=CharField()
            )
        )

        return queryset.select_related(
            'organization', 'parent'
        ).prefetch_related(
            'tags', 'key_values', 'subdocuments', 'subdocuments__key_values'
        ).distinct()

    def _apply_database_filters(
        self,
        queryset,
        tags,
        organizations,
        resource_types,
        media_types,
        exclude_organizations=None,
        exclude_media_types=None,
        any_of_blocks=None,
    ):
        if tags:
            tag_conditions = Q()
            for tag in tags:
                tag_conditions |= Q(tags__name__icontains=tag)
            queryset = queryset.filter(tag_conditions)

        if organizations:
            org_conditions = Q()
            for org in organizations:
                # The frontend passes organization slugs, so match on slug.
                org_conditions |= Q(organization__slug__iexact=org)
            queryset = queryset.filter(org_conditions)

        if resource_types:
            resource_conditions = Q()
            for resource_type in resource_types:
                resource_conditions |= Q(
                    key_values__key__iregex=r'^document[_ ]type$',
                    key_values__value__icontains=resource_type
                )
            queryset = queryset.filter(resource_conditions)

        if media_types:
            queryset = queryset.filter(overridden_media_type__in=media_types)

        # .exclude(a | b) is NOT (a OR b), i.e. the NOT IN the filters ask for.
        if exclude_organizations:
            queryset = queryset.exclude(
                any_of('organization__slug__iexact', exclude_organizations))

        if exclude_media_types:
            queryset = queryset.exclude(overridden_media_type__in=exclude_media_types)

        if any_of_blocks:
            any_of_conditions = Q()
            for block in any_of_blocks:
                block_conditions = Q()
                if isinstance(block, dict):
                    block_organizations = block.get('organizations') or []
                    block_media_types = (
                        block.get('media_types') or block.get('file_type') or []
                    )
                    block_exclude_organizations = (
                        block.get('exclude_organizations') or []
                    )
                    block_exclude_media_types = (
                        block.get('exclude_media_types')
                        or block.get('exclude_file_type')
                        or []
                    )
                else:
                    block_organizations = block.organizations
                    block_media_types = block.media_types
                    block_exclude_organizations = block.exclude_organizations
                    block_exclude_media_types = block.exclude_media_types
                
                if block_organizations:
                    org_q = Q()
                    for org in block_organizations:
                        org_q |= Q(organization__slug__iexact=org)
                    block_conditions &= org_q
                
                if block_media_types:
                    block_conditions &= Q(overridden_media_type__in=block_media_types)
                
                if block_exclude_organizations:
                    block_conditions &= ~any_of(
                        'organization__slug__iexact',
                        block_exclude_organizations,
                    )
                
                if block_exclude_media_types:
                    block_conditions &= ~Q(
                        overridden_media_type__in=block_exclude_media_types
                    )

                # A block that recognised nothing is an empty Q(), which matches
                # every row and would cancel the whole alternative set.
                if not block_conditions:
                    continue

                any_of_conditions |= block_conditions
            
            queryset = queryset.filter(any_of_conditions)

        return queryset.distinct()

    def _apply_database_ordering(self, queryset, field, reverse=False):
        ordering_map = {
            'id': 'id',
            'name': 'name',
            'created_at': 'created_at',
            'updated_at': 'updated_at',
            'priority': 'priority',
            'media_type': 'overridden_media_type',
            'organization': 'organization_name',
            'title': 'title',
        }

        ordering_field = ordering_map.get(field, 'created_at')
        prefix = '-' if reverse else ''
        return queryset.order_by(f'{prefix}{ordering_field}', f'{prefix}id')

    def _build_pagination_urls(
        self, request, limit, offset, total_results, ordering='',
    ):
        """
        Next/previous for this request, in exactly the parameters it arrived in.

        The filters are re-read from the request rather than taken from the
        view's locals: by the time these are built the AI flow has replaced
        those with the filters it resolved, and a page-two URL carrying them
        would drop the query it rewrote and hand the resolved filters back as
        explicit UI ones. Parsed the same way get() parses them, aliases and all.
        """
        base_url = request.build_absolute_uri(request.path)

        query = request.query_params.get('q', '').strip()

        tags = self._parse_list_param(
            request.query_params.get('tags', '')
        )
        if not tags:
            tags = self._parse_list_param(
                request.query_params.get('categories', '')
            )

        organizations = self._parse_list_param(
            request.query_params.get('organizations', '')
        )

        resource_types = self._parse_list_param(
            request.query_params.get('resource_types', '')
        )
        if not resource_types:
            resource_types = self._parse_list_param(
                request.query_params.get('resource_type', '')
            )

        media_types = self._parse_list_param(
            request.query_params.get('media_types', '')
        )
        if not media_types:
            media_types = self._parse_list_param(
                request.query_params.get('file_type', '')
            )
        media_types = self._normalize_media_types(media_types)

        # Initialize a dictionary instead of a list
        query_params = {
            "limit": str(limit),
            "offset": str(offset),
        }

        # Add items to the dictionary
        if query:
            query_params["q"] = query
        if ordering:
            query_params["ordering"] = ordering
        if tags:
            query_params["tags"] = ",".join(tags)
        if organizations:
            query_params["organizations"] = ",".join(organizations)
        if resource_types:
            query_params["resource_types"] = ",".join(resource_types)
        if media_types:
            query_params["media_types"] = ",".join(media_types)

        next_url = None
        previous_url = None

        # Safely encode the URL using urlencode
        if offset + limit < total_results:
            next_params = query_params.copy()
            next_params["offset"] = str(offset + limit)
            next_url = f"{base_url}?{urlencode(next_params, doseq=True)}"

        if offset > 0:
            previous_offset = max(0, offset - limit)
            previous_params = query_params.copy()
            previous_params["offset"] = str(previous_offset)
            previous_url = f"{base_url}?{urlencode(previous_params, doseq=True)}"

        return next_url, previous_url

    def _apply_media_type_filter(self, results, requested_media_types):
        """
        Filter results by actual media type, considering source document children.
        This ensures that when a source document child exists, we filter by the child's
        media type, not the parent's media type.
        """
        filtered_results = []

        for result in results:
            source_id = result.get('source_id')
            try:
                source_id_int = int(source_id) if source_id else None
            except (ValueError, TypeError):
                source_id_int = None

            if not source_id_int:
                continue

            try:
                media_obj = Media.objects.prefetch_related(
                    'subdocuments',
                    'subdocuments__key_values'
                ).only('id', 'media_type').get(id=source_id_int)

                source_child = media_obj.subdocuments.filter(
                    key_values__key__iregex=r'^document[_ ]type$',
                    key_values__value__icontains='source document'
                ).first()

                # Use source child's media type if exists, otherwise parent's
                actual_media_type = source_child.media_type if source_child else media_obj.media_type

                # Check if actual media type matches any requested media type
                if actual_media_type in requested_media_types:
                    filtered_results.append(result)

            except Media.DoesNotExist:
                # If media object doesn't exist, skip this result
                continue
            except Exception:
                # If any error occurs, skip this result
                continue

        return filtered_results
    
    def _apply_content_exclusion_filter_v2(self, results):
        # Exclude source documents, low scores, and non-visible media
        from chatbot.models import CompanyBot
        company_bot = CompanyBot.objects.get(route='/sg_search_bot')
        
        # Filter by relevance score
        score_filtered_results = results
        
        # for result in results:
        #     if not isinstance(result, dict):
        #         continue
        #
        #     relevance_score = result.get('score', 0)
        #
        #     if relevance_score >= company_bot.filter_score:
        #         score_filtered_results.append(result)
        
        # Get source document media IDs
        source_document_media_ids = set(
            KeyValue.objects.annotate(
                norm_key=Lower('key', output_field=TextField())
            ).filter(
                norm_key__iregex=r'^document[_ ]type$',
                value__icontains='source document'
            ).values_list('media_id', flat=True)
        )
        
        # Get non-visible media IDs
        non_visible_media_ids = set(
            Media.objects.exclude(
                display_mode=FileDisplayMode.VISIBLE
            ).values_list('id', flat=True)
        )
        
        # Filter out excluded media
        filtered_results = []
        
        for result in score_filtered_results:
            source_id = result.get('source_id')
            try:
                source_id_int = int(source_id) if source_id else None
            except (ValueError, TypeError):
                source_id_int = None
            
            # Exclude source documents and non-visible media
            if source_id_int and (
                source_id_int in source_document_media_ids or
                source_id_int in non_visible_media_ids
            ):
                continue
            
            filtered_results.append(result)
        
        return filtered_results
    
    def _parse_list_param(self, param_value):
        # Parse comma-separated string to list
        if not param_value or not param_value.strip():
            return []
        return [
            item.strip() for item in param_value.split(',')
            if item.strip()
        ]

    def _resolve_query_filters(self, query):
        from chatbot.services.search.vocabularies import (
            file_type_vocabulary,
            organization_vocabulary,
        )
        return resolve_query_exact(
            query,
            organization_vocabulary=organization_vocabulary(),
            file_type_vocabulary=file_type_vocabulary(),
        )

    def _fuzzy_result_from_resolved_filters(
        self,
        resolved_filters,
        include_flat_filters=True,
        raw_query=None,
        semantic_query=None,
    ):
        semantic_query = self._clean_filter_search_text(
            resolved_filters.search_text if semantic_query is None
            else semantic_query
        )
        if not semantic_query and raw_query:
            semantic_query = self._semantic_query_without_filter_spans(
                raw_query, resolved_filters
            )
        return FuzzyFilterResult(
            organizations=included_values(
                resolved_filters.organization, use_slug=True
            ) if include_flat_filters else [],
            media_types=self._included_file_type_values(
                resolved_filters.file_type
            ) if include_flat_filters else [],
            exclude_organizations=self._excluded_values(
                resolved_filters.organization, use_slug=True
            ) if include_flat_filters else [],
            exclude_media_types=self._excluded_file_type_values(
                resolved_filters.file_type
            ) if include_flat_filters else [],
            query=semantic_query,
            confidence=resolved_filters.confidence,
            candidates={
                "organizations": resolved_filters.candidates.get(
                    "organization", []
                ),
                "media_types": resolved_filters.candidates.get(
                    "file_type", []
                ),
            },
        )

    def _semantic_query_without_filter_spans(self, raw_query, resolved_filters):
        remaining = raw_query or ""
        for match in (
            list(resolved_filters.organization)
            + list(resolved_filters.file_type)
        ):
            span = getattr(match, "matched_span", "")
            if not span:
                continue
            remaining = re.sub(
                re.escape(span),
                " ",
                remaining,
                count=1,
                flags=re.IGNORECASE,
            )
        return self._clean_filter_search_text(clean_search_text(remaining))

    def get_applied_search_filters(
        self,
        tags=None,
        organizations=None,
        resource_types=None,
        file_types=None,
        exclude_organizations=None,
        exclude_file_types=None,
        any_of_blocks=None,
    ):
        """
        Report the filters actually applied, for the log and search_metadata.

        Unlike filter_resolution (how filters were *decided*), this is what was
        applied after alias expansion. str() keeps enum media types serialisable.
        """
        return {
            'tags': list(tags or []),
            'organizations': list(organizations or []),
            'resource_types': list(resource_types or []),
            'media_types': [str(value) for value in file_types or []],
            'exclude_organizations': list(exclude_organizations or []),
            'exclude_media_types': [
                str(value) for value in exclude_file_types or []],
            'any_of': [
                self._filter_block_payload(block)
                for block in any_of_blocks or []
            ],
        }

    def _filter_block_payload(self, block):
        if isinstance(block, dict):
            return block
        return block.as_payload()

    def _excluded_values(self, matches, use_slug=False):
        values = []
        for match in matches:
            if not match.negated:
                continue
            values.append(match.slug if use_slug and match.slug else match.display_value)
        return list(dict.fromkeys(value for value in values if value))

    def _included_file_type_values(self, matches):
        values = []
        for match in matches:
            if match.negated:
                continue
            values.append(self._file_type_payload_value(match))
        return list(dict.fromkeys(value for value in values if value))

    def _excluded_file_type_values(self, matches):
        values = []
        for match in matches:
            if not match.negated:
                continue
            values.extend(self._file_type_payload_variants(match))
        return list(dict.fromkeys(value for value in values if value))

    def _file_type_payload_variants(self, match):
        display_value = match.display_value or ""
        slug = match.slug or ""
        variants = [
            slug,
            display_value,
            display_value.lower(),
        ]

        extension = FileTypeChoices.get_extension_mapping().get(slug)
        if not extension and "/" in slug:
            extension = f".{slug.rsplit('/', 1)[-1]}"
        if extension:
            variants.extend([extension, extension.lstrip(".")])

        return variants

    def _build_any_of_filters(self, query):
        clauses = [
            clause.strip()
            for clause in re.split(r"\bOR\b", query, flags=re.IGNORECASE)
            if clause.strip()
        ]
        if len(clauses) < 2:
            return []

        blocks = []
        for clause in clauses:
            resolved = self._resolve_query_filters(clause)
            block = self._any_of_block_from_resolved_filters(resolved)
            if block:
                blocks.append(block)

        # Fewer than two alternatives is an AND, which the flat fields already
        # express, and the vector service rejects a one-entry any_of outright.
        # Mirrors llm_extractor._resolve_any_of.
        if len(blocks) < 2:
            return []

        return self._distribute_shared_file_types(blocks)

    def _distribute_shared_file_types(self, blocks):
        """
        Carry a file type stated once into the bare organization branches after it.

        "pdf from A or B" resolves its second clause to an organization alone,
        matching every file B has and swallowing the narrowed branch beside it.
        Only such a branch inherits — one naming its own format, or format-only,
        means what it says — and only the positive type travels, never exclusions.
        """
        distributed = []
        for block in blocks:
            if set(block) == {'organizations'}:
                inherited = next(
                    (earlier['file_type']
                     for earlier in distributed if earlier.get('file_type')),
                    None,
                )
                if inherited:
                    block = dict(block, file_type=list(inherited))
            distributed.append(block)
        return distributed

    def _search_text_from_any_of_clauses(self, query):
        clauses = [
            clause.strip()
            for clause in re.split(r"\bOR\b", query, flags=re.IGNORECASE)
            if clause.strip()
        ]
        search_texts = []
        for clause in clauses:
            search_text = self._resolve_query_filters(clause).search_text
            if search_text and search_text not in search_texts:
                search_texts.append(search_text)
        if not search_texts:
            return ""
        if len(search_texts) == 1:
            return search_texts[0]
        return " ".join(search_texts)

    def _any_of_block_from_resolved_filters(self, resolved_filters):
        block = {}
        organizations = included_values(
            resolved_filters.organization, use_slug=True
        )
        file_types = self._included_file_type_values(
            resolved_filters.file_type
        )
        exclude_organizations = self._excluded_values(
            resolved_filters.organization, use_slug=True
        )
        exclude_file_types = self._excluded_file_type_values(
            resolved_filters.file_type
        )

        if organizations:
            block["organizations"] = organizations
        if file_types:
            block["file_type"] = file_types
        if exclude_organizations:
            block["exclude_organizations"] = exclude_organizations
        if exclude_file_types:
            block["exclude_file_type"] = exclude_file_types

        return block

    def _file_type_payload_value(self, match):
        # The slug is the FileTypeChoices value, which is what both stores hold:
        # Postgres in Media.media_type, and Qdrant in metadata.type via
        # prepare_vector_db_data. Nothing writes a short 'application/docx'.
        return match.slug

    def _clean_filter_search_text(self, search_text):
        cleaned = re.sub(r"[^\w\s]", " ", search_text or "").strip().lower()
        cleaned = re.sub(r"\s+", " ", cleaned)
        if cleaned in {"everything", "all", "anything", "and", "or"}:
            return ""
        return cleaned

    def _normalize_media_types(self, media_types):
        normalized = []
        for media_type in media_types:
            mime_type = FileTypeChoices.get_mime_from_extension(media_type)
            normalized.append(mime_type or media_type)
        return normalized
    
    def _normalize_media_types(self, media_types):
        normalized = []
        for media_type in media_types:
            mime_type = FileTypeChoices.get_mime_from_extension(media_type)
            normalized.append(mime_type or media_type)
        return normalized
    
    def _parse_ordering(self, ordering_param):
        # Parse ordering parameter to (field, reverse) tuple
        if not ordering_param:
            return 'created_at', True
        
        reverse = ordering_param.startswith('-')
        field = ordering_param.lstrip('-')
        
        if field not in self.VALID_ORDERING_FIELDS:
            return 'created_at', True
        
        # Higher scores should come first
        if field == 'score':
            reverse = not reverse
        
        return field, reverse
    
    def _apply_ordering(self, results, field, reverse=False):
        # Sort results by specified field
        def get_sort_key(item):
            # Extract sort key from result item
            metadata = item.get('metadata', {})
            
            if field == 'score':
                try:
                    return float(item.get('score', 0) or 0)
                except (ValueError, TypeError):
                    return 0.0
            elif field == 'id':
                source_id = (
                    item.get('source_id') or item.get('id') or
                    metadata.get('id') or metadata.get('source_id')
                )
                if source_id is None:
                    return 0
                try:
                    if isinstance(source_id, str):
                        return int(source_id)
                    elif isinstance(source_id, (int, float)):
                        return int(source_id)
                    else:
                        return 0
                except (ValueError, TypeError):
                    return 0
            elif field == 'name' or field == 'title':
                title = metadata.get('title', item.get('title', ''))
                return title.lower() if title else ''
            elif field == 'created_at':
                created_at = metadata.get('created_at', '')
                return (
                    created_at if created_at
                    else '1970-01-01T00:00:00'
                )
            elif field == 'updated_at':
                updated_at = metadata.get('updated_at', '')
                return (
                    updated_at if updated_at
                    else '1970-01-01T00:00:00'
                )
            elif field == 'priority':
                priority = metadata.get('priority', 'P4')
                priority_map = {
                    'P1': 1, 'P2': 2, 'P3': 3, 'P4': 4
                }
                return priority_map.get(priority, 5)
            elif field == 'media_type':
                media_type = metadata.get('type', '')
                return media_type.lower() if media_type else ''
            elif field == 'organization':
                org = metadata.get('company', '')
                return org.lower() if org else ''
            else:
                return ''
        
        try:
            return sorted(results, key=get_sort_key, reverse=reverse)
        except Exception:
            return results
