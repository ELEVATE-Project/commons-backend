"""Main module providing the public API for document extraction"""

import json
import logging
from typing import Dict, Any
from chatbot.utils.knowledge_service.extractor.document_extractor import DocumentExtractor
from chatbot.utils.knowledge_service.base.extraction_config import parse_extractor_config

logger = logging.getLogger('django')


def extract_tags_from_document_url(url: str, company_bot) -> Dict[str, Any]:
    """
    Extract structured information from document URL
    """
    default_response = {
        "title": "",
        "organization": "",
        "tags": [],
        "exact_content": "",
        "summary": "",
        "document_type": "",
        "key_entities": [],
        "url": [],
        "subdocument": [],
        "source_document": [],
        "images": [],
        "media_type": None
    }

    try:
        # Parse configuration from company_bot
        extractor_config = parse_extractor_config(company_bot)

        # Create extractor instance
        extractor = DocumentExtractor(**extractor_config)

        # Process document
        result = extractor.process_document_from_url(url, company_bot)
        return result

    except Exception as e:
        logger.error(f"Error extracting tags from URL: {e}")
        return default_response


def extract_tags_from_document_file(file, company_bot, file_extension, other_data):
    """
    Extract structured information from document file
    """
    default_response = {
        "title": "",
        "organization": "",
        "tags": [],
        "exact_content": "",
        "summary": "",
        "document_type": "",
        "key_entities": [],
        "url": [],
        "subdocument": [],
        "source_document": [],
        "images": [],
        "media_type": None
    }

    try:
        # Parse configuration from company_bot
        extractor_config = parse_extractor_config(company_bot)

        # Validate file size
        max_file_size_mb = extractor_config.get('max_file_size_mb', 50)
        max_file_size_bytes = max_file_size_mb * 1024 * 1024
        file_size = 0

        if hasattr(file, 'size'):
            file_size = file.size
        elif hasattr(file, 'seek') and hasattr(file, 'tell'):
            current_position = file.tell()
            file.seek(0, 2)  # Seek to end
            file_size = file.tell()
            file.seek(current_position)

        if file_size > max_file_size_bytes:
            file_size_mb = file_size / (1024 * 1024)
            error_msg = (f"File size ({file_size_mb:.2f} MB) exceeds the maximum allowed size "
                         f"of {max_file_size_mb} MB. Please reduce the file size.")
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Create extractor instance
        extractor = DocumentExtractor(**extractor_config)

        # Extract both limited and comprehensive content
        document_text, extracted_images, comprehensive_text_for_urls, media_type = extractor.extract_text_from_file(
            file, file_extension
        )

        if not document_text:
            return default_response

        # Pass comprehensive content in other_data
        if not other_data:
            other_data = {}
        other_data['comprehensive_text_for_urls'] = comprehensive_text_for_urls

        # Extract information using Bedrock with URL processing
        result = extractor.extract_with_llm(
            document_text, company_bot, extracted_images=extracted_images, other_data=other_data
        )

        if result and not result.get('media_type'):
            print(f"Assigning media_type {media_type} to result")
            result['media_type'] = media_type

        return result

    except ValueError as ve:
        error_message = str(ve)
        logger.error(f"Processing error: {error_message}")

        # Return error response instead of default_response
        error_response = {
            "error": error_message,
            "title": "",
            "organization": "",
            "tags": [],
            "exact_content": "",
            "summary": "",
            "document_type": "",
            "key_entities": [],
            "url": [],
            "subdocument": [],
            "source_document": [],
            "images": [],
            "media_type": None
        }

        # Distinguish between different types of ValueError
        if "file size" in error_message.lower() or "exceeds the maximum allowed size" in error_message.lower():
            # File size validation error
            error_response["error_type"] = "file_size_exceeded"
        elif "llm returned" in error_message.lower() or "unexpected list format" in error_message.lower() or "plain text instead" in error_message.lower():
            # LLM response format error
            error_response["error_type"] = "llm_response_format_error"
        elif "failed to extract title" in error_message.lower():
            # Title extraction error
            error_response["error_type"] = "title_extraction_error"
        elif "processing failed with unexpected error" in error_message.lower():
            # LLM processing error
            error_response["error_type"] = "llm_processing_error"
        else:
            # Generic validation error
            error_response["error_type"] = "validation_error"

        return error_response

    except Exception as e:
        # Handle any other unexpected errors
        error_message = f"Unexpected error during document processing: {str(e)}"
        logger.error(error_message)
        return {
            "error": error_message,
            "error_type": "unexpected_error",
            "title": "",
            "organization": "",
            "tags": [],
            "exact_content": "",
            "summary": "",
            "document_type": "",
            "key_entities": [],
            "url": [],
            "subdocument": [],
            "source_document": [],
            "images": []
        }


def get_doc_tags_from_ai(file, company_bot, file_extension, other_data):
    """
    Main entry point for document processing with improved error handling
    """
    try:
        result = extract_tags_from_document_file(file, company_bot, file_extension, other_data)
        print("Final result: ", result)
        logger.info("Final Extraction Result:\n%s", json.dumps(result, indent=2, ensure_ascii=False))
        return result

    except ValueError as ve:
        error_message = str(ve)
        logger.error(f"Processing error: {error_message}")

        # Common error response for all AI processing failures
        if any(keyword in error_message.lower() for keyword in [
            "ai processing failed", "unable to extract structured data",
            "llm returned", "unexpected", "processing failed"
        ]):
            return {
                "error": "AI processing failed - unable to extract structured data from document. Please try uploading the file again.",
                "error_type": "ai_processing_failed",
                "title": "",
                "organization": "",
                "tags": [],
                "exact_content": "",
                "summary": "",
                "document_type": "",
                "key_entities": [],
                "url": [],
                "subdocument": [],
                "source_document": [],
                "images": []
            }
        elif "file size" in error_message.lower() or "exceeds the maximum allowed size" in error_message.lower():
            # File size validation error
            return {
                "error": error_message,
                "error_type": "file_size_exceeded",
                "title": "",
                "organization": "",
                "tags": [],
                "exact_content": "",
                "summary": "",
                "document_type": "",
                "key_entities": [],
                "url": [],
                "subdocument": [],
                "source_document": [],
                "images": []
            }
        else:
            # Generic validation error
            return {
                "error": f"Document processing failed: {error_message}",
                "error_type": "validation_error",
                "title": "",
                "organization": "",
                "tags": [],
                "exact_content": "",
                "summary": "",
                "document_type": "",
                "key_entities": [],
                "url": [],
                "subdocument": [],
                "source_document": [],
                "images": []
            }

    except Exception as e:
        # Handle any other unexpected errors
        error_message = "AI processing failed - unable to extract structured data from document. Please try uploading the file again."
        logger.error(f"Unexpected error during document processing: {str(e)}")
        return {
            "error": error_message,
            "error_type": "ai_processing_failed",
            "title": "",
            "organization": "",
            "tags": [],
            "exact_content": "",
            "summary": "",
            "document_type": "",
            "key_entities": [],
            "url": [],
            "subdocument": [],
            "source_document": [],
            "images": []
        }