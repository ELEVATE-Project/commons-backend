import re
import requests
import docx
import io
from typing import List, Dict


def extract_tags_from_document_sections(url: str) -> Dict[str, List[str]]:
    """
    Extract tags/classification directly from document sections with clean parsing

    Args:
        url: Document URL (Google Docs, DOCX, etc.)

    Returns:
        Dictionary with extracted tags and classifications (cleaned)
    """

    def get_document_paragraphs(url: str) -> List[str]:
        """Get all paragraphs from document"""

        def get_google_doc_text(doc_url: str) -> str:
            match = re.search(r'/document/d/([a-zA-Z0-9-_]+)', doc_url)
            if not match:
                raise ValueError("Invalid Google Docs URL")

            doc_id = match.group(1)
            export_url = f"https://docs.google.com/document/d/{doc_id}/export?format=txt"

            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            response = requests.get(export_url, headers=headers, timeout=30)
            response.raise_for_status()

            # Split into paragraphs
            return [p.strip() for p in response.text.split('\n') if p.strip()]

        def get_docx_paragraphs(content: bytes) -> List[str]:
            doc = docx.Document(io.BytesIO(content))
            paragraphs = []

            for para in doc.paragraphs:
                text = para.text.strip()
                if text:
                    paragraphs.append(text)

            return paragraphs

        try:
            if 'docs.google.com/document' in url:
                return get_google_doc_text(url)

            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            if url.lower().endswith(('.docx', '.doc')):
                return get_docx_paragraphs(response.content)
            else:
                # Treat as text
                return [p.strip() for p in response.text.split('\n') if p.strip()]

        except Exception as e:
            print(f"Error reading document: {e}")
            return []

    def find_section_content(paragraphs: List[str], section_keywords: List[str]) -> List[str]:
        """Find content under specific section headings"""

        content = []
        found_section = False

        for i, para in enumerate(paragraphs):
            para_lower = para.lower().strip()

            # Check if this paragraph is a section heading we're looking for
            is_section_header = False
            for keyword in section_keywords:
                if (keyword.lower() in para_lower and
                        len(para.split()) <= 5 and  # Short heading
                        (para_lower.startswith(keyword.lower()) or
                         para_lower.endswith(keyword.lower()) or
                         para_lower == keyword.lower())):
                    is_section_header = True
                    found_section = True
                    break

            if is_section_header:
                continue  # Skip the header itself

            # If we found our section, collect content until next major heading
            if found_section:
                # Check if this is a numbered section header (e.g., "12. Next Section")
                numbered_section = re.match(r'^\d+\.\s+\w+', para)

                # Only stop if we hit a numbered section that looks like a major heading
                if numbered_section and len(para) > 15:  # Longer numbered sections are likely new sections
                    break

                # Or stop if line ends with colon and has section keywords (but not list items)
                if (para.endswith(':') and
                        not re.match(r'^\s*[\-\*•\[\]x\s]', para) and
                        any(keyword in para_lower for keyword in
                            ['section', 'chapter', 'part', 'instructions', 'purpose',
                             'overview', 'background', 'audience', 'intended users',
                             'complementary resources', 'limitations', 'alignment'])):
                    break

                # Add content from this section
                content.append(para)

        return content

    def parse_list_content(content_lines: List[str]) -> List[str]:
        """Parse content lines into clean list items - FIXED VERSION"""

        # Define all possible checkbox/checkmark indicators
        CHECKBOX_MARKERS = [
            '[x]', '[X]', '[ ]', '✅', '☑️', '✓', '✔', '☒', '☐', '⬜', '🔲', '🔳',
        ]

        # Build regex pattern from markers
        # Escape special regex characters in markers
        escaped_markers = [re.escape(marker) for marker in CHECKBOX_MARKERS]
        markers_pattern = '|'.join(escaped_markers)

        items = []

        for line in content_lines:
            line = line.strip()
            if not line:
                continue

            # Check if line contains any of our markers
            if any(marker in line for marker in CHECKBOX_MARKERS):
                # Find all checkbox patterns in the line
                # Pattern matches: optional bullet + optional space + (any marker) + space + (capture everything until another marker or end)
                # Using negative lookahead to stop before next marker
                checkbox_pattern = rf'[\-\*•]?\s*(?:{markers_pattern})\s*([^✅☑️✓✔☒☐⬜🔲🔳\[\]]+?)(?=[\-\*•]?\s*(?:{markers_pattern})|$)'
                matches = re.findall(checkbox_pattern, line, re.IGNORECASE)
                for match in matches:
                    item = match.strip()
                    if item:
                        items.append(item)
                if matches:  # If we found matches, continue to next line
                    continue

            # Handle other list formats...

            # Format 1: Bullet points: - item, • item, * item
            bullet_match = re.match(r'^\s*[\-\*•]\s*(.+)', line)
            if bullet_match:
                item = bullet_match.group(1).strip()
                # Remove any markers from the item
                item = re.sub(rf'(?:{markers_pattern})\s*', '', item, flags=re.IGNORECASE).strip()
                if item:
                    items.append(item)
                continue

            # Format 2: Numbered lists: 1. item, 1) item
            number_match = re.match(r'^\s*\d+[.)]\s*(.+)', line)
            if number_match:
                item = number_match.group(1).strip()
                # Remove any markers from the item
                item = re.sub(rf'(?:{markers_pattern})\s*', '', item, flags=re.IGNORECASE).strip()
                if item:
                    items.append(item)
                continue

            # Format 3: Comma/semicolon separated in single line
            has_markers = any(marker in line for marker in CHECKBOX_MARKERS)
            if (',' in line or ';' in line) and not has_markers and not any(marker in line for marker in ['-', '*']):
                sub_items = re.split(r'[,;]', line)
                for sub_item in sub_items:
                    clean_item = sub_item.strip()
                    if clean_item:
                        items.append(clean_item)
                continue

            # Format 4: Plain text item (if it doesn't look like a heading)
            if len(line.split()) <= 6 and line and not line.endswith(':'):
                # Remove any markers
                clean_line = re.sub(rf'(?:{markers_pattern})\s*', '', line, flags=re.IGNORECASE).strip()
                if clean_line:
                    items.append(clean_line)

        # Final cleanup of items
        cleaned_items = []
        for item in items:
            # Remove extra whitespace
            clean_item = re.sub(r'\s+', ' ', item).strip()
            # Remove leading/trailing punctuation
            clean_item = clean_item.strip('.,;:-')
            # Remove any remaining markers
            clean_item = re.sub(rf'(?:{markers_pattern})', '', clean_item, flags=re.IGNORECASE).strip()

            if clean_item and len(clean_item) > 1:
                cleaned_items.append(clean_item)

        return cleaned_items

    # Main extraction logic
    try:
        print(f"Reading document: {url}")

        # Get all paragraphs from document
        paragraphs = get_document_paragraphs(url)
        print(f"Found {len(paragraphs)} paragraphs")

        result = {}

        # Look for Tags section (including "Tags / Classification")
        tag_keywords = ['tags', 'tag', 'keywords', 'labels', 'tags / classification', 'classification']
        tag_content = find_section_content(paragraphs, tag_keywords)
        if tag_content:
            result['tags'] = parse_list_content(tag_content)
            print(f"Found tags section with {len(result['tags'])} items: {result['tags']}")

        # Look for Classification section separately
        classification_keywords = ['classification', 'category', 'categories', 'type', 'types']
        classification_content = find_section_content(paragraphs, classification_keywords)
        if classification_content:
            result['classification'] = parse_list_content(classification_content)
            print(
                f"Found classification section with {len(result['classification'])} items: {result['classification']}")

        return result

    except Exception as e:
        print(f"Error extracting sections: {e}")
        return {}


def get_tags_list(url: str) -> List[str]:
    """
    Simple function to get just the tags as a clean list

    Args:
        url: Document URL

    Returns:
        List of clean tags found in the document
    """

    result = extract_tags_from_document_sections(url)

    # Combine tags and classification into one list
    all_tags = []

    if 'tags' in result:
        all_tags.extend(result['tags'])

    if 'classification' in result:
        all_tags.extend(result['classification'])

    # Remove duplicates while preserving order
    unique_tags = []
    seen = set()
    for tag in all_tags:
        if tag.lower() not in seen:
            unique_tags.append(tag)
            seen.add(tag.lower())

    return unique_tags


def get_classification_list(url: str) -> List[str]:
    """
    Get just the classification items as a clean list

    Args:
        url: Document URL

    Returns:
        List of clean classification items
    """

    result = extract_tags_from_document_sections(url)
    return result.get('classification', [])


# Simple one-liner functions
def extract_tags(url: str) -> List[str]:
    """One-liner to extract clean tags from document"""
    return get_tags_list(url)


def extract_classification(url: str) -> List[str]:
    """One-liner to extract clean classification from document"""
    return get_classification_list(url)


# Test function with your exact format
def test_checkbox_parsing():
    """Test the fixed parsing logic"""

    # Test cases that match your document format
    test_lines = [
        "- [x] Classroom Culture",
        "- [x] Systems Change",
        "- [x] FLN",
        "[x] M&E",
        "[x] Tools",
        "[ ] School Leadership",
        "- Tool/Artifact",
        "- Template"
    ]

    # print("Testing checkbox parsing:")

    # Test the parse_list_content function
    def test_parse_list_content(content_lines):
        items = []

        for line in content_lines:
            line = line.strip()
            if not line:
                continue

            # Enhanced parsing logic

            # Format 1: Checkbox with bullet: - [x] item
            checkbox_with_bullet = re.match(r'^\s*[\-\*•]\s*\[[x\s]\]\s*(.+)', line, re.IGNORECASE)
            if checkbox_with_bullet:
                item = checkbox_with_bullet.group(1).strip()
                items.append(item)
                continue

            # Format 2: Direct checkbox: [x] item
            direct_checkbox = re.match(r'^\s*\[[x\s]\]\s*(.+)', line, re.IGNORECASE)
            if direct_checkbox:
                item = direct_checkbox.group(1).strip()
                items.append(item)
                continue

            # Format 3: Simple bullet: - item
            bullet_match = re.match(r'^\s*[\-\*•]\s*(.+)', line)
            if bullet_match:
                item = bullet_match.group(1).strip()
                # Remove any remaining checkbox markers
                clean_item = re.sub(r'\[[x\s]\]\s*', '', item, flags=re.IGNORECASE).strip()
                items.append(clean_item)
                continue

            # Plain text
            if line:
                clean_item = re.sub(r'\[[x\s]\]\s*', '', line, flags=re.IGNORECASE).strip()
                items.append(clean_item)

        return items

    result = test_parse_list_content(test_lines)


def get_tag_from_doc(file_url):
    # Test the parsing logic first
    # print("Testing improved parsing logic:")
    test_checkbox_parsing()

    # print("\n" + "="*60)

    # Test with your actual document
    # print(f"\nExtracting from document: {test_url}")

    # Get clean extraction results
    # tags = get_tags_list(test_url)
    # print(f"Clean Tags: {tags}")

    classification = get_classification_list(file_url)
    print(f"Clean Classification: {classification}")
    return classification
