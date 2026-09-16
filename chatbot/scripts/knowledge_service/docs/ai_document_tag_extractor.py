import docx
from typing import List, Dict
from jinja2 import Template
import json_repair
from chatbot.llm_models.llm_script import handle_bedrock_model
import PyPDF2
import pandas as pd


def extract_text_from_file(file, file_extension: str) -> str:
    """
    Extract text content from various file types

    Args:
        file: File object (Django UploadedFile or similar)
        file_extension: File extension (pdf, doc, docx, txt, csv, xls, xlsx)

    Returns:
        Extracted text as string
    """
    try:
        file_extension = file_extension.lower().strip('.')

        if file_extension == 'pdf':
            # Extract text from PDF
            pdf_reader = PyPDF2.PdfReader(file)
            text_parts = []
            for page_num in range(len(pdf_reader.pages)):
                page = pdf_reader.pages[page_num]
                text_parts.append(page.extract_text())
            return '\n'.join(text_parts)

        elif file_extension in ['doc', 'docx']:
            # Extract text from Word document
            doc = docx.Document(file)
            text_parts = []
            for para in doc.paragraphs:
                if para.text.strip():
                    text_parts.append(para.text)
            return '\n'.join(text_parts)

        elif file_extension == 'txt':
            # Extract text from plain text file
            content = file.read()
            if isinstance(content, bytes):
                content = content.decode('utf-8', errors='ignore')
            return content

        elif file_extension == 'csv':
            # Extract text from CSV
            df = pd.read_csv(file)
            # Convert dataframe to string representation
            return df.to_string()

        elif file_extension in ['xls', 'xlsx']:
            # Extract text from Excel
            df = pd.read_excel(file)
            # Convert dataframe to string representation
            return df.to_string()

        else:
            # Try to read as text for unknown file types
            content = file.read()
            if isinstance(content, bytes):
                content = content.decode('utf-8', errors='ignore')
            return content

    except Exception as e:
        print(f"Error extracting text from file: {e}")
        return ""


def extract_tags_with_bedrock(document_text: str, company_bot) -> Dict[str, List[str]]:
    """
    Extract tags using Bedrock model

    Args:
        document_text: Full document content
        company_bot: Company bot object for Bedrock model

    Returns:
        Dictionary with extracted tags and classifications
    """
    try:
        print("Attempting Bedrock model extraction...")

        if len(document_text) > 8000:
            document_text = document_text[:8000] + "..."

        system_prompt = [
            {
                'text': company_bot.context
            },
        ]
        tag_context = company_bot.tag_context
        if not tag_context:
            return {'tags': [], 'classification': []}

        context_data = {
            "document_text": document_text,
        }
        template = Template(tag_context)
        tag_context = template.render(context_data)

        messages = [{
            'role': 'user',
            'content': [{'text': f"{tag_context}"}]
        }]

        tool = company_bot.tool_context
        if tool and isinstance(tool, str):
            tool = json_repair.repair_json(tool, return_objects=True)

        response = handle_bedrock_model(
            system_prompt=system_prompt, messages=messages, model_name=company_bot.llm_model,
            temperature=company_bot.bot_temperature, max_token=company_bot.max_token, company_bot=company_bot,
            tools=tool
        )

        print("response: ", response)
        print("type: response: ", type(response))

        if response and isinstance(response, dict):
            extracted_data = response.pop("parameters", response.pop("input", None))
            if extracted_data and isinstance(extracted_data, dict):
                response.clear()
                response.update(extracted_data)
            print("last response: ", response)
            print("last type: response: ", type(response))
            return response
        else:
            result = {'tags': [], 'classification': []}

        print(f"Bedrock extraction successful: {result}")
        return {
            'tags': result.get('tags', []),
            'classification': result.get('classification', [])
        }

    except Exception as e:
        print(f"Bedrock extraction failed: {str(e)}")
        return {'tags': [], 'classification': []}


def extract_tags_from_document_file(file, file_extension: str, company_bot) -> Dict[str, List[str]]:
    """
    Extract tags/classification from document file using AI

    Args:
        file: File object
        file_extension: File extension (pdf, doc, docx, txt, csv, xls, xlsx)
        company_bot: Company bot object for Bedrock model

    Returns:
        Dictionary with extracted tags and classifications
    """
    try:
        print(f"Processing file with extension: {file_extension}")

        # Extract text from file
        document_text = extract_text_from_file(file, file_extension)

        if not document_text:
            print("Could not extract text from file")
            return {'tags': [], 'classification': []}

        print(f"Extracted {len(document_text)} characters from file")

        # Extract tags using Bedrock
        ai_result = extract_tags_with_bedrock(document_text, company_bot)

        if ai_result and (ai_result.get('tags') or ai_result.get('classification')):
            print("Bedrock extraction successful")
            return ai_result

        # If extraction fails, return empty
        print("Tag extraction failed, returning empty results")
        return {'tags': [], 'classification': []}

    except Exception as e:
        print(f"Error extracting tags from file: {e}")
        return {'tags': [], 'classification': []}


def get_tags_list_from_file(file, file_extension: str, company_bot) -> List[str]:
    """
    Get tags as a clean list from file

    Args:
        file: File object
        file_extension: File extension
        company_bot: Company bot object for Bedrock

    Returns:
        List of clean tags found in the document
    """
    result = extract_tags_from_document_file(file, file_extension, company_bot)

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


def get_classification_list_from_file(file, file_extension: str, company_bot) -> List[str]:
    """
    Get classification items as a clean list from file

    Args:
        file: File object
        file_extension: File extension
        company_bot: Company bot object for Bedrock

    Returns:
        List of clean classification items
    """
    result = extract_tags_from_document_file(file, file_extension, company_bot)
    return result.get('classification', [])


# Enhanced one-liner functions
def extract_tags(file, file_extension: str, company_bot) -> List[str]:
    """One-liner to extract clean tags from file"""
    return get_tags_list_from_file(file, file_extension, company_bot)


def extract_classification(file, file_extension: str, company_bot) -> List[str]:
    """One-liner to extract clean classification from file"""
    return get_classification_list_from_file(file, file_extension, company_bot)


# Main function to use
def get_doc_tags_from_ai(file, file_extension, company_bot):
    """
    Extract auto tags from file using AI

    Args:
        file: File object (Django UploadedFile or similar)
        file_extension: File extension (pdf, doc, docx, txt, csv, xls, xlsx)
        company_bot: Company bot object with Bedrock configuration

    Returns:
        List of extracted tags
    """
    auto_tags = get_tags_list_from_file(file, file_extension, company_bot)
    print(f"Tags: {auto_tags}")
    return auto_tags
