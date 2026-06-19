import os
import django
from django.db.models import Q

# project_root = Path(__file__).resolve().parent.parent
# sys.path.insert(0, str(project_root))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'shikshalokam.settings')
django.setup()

from django.core.files.base import ContentFile
from chatbot.models import Media, FileTypeChoices
from chatbot.utils.knowledge_service.extractor.markdown_extractor import MarkdownExtractor


def get_xlsx_stats():
    """
    Get statistics about XLSX files with and without markdown
    """
    xlsx_media = Media.objects.filter(media_type=FileTypeChoices.XLSX)
    total_xlsx = xlsx_media.count()
    without_md = xlsx_media.filter(
        Q(markdown_file__isnull=True) | Q(markdown_file='')
    ).count()

    return {
        'total': total_xlsx,
        'without_md': without_md,
        'with_md': total_xlsx - without_md
    }


def print_stats(stats):
    """
    Display statistics in formatted output
    """
    print(f"Total XLSX files: {stats['total']}")
    print(f"With markdown: {stats['with_md']}")
    print(f"Without markdown: {stats['without_md']}")
    print("-" * 50)


def read_file_content(media):
    """
    Read file content from media object
    """
    if not media.file:
        raise ValueError("No file attached")

    media.file.open('rb')
    content_bytes = media.file.read()
    media.file.close()

    filename = media.file.name.split('/')[-1]
    return content_bytes, filename


def generate_markdown_content(content_bytes, filename, extractor):
    """
    Generate markdown content using MarkdownExtractor
    """
    markdown_content, _ = extractor.extract_comprehensive_content_for_urls(
        content_bytes, filename
    )

    if not markdown_content or len(markdown_content.strip()) == 0:
        raise ValueError("No markdown content generated")

    return markdown_content


def create_markdown_filename(original_filename):
    """
    Create markdown filename from original filename
    """
    base_filename = os.path.splitext(original_filename)[0]
    markdown_filename = f"Markdown_{base_filename}.md"

    if not markdown_filename.endswith('.md'):
        markdown_filename = f"{markdown_filename}.md"

    return markdown_filename


def save_markdown_to_media(media, markdown_content, markdown_filename):
    """
    Save markdown content to media object
    """
    markdown_content_bytes = markdown_content.encode('utf-8')

    media.markdown_file.save(
        markdown_filename,
        ContentFile(markdown_content_bytes),
        save=True
    )


def process_single_media(media, extractor, index, total):
    """
    Process a single media object to generate markdown
    """
    print(f"[{index}/{total}] Processing: {media.name} (ID: {media.id})")

    try:
        content_bytes, filename = read_file_content(media)
        markdown_content = generate_markdown_content(content_bytes, filename, extractor)
        markdown_filename = create_markdown_filename(filename)
        save_markdown_to_media(media, markdown_content, markdown_filename)

        print(f"  ✓ Markdown saved: {markdown_filename}")
        return True, None

    except Exception as e:
        error_msg = str(e)
        print(f"  ✗ Error: {error_msg}")
        return False, error_msg


def generate_markdown_files():
    """
    Main function to generate markdown files for Excel media
    """
    stats = get_xlsx_stats()
    print_stats(stats)

    if stats['without_md'] == 0:
        print("All XLSX files already have markdown files!")
        return

    print(f"Starting generation for {stats['without_md']} files...")
    print("-" * 50)

    extractor = MarkdownExtractor()
    media_without_md = Media.objects.filter(
        media_type=FileTypeChoices.XLSX
    ).filter(
        Q(markdown_file__isnull=True) | Q(markdown_file='')
    )

    success_list = []
    error_list = []

    for i, media in enumerate(media_without_md, 1):
        success, error_msg = process_single_media(media, extractor, i, stats['without_md'])

        if success:
            success_list.append({
                'id': media.id,
                'name': media.name
            })
        else:
            error_list.append({
                'id': media.id,
                'name': media.name,
                'error': error_msg
            })

    print("-" * 50)
    print(f"Complete! Success: {len(success_list)}, Errors: {len(error_list)}")
    print("=" * 50)

    if success_list:
        print(f"\n✓ SUCCESSFUL ({len(success_list)}):")
        for item in success_list:
            print(f"  - ID {item['id']}: {item['name']}")

    if error_list:
        print(f"\n✗ FAILED ({len(error_list)}):")
        for item in error_list:
            print(f"  - ID {item['id']}: {item['name']}")
            print(f"    Error: {item['error']}")

    print("=" * 50)


# if __name__ == "__main__":
#     generate_markdown_files()