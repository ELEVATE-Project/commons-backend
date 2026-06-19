import json_repair
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from django.db import models

from chatbot.models import Tag, FileTypeChoices, FileDisplayMode, TagChoices, TagSourceChoices
from chatbot.models.media_models import Media, KeyValue
from chatbot.serializer.media_serializer import (
    MediaListSerializer, MediaDetailSerializer, MediaSearchResultSerializer
)
from chatbot.filter.media_filters import MediaFilter
from chatbot.utils.chat_query_handler import query_database_with_metadata
from django.contrib.postgres.search import TrigramSimilarity
from django.db.models import (
    Count, Q, Value, FloatField, OuterRef, Subquery, TextField,
    CharField, IntegerField, Case, When, F
)
from django.db.models.functions import Greatest, Coalesce, Lower


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
            key_values__key__iregex=r'^document[ _]type$',
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
            norm_key__iregex=r'^document[ _]type$',
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
            key__iregex=r'^document[ _]type$'
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
                    org_conditions |= Q(
                        organization__name__icontains=org
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
                                key__iregex=r'^document[ _]type$',
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
                key__iregex=r'^document[ _]type$',
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

        serializer = MediaListSerializer(related, many=True)
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
        
        try:
            limit = int(
                request.query_params.get('limit', 1000000000)
            )
            offset = int(request.query_params.get('offset', 0))
        except ValueError:
            return Response({
                "error": "Invalid limit or offset parameter",
                "count": 0,
                "next": None,
                "previous": None,
                "results": []
            }, status=status.HTTP_400_BAD_REQUEST)
        
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
        
        # Determine ordering: score for search, user choice otherwise
        ordering_param = request.query_params.get(
            'ordering', ''
        ).strip()
        
        if query:
            # Use score-based ordering for search queries
            ordering = 'score'
        else:
            # Use user's ordering or default to newest first
            ordering = ordering_param if ordering_param else '-created_at'
        
        ordering_field, ordering_reverse = self._parse_ordering(ordering)
        
        # Fetch large batch for proper sorting and pagination
        top_k = max(1000, offset + limit * 2)
        from chatbot.models import CompanyBot
        company_bot = CompanyBot.objects.filter(route='/sg_search_bot').first()
        filter_score = company_bot.filter_score if company_bot else 0

        other_params = company_bot.other_params if company_bot.other_params else {}
        if other_params and isinstance(other_params, str):
            other_params = json_repair.repair_json(other_params, return_objects=True)
        detail_filter_score = other_params.get("detail_filter_score", None)

        # Query vector database
        vector_response = query_database_with_metadata(
            query=query if query else None,
            top_k=top_k,
            filter_score=filter_score,
            detail_filter_score=detail_filter_score,
            categories=tags if tags else None,
            organizations=organizations if organizations else None,
            resource_type=resource_types if resource_types else None,
            file_type=None
        )
        
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
                "search_metadata": {
                    "query": query,
                    "vector_db_error": True
                }
            }, status=error_status)
        
        all_results = vector_response.get('results', [])
        print("all_results len: ", len(all_results))
        # Apply content exclusion filter
        all_results = self._apply_content_exclusion_filter_v2(
            all_results
        )
        print("all_results len: ", len(all_results))

        if media_types:
            all_results = self._apply_media_type_filter(all_results, media_types)

        total_results = len(all_results)
        print("total_results len: ", total_results)

        # Apply ordering
        if ordering_field and all_results:
            all_results = self._apply_ordering(
                all_results, ordering_field, ordering_reverse
            )
        
        # Apply pagination
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
        
        if offset + limit < total_results:
            next_offset = offset + limit
            next_url = (
                f"{base_url}?q={query}&limit={limit}"
                f"&offset={next_offset}"
            )
            if ordering_param:
                next_url += f"&ordering={ordering}"
            if tags:
                next_url += f"&tags={','.join(tags)}"
            if organizations:
                next_url += f"&organizations={','.join(organizations)}"
            if resource_types:
                next_url += f"&resource_types={','.join(resource_types)}"
            if media_types:
                next_url += f"&media_types={','.join(media_types)}"
        
        if offset > 0:
            previous_offset = max(0, offset - limit)
            previous_url = (
                f"{base_url}?q={query}&limit={limit}"
                f"&offset={previous_offset}"
            )
            if ordering_param:
                previous_url += f"&ordering={ordering}"
            if tags:
                previous_url += f"&tags={','.join(tags)}"
            if organizations:
                previous_url += f"&organizations={','.join(organizations)}"
            if resource_types:
                previous_url += f"&resource_types={','.join(resource_types)}"
            if media_types:
                previous_url += f"&media_types={','.join(media_types)}"
        
        print("len(serializer.data): ", len(serializer.data))
        response_data = {
            "count": total_results,
            "next": next_url,
            "previous": previous_url,
            "results": serializer.data,
            "search_metadata": {
                "query": query,
                "top_k": top_k,
                "offset": offset,
                "limit": limit,
                "ordering": ordering,
                "returned_results": len(serializer.data),
                "search_config": vector_response.get(
                    'search_config', {}
                )
            }
        }
        
        return Response(response_data, status=status.HTTP_200_OK)

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
                    key_values__key__iregex=r'^document[ _]type$',
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
                norm_key__iregex=r'^document[ _]type$',
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
