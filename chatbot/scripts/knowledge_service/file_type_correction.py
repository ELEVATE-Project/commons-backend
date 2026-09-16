import os
import django
import sys
from pathlib import Path

# project_root = Path(__file__).resolve().parent.parent
# sys.path.insert(0, str(project_root))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'shikshalokam.settings')
django.setup()

from chatbot.models import Media, FileTypeChoices


def get_file_extension(filename):
    """
    Extract file extension from filename
    """
    if not filename:
        return None

    ext = os.path.splitext(filename)[1].lower()
    return ext.lstrip('.')


def get_media_type_from_extension(extension):
    """
    Map file extension to FileTypeChoices
    """
    if not extension:
        return None

    extension_mapping = {
        'pdf': FileTypeChoices.PDF,
        'doc': FileTypeChoices.DOC,
        'docx': FileTypeChoices.DOCX,
        'txt': FileTypeChoices.TXT,
        'csv': FileTypeChoices.CSV,
        'xls': FileTypeChoices.XLS,
        'xlsx': FileTypeChoices.XLSX,
    }

    return extension_mapping.get(extension.lower())


def analyze_media_types():
    """
    Analyze all media to find mismatches between file extension and media_type
    """
    all_media = Media.objects.all()
    total_count = all_media.count()

    mismatch_list = []
    no_file_list = []
    unknown_extension_list = []
    correct_count = 0

    print(f"Analyzing {total_count} media objects...")
    print("-" * 50)

    for media in all_media:
        if not media.file:
            no_file_list.append({
                'id': media.id,
                'name': media.name,
                'stored_type': media.media_type
            })
            continue

        filename = media.file.name.split('/')[-1]
        file_extension = get_file_extension(filename)

        if not file_extension:
            no_file_list.append({
                'id': media.id,
                'name': media.name,
                'stored_type': media.media_type,
                'filename': filename
            })
            continue

        expected_media_type = get_media_type_from_extension(file_extension)

        if not expected_media_type:
            unknown_extension_list.append({
                'id': media.id,
                'name': media.name,
                'extension': file_extension,
                'stored_type': media.media_type
            })
            continue

        if media.media_type != expected_media_type:
            mismatch_list.append({
                'id': media.id,
                'name': media.name,
                'filename': filename,
                'file_extension': file_extension,
                'stored_type': media.media_type,
                'expected_type': expected_media_type
            })
        else:
            correct_count += 1

    return {
        'total': total_count,
        'correct': correct_count,
        'mismatches': mismatch_list,
        'no_file': no_file_list,
        'unknown_extension': unknown_extension_list
    }


def print_analysis_results(results):
    """
    Display analysis results in formatted output
    """
    print(f"Total media objects: {results['total']}")
    print(f"Correct media types: {results['correct']}")
    print(f"Mismatched media types: {len(results['mismatches'])}")
    print(f"No file attached: {len(results['no_file'])}")
    print(f"Unknown extensions: {len(results['unknown_extension'])}")
    print("=" * 50)


def fix_single_media_type(media_info):
    """
    Fix media type for a single media object
    """
    try:
        # media = Media.objects.get(id=media_info['id'])
        # old_type = media.media_type
        # media.media_type = media_info['expected_type']
        # media.save()
        media_id = media_info['id']
        new_type = media_info['expected_type']

        media = Media.objects.only('id', 'media_type').get(id=media_id)
        old_type = media.media_type

        if old_type == new_type:
            return True, "No change needed"

        Media.objects.filter(id=media_id).update(
            media_type=new_type
        )

        return True, f"Changed from {old_type} to {media_info['expected_type']}"

    except Exception as e:
        return False, str(e)


def fix_media_types():
    """
    Main function to analyze and fix media type mismatches
    """
    results = analyze_media_types()
    print_analysis_results(results)

    if len(results['mismatches']) == 0:
        print("No mismatches found! All media types are correct.")
        return

    print(f"\nStarting correction for {len(results['mismatches'])} mismatched files...")
    print("-" * 50)

    success_list = []
    error_list = []

    for i, media_info in enumerate(results['mismatches'], 1):
        print(f"[{i}/{len(results['mismatches'])}] Fixing: {media_info['name']} (ID: {media_info['id']})")
        print(f"  File: {media_info['filename']} (.{media_info['file_extension']})")
        print(f"  Stored: {media_info['stored_type']} → Expected: {media_info['expected_type']}")

        success, message = fix_single_media_type(media_info)

        if success:
            print(f"  ✓ {message}")
            success_list.append({
                'id': media_info['id'],
                'name': media_info['name'],
                'old_type': media_info['stored_type'],
                'new_type': media_info['expected_type']
            })
        else:
            print(f"  ✗ Error: {message}")
            error_list.append({
                'id': media_info['id'],
                'name': media_info['name'],
                'error': message
            })

    print("-" * 50)
    print(f"Complete! Success: {len(success_list)}, Errors: {len(error_list)}")
    print("=" * 50)

    if success_list:
        print(f"\n✓ SUCCESSFULLY FIXED ({len(success_list)}):")
        for item in success_list:
            print(f"  - ID {item['id']}: {item['name']}")
            print(f"    Changed: {item['old_type']} → {item['new_type']}")

    if error_list:
        print(f"\n✗ FAILED ({len(error_list)}):")
        for item in error_list:
            print(f"  - ID {item['id']}: {item['name']}")
            print(f"    Error: {item['error']}")

    if results['no_file']:
        print(f"\n⚠ NO FILE ATTACHED ({len(results['no_file'])}):")
        for item in results['no_file']:
            print(f"  - ID {item['id']}: {item['name']} (Type: {item['stored_type']})")

    if results['unknown_extension']:
        print(f"\n⚠ UNKNOWN EXTENSIONS ({len(results['unknown_extension'])}):")
        for item in results['unknown_extension']:
            print(f"  - ID {item['id']}: {item['name']}")
            print(f"    Extension: .{item['extension']} (Type: {item['stored_type']})")

    print("=" * 50)


# if __name__ == "__main__":
#     fix_media_types()
