from chatbot.models import FileTypeChoices


def get_media_type_from_ai_data(document_type):
    """Map AI-detected document type to our media type choices"""
    if isinstance(document_type, dict):
        doc_type_text = document_type.get('type', '')
    else:
        doc_type_text = document_type or ''

    if not doc_type_text:
        return FileTypeChoices.TXT.value

    if doc_type_text and doc_type_text != '':
        doc_type_text = doc_type_text.lower()
    type_mapping = {
        'report': FileTypeChoices.PDF,
        'spreadsheet': FileTypeChoices.XLSX,
        'document': FileTypeChoices.DOCX,
        'text': FileTypeChoices.TXT,
        'csv': FileTypeChoices.CSV,
        'excel': FileTypeChoices.XLSX,
        'word': FileTypeChoices.DOCX,
        'pdf': FileTypeChoices.PDF
    }

    for key, value in type_mapping.items():
        if key in doc_type_text:
            return value.value
    return FileTypeChoices.TXT.value


def build_key_values(data_dict):
    """Build key-value pairs from document data with metadata tracking"""
    key_values = []
    array_fields_metadata = []  # Track which fields were originally arrays

    if data_dict.get('title'):
        key_values.append({'key': 'TITLE', 'value': str(data_dict['title']), 'source': 'ai'})

    organization_value = data_dict.get('organization', '')
    key_values.append({'key': 'ORGANIZATION', 'value': str(organization_value), 'source': 'ai'})

    # ADD GEOGRAPHY HANDLING
    geography_value = data_dict.get('geography', '')
    if geography_value:
        key_values.append({'key': 'GEOGRAPHY', 'value': str(geography_value), 'source': 'ai'})

    document_type = data_dict.get('document_type')
    if document_type:
        if isinstance(document_type, dict):
            doc_type_value = document_type.get('type', '')
            if doc_type_value:
                doc_type_value = doc_type_value.title()
                key_values.append({'key': 'DOCUMENT_TYPE', 'value': str(doc_type_value), 'source': 'ai'})
        else:
            doc_type_value = document_type.title() if document_type else ''
            key_values.append({'key': 'DOCUMENT_TYPE', 'value': str(doc_type_value), 'source': 'ai'})

    if data_dict.get('key_entities') and len(data_dict['key_entities']) > 0:
        key_values.append({'key': 'KEY ENTITIES', 'value': ', '.join(map(str, data_dict['key_entities'])), 'source': 'ai'})

    # ENHANCED: Handle structured content with proper array formatting
    if data_dict.get('structured_content') and isinstance(data_dict['structured_content'], dict):
        for heading, content in data_dict['structured_content'].items():
            if heading.upper() in [
                'BASIC INFORMATION', 'GENERAL INFORMATION', 'TAGS', 'KEYWORDS',
                'CATEGORIES', 'CLASSIFICATION', 'TAGS FOR CLASSIFICATION'
            ]:
                continue

            key_name = heading.upper()

            # Format arrays as multi-line strings with bullet points
            if isinstance(content, list):
                # Track that this field was originally an array
                array_fields_metadata.append(key_name)

                # Ensure all list items are strings
                string_items = [str(item) for item in content if item is not None]
                formatted_content = '\n'.join([f"• {item}" for item in string_items])
                key_values.append({
                    'key': key_name,
                    'value': formatted_content,
                    'original_type': 'array',
                    'source': 'ai'  # Mark as AI-extracted
                })
            else:
                # Handle text that might already be formatted
                content_str = str(content) if content is not None else ''
                key_values.append({
                    'key': key_name,
                    'value': content_str,
                    'original_type': 'string',
                    'source': 'ai'  # Mark as AI-extracted
                })

    return key_values, array_fields_metadata