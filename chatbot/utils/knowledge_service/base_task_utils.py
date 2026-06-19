import os
from chatbot.models import FileTypeChoices
import hashlib
import requests


def determine_media_type_from_url(source_url, parent_media=None):
    """
    Determine media type and filename from URL response.
    """
    response = None
    try:
        # Download the source document
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        }

        # Convert Google URLs to downloadable format
        download_url = source_url
        if 'docs.google.com/document' in source_url and '/d/' in source_url:
            doc_id = source_url.split('/d/')[1].split('/')[0]
            download_url = f"https://docs.google.com/document/d/{doc_id}/export?format=docx"
        elif 'docs.google.com/spreadsheets' in source_url and '/d/' in source_url:
            sheet_id = source_url.split('/d/')[1].split('/')[0]
            download_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
        elif 'drive.google.com/file/d/' in source_url:
            file_id = source_url.split('/d/')[1].split('/')[0]
            download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
            print(f"Converting Google Drive URL: {source_url} -> {download_url}")

        response = requests.get(download_url, headers=headers, timeout=30, allow_redirects=True)
        response.raise_for_status()

        # Default values
        if parent_media:
            parent_name_without_ext = os.path.splitext(parent_media.name)[0]
        else:
            parent_name_without_ext = "document"

        url_hash = hashlib.md5(source_url.encode()).hexdigest()[:6]
        filename = f"linked_doc_{parent_name_without_ext}_{url_hash}"
        media_type = FileTypeChoices.TXT.value

        # Check content type first
        content_type = response.headers.get('content-type', '').lower()

        # FIXED: Determine file type from content-type header (after proper download URL)
        print(f"Content-Type: {content_type}")

        # Detect file type from content-type header
        if 'application/pdf' in content_type:
            media_type = FileTypeChoices.PDF.value
            filename = f"source_doc_{parent_name_without_ext}_{url_hash}.pdf"
        elif 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' in content_type:
            media_type = FileTypeChoices.DOCX.value
            filename = f"source_doc_{parent_name_without_ext}_{url_hash}.docx"
        elif 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' in content_type:
            media_type = FileTypeChoices.XLSX.value
            filename = f"source_doc_{parent_name_without_ext}_{url_hash}.xlsx"
        elif 'application/msword' in content_type:
            media_type = FileTypeChoices.DOC.value if hasattr(FileTypeChoices, 'DOC') else FileTypeChoices.DOCX.value
            filename = f"source_doc_{parent_name_without_ext}_{url_hash}.doc"
        elif 'application/vnd.ms-excel' in content_type:
            media_type = FileTypeChoices.XLS.value if hasattr(FileTypeChoices, 'XLS') else FileTypeChoices.XLSX.value
            filename = f"source_doc_{parent_name_without_ext}_{url_hash}.xls"
        elif 'text/plain' in content_type:
            media_type = FileTypeChoices.TXT.value
            filename = f"source_doc_{parent_name_without_ext}_{url_hash}.txt"
        elif 'text/csv' in content_type:
            media_type = FileTypeChoices.CSV.value
            filename = f"source_doc_{parent_name_without_ext}_{url_hash}.csv"
        elif 'docs.google.com' in source_url:
            # Fallback for Google Docs URLs
            if 'document' in source_url:
                media_type = FileTypeChoices.DOCX.value
                filename = f"source_doc_{parent_name_without_ext}_{url_hash}.docx"
            elif 'spreadsheets' in source_url:
                media_type = FileTypeChoices.XLSX.value
                filename = f"source_doc_{parent_name_without_ext}_{url_hash}.xlsx"
        else:
            # Try content-disposition header first
            content_disposition = response.headers.get('content-disposition')
            if content_disposition:
                import re
                matches = re.findall('filename="?([^"]+)"?', content_disposition)
                if matches:
                    filename = matches[0]
                    # Get extension and determine type
                    ext = os.path.splitext(filename)[1].lower().strip('.')
                    if ext:
                        media_type = FileTypeChoices.get_mime_from_extension(ext) or FileTypeChoices.TXT.value
                    else:
                        # Filename without extension, try content-type
                        if 'application/pdf' in content_type:
                            media_type = FileTypeChoices.PDF.value
                            filename = f"{filename}.pdf"
                        else:
                            media_type = FileTypeChoices.TXT.value
                            filename = f"{filename}.txt"
            else:
                # Fallback: Default to PDF for unknown Google Drive files (most common)
                if 'drive.google.com' in source_url:
                    media_type = FileTypeChoices.PDF.value
                    filename = f"source_doc_{parent_name_without_ext}_{url_hash}.pdf"
                else:
                    media_type = FileTypeChoices.TXT.value
                    filename = f"source_doc_{parent_name_without_ext}_{url_hash}.txt"
    except Exception as e:
        print("error while determining media_type")
        return None, None, response

    print(f"Determined media_type: {media_type}, filename: {filename}")
    return media_type, filename, response
