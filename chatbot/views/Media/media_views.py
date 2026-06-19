from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from chatbot.models import Media
from django.db.models import Q

from chatbot.serializer.media_serializer import MediaDetailSerializer


class MediaSearchView(APIView):
    """
    GET /media/search/?q=budget+approval
    Optional: &limit=50
    Optional: &tags=tag1,tag2
    Optional: &key_values=key1:value1,key2:value2
    """

    def get(self, request, format=None):
        q = request.query_params.get("q", "").strip()
        tags_param = request.query_params.get("tags", "").strip()
        key_values_param = request.query_params.get("key_values", "").strip()

        if not q and not tags_param and not key_values_param:
            return Response({
                "error": "Provide at least q, tags, or key_values"
            }, status=status.HTTP_400_BAD_REQUEST)

        limit_param = request.query_params.get("limit")
        limit = int(limit_param) if limit_param else None

        # Convert tags and key_values into usable structures
        tags_list = [t.strip() for t in tags_param.split(",") if t.strip()] if tags_param else []
        kv_dict = dict(kv.split(":", 1) for kv in key_values_param.split(",") if ":" in kv) if key_values_param else {}

        print(f"Raw query string: {q}")
        print(f"Limit: {limit}")
        print(f"Tags filter: {tags_list}")
        print(f"Key-Value filter: {kv_dict}")

        # ---------- FTS path ----------
        if q:
            query = SearchQuery(q, search_type="plain")
            vector = SearchVector("extracted_text", weight="A")

            fts_qs = (
                Media.objects
                .annotate(rank=SearchRank(vector, query))
                .filter(rank__gte=0.3)
                .distinct()
                .order_by("-rank", "-created_at")[:limit]
            )
            print(f"\nFTS QS: {fts_qs}\n")
            print("SQL being run for FTS:")
            print(str(fts_qs.query))
        else:
            fts_qs = None
            print("\nNo FTS search performed since q is empty")

        qs = None

        if fts_qs is not None and fts_qs.exists():
            qs = fts_qs
            for media in fts_qs:
                print(f"Media: {media.name}, Score: {media.rank}")

            print(f"\nUsing FTS results, count: {fts_qs.count()}\n")
        elif tags_list or kv_dict:
            # Only run fallback if tags or key_values are provided
            print("\nFTS returned 0 results, using fallback search on tags & key-values")

            tags_qs = Media.objects.none()
            kv_qs = Media.objects.none()

            # Search in specified tags
            for t in tags_list:
                print(f"Searching for specified tag: '{t}'")
                tags_qs |= Media.objects.filter(tags__name__icontains=t)

            # Search in specified key-values
            for k, v in kv_dict.items():
                print(f"Searching for key-value: '{k}:{v}'")
                kv_qs |= Media.objects.filter(
                    Q(key_values__key__icontains=k) & Q(key_values__value__icontains=v)
                )

            qs = (tags_qs | kv_qs).distinct().order_by("-created_at")[:limit]

        if qs:
            print(f"\nQS after combining FTS/fallback: {qs}\n")
            print("SQL being run for final QS:")
            print(str(qs.query))

            data = MediaDetailSerializer(qs, many=True).data
            print(f"Found {len(data)} results\n")
        else:
            print("QS returned no results, fallback disabled")
            data = []

        return Response({"count": len(data), "results": data})
