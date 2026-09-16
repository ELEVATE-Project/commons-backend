import json
from chatbot.models import Media, KeyValue
from chatbot.models.media_models import MediaImage


# ============================================================================
# SHARED SERIALIZER
# ============================================================================
def serialize_media(media, truncate_text=False):
    """
    Serialize a Media object into a unified dict
    used by BOTH parents and subdocuments.
    """

    extracted_text = media.extracted_text or ''

    if truncate_text and len(extracted_text) > 200:
        extracted_text = extracted_text[:200] + '...'

    # Tags
    tags = []
    if hasattr(media, 'tags'):
        try:
            tags = list(media.tags.values_list('name', flat=True))
        except Exception:
            tags = []

    data = {
        'id': media.id,
        'name': str(media.name) if media.name else '',
        'media_type': str(media.media_type) if media.media_type else '',
        'description': str(media.description) if media.description else '',
        'priority': str(media.priority) if media.priority else '',
        'organization': media.organization.slug if media.organization else '',
        'file_url': media.get_s3_url() if hasattr(media, 'get_s3_url') else '',
        'extracted_text': extracted_text,
        'extracted_text_length': len(media.extracted_text or ''),
        'tags': tags,
        'parent_id': media.parent_id,
        'company_bot_id': media.company_bot_id,
        'created_at': str(media.created_at),
    }

    # Key Values
    kvs = KeyValue.objects.filter(media=media)
    data['key_values'] = [
        {'key': str(kv.key), 'value': str(kv.value) if kv.value else ''}
        for kv in kvs
    ]
    data['key_value_count'] = len(data['key_values'])

    # Images
    images = MediaImage.objects.filter(media=media)
    data['images'] = [
        {
            'image_url': str(img.image_url) if img.image_url else '',
            'caption': str(img.caption) if img.caption else ''
        }
        for img in images
    ]
    data['image_count'] = len(data['images'])

    return data


# ============================================================================
# RECURSIVE CHILD FETCH (IMPORTANT FIXES)
# 1. Use parent_id (NOT parent=media)
# 2. Use _base_manager (NO hidden filtering)
# ============================================================================
def get_subdocuments_recursive(media):
    children = Media._base_manager.filter(
        parent_id=media.id
    ).order_by('created_at')

    subdocuments = []

    for child in children:
        child_dict = serialize_media(child, truncate_text=True)

        child_dict['subdocuments'] = get_subdocuments_recursive(child)
        child_dict['subdocument_count'] = len(child_dict['subdocuments'])

        subdocuments.append(child_dict)

    return subdocuments


# ============================================================================
# MAIN EXPORT FUNCTION
# ============================================================================
def export_media_hierarchy(media_id=None, output_file=None, limit=None):
    """
    Export media with full parent → source → subdocument hierarchy.

    Behavior:
    - If media_id is provided:
        → Export ONLY that tree
    - If media_id is None:
        → Export ALL ROOT documents (parent_id IS NULL)
    """

    # --------------------------------------------------
    # ROOT SELECTION (THIS IS WHY SINGLE VS ALL DIFFERS)
    # --------------------------------------------------
    if media_id:
        try:
            media_queryset = [
                Media._base_manager.get(id=media_id)
            ]
        except Media.DoesNotExist:
            print(f"Media with ID {media_id} not found")
            return []
    else:
        media_queryset = Media._base_manager.filter(
            parent__isnull=True
        ).order_by('-created_at')

        if limit:
            media_queryset = media_queryset[:limit]

    exported_data = []

    # --------------------------------------------------
    # BUILD TREES
    # --------------------------------------------------
    for media in media_queryset:
        media_dict = serialize_media(media)

        media_dict['subdocuments'] = get_subdocuments_recursive(media)
        media_dict['subdocument_count'] = len(media_dict['subdocuments'])

        exported_data.append(media_dict)

    # --------------------------------------------------
    # SUMMARY
    # --------------------------------------------------
    def count_all_subdocs(subdocs):
        count = len(subdocs)
        for s in subdocs:
            count += count_all_subdocs(s.get('subdocuments', []))
        return count

    total_subdocs = sum(
        count_all_subdocs(m['subdocuments']) for m in exported_data
    )

    print("\n" + "=" * 60)
    print("EXPORT SUMMARY")
    print("=" * 60)
    print(f"Total root documents: {len(exported_data)}")
    print(f"Total subdocuments (all levels): {total_subdocs}")
    print("=" * 60)

    # --------------------------------------------------
    # TREE VIEW (DEBUG)
    # --------------------------------------------------
    def print_tree(media, indent=0):
        prefix = "    " * indent
        print(f"{prefix}📄 {media['name']} (ID: {media['id']})")
        print(f"{prefix}   ├─ file_url: {'YES' if media['file_url'] else 'NO'}")
        print(f"{prefix}   ├─ KVs: {media['key_value_count']}")
        print(f"{prefix}   ├─ Images: {media['image_count']}")
        print(f"{prefix}   └─ Subdocs: {media['subdocument_count']}")

        for sub in media.get('subdocuments', []):
            print_tree(sub, indent + 1)

    print("\nHIERARCHY TREE")
    print("-" * 60)
    for media in exported_data:
        print_tree(media)
        print()

    # --------------------------------------------------
    # SAVE FILE
    # --------------------------------------------------
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(exported_data, f, indent=2, ensure_ascii=False)
        print(f"✓ Exported to: {output_file}")

    return exported_data


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

# 1️⃣ Export ONLY one media tree (recommended for debugging)
# result = export_media_hierarchy(
#     media_id=328,
#     output_file='/tmp/media_328_export.json'
# )

# 2️⃣ Export ALL root media trees
result = export_media_hierarchy(
    output_file='/tmp/all_media_export2.json'
)

# 3️⃣ Export ALL root media trees (LIMITED)
# result = export_media_hierarchy(
#     output_file='/tmp/all_media_export.json',
#     limit=10
# )
