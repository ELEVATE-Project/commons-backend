import json
import logging
from typing import Dict, Any, List
from jinja2 import Template
import json_repair
from chatbot.llm_models.llm_script import handle_bedrock_model
import os
from chatbot.utils.knowledge_service.base.extraction_utils import find_explicit_tag_sections

logger = logging.getLogger('django')


class AIContentProcessor:
    """Handles content extraction using AWS Bedrock LLM"""

    def __init__(self, main_doc_max_chars: int = 3000):
        self.main_doc_max_chars = main_doc_max_chars

    def create_default_response(self, document_text: str = "",
                                extracted_images: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Create default response structure
        """
        return {
            "title": "",
            "organization": "",
            "tags": [],
            "exact_content": document_text,  # Always preserve content
            "summary": "",
            "document_type": "",
            "key_entities": [],
            "url": [],
            "subdocument": [],
            "images": extracted_images or []
        }

    def validate_and_enhance_result(self, result: Dict[str, Any],
                                    document_text: str) -> Dict[str, Any]:
        """
        Validate and enhance the extracted result
        """
        # Ensure all required fields exist
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
            "images": []
        }

        for key in default_response:
            if key not in result:
                result[key] = default_response[key]

        # Ensure exact_content is preserved
        if not result.get('exact_content'):
            result['exact_content'] = document_text

        # Find explicit tag sections
        explicit_tag_sections = find_explicit_tag_sections(document_text)

        # Validate tags
        if result.get('tags'):
            validated_tags = []
            for tag in result['tags']:
                if isinstance(tag, str):
                    # Try to parse as JSON first
                    try:
                        parsed_tag = json_repair.repair_json(tag, return_objects=True)
                        if isinstance(parsed_tag, dict) and 'text' in parsed_tag:
                            # Successfully parsed as tag dict
                            validated_tags.append(parsed_tag)
                        else:
                            # Not a valid tag dict, treat as plain string
                            validated_tags.append({"text": tag, "source": "generated"})
                    except:
                        # Failed to parse as JSON, treat as plain string
                        validated_tags.append({"text": tag, "source": "generated"})
                elif isinstance(tag, dict) and 'text' in tag:
                    # Already a proper dict with text field
                    validated_tags.append(tag)
            result['tags'] = validated_tags

        # Ensure minimum content quality
        if not result.get('title') or len(result['title'].strip()) < 3:
            content_words = document_text.split()[:10]
            result['title'] = ' '.join(content_words).strip() + '...' if content_words else 'Untitled Document'

        return result

    def extract_basic_content(self, document_text: str, company_bot,
                              extracted_images: List[Dict[str, Any]] = None,
                              other_data: dict = None, is_subdoc: bool = False) -> Dict[str, Any]:
        """
        Extract basic content using Bedrock
        """
        default_response = self.create_default_response(document_text, extracted_images)

        try:
            logger.info("Processing content with Bedrock...")
            logger.info(f"Passing Text to llm: {document_text}")

            # Preserve complete content
            complete_content = document_text

            system_prompt = [
                {
                    'text': company_bot.context
                },
            ]

            tool_context_data = json_repair.repair_json(
                company_bot.tool_context, return_objects=True
            ) if isinstance(company_bot.tool_context, str) else company_bot.tool_context

            if isinstance(tool_context_data, list) and len(tool_context_data) > 0:
                tool_context_data = tool_context_data[0]

            end_context = company_bot.end_context

            if not end_context:
                print("Early return due to no data in end context value.")
                logger.error("Early return due to no data in end context value.")
                default_response['exact_content'] = complete_content
                return default_response

            master_document_types = None
            if company_bot and hasattr(company_bot, 'other_params') and company_bot.other_params:
                try:
                    other_params = json_repair.repair_json(
                        company_bot.other_params, return_objects=True
                    ) if isinstance(company_bot.other_params, str) else company_bot.other_params
                    master_document_types = other_params.get('master_document_types', [])
                except Exception as e:
                    print(f"Error parsing master_document_types: {e}")
                    logger.error(f"Error parsing master_document_types: {e}")
                    default_response['exact_content'] = complete_content
                    return default_response

            # Create analysis version if text is too long
            analysis_text = document_text
            max_analysis_chars = self.main_doc_max_chars

            if len(document_text) > max_analysis_chars:
                first_part = document_text[:max_analysis_chars // 2]
                last_part = document_text[-(max_analysis_chars // 2):]
                analysis_text = first_part + f"\n\n[SAMPLE - Full: {len(document_text)} chars]\n\n" + last_part

            # Include image information in context if available
            image_context = ""
            if extracted_images:
                image_context = f"\n\nDocument contains {len(extracted_images)} embedded images."

            context_data = {
                "document_text": analysis_text,
                "extracted_images": extracted_images,
                "master_tags": other_data.get('master_tag', None) if other_data else None,
                "master_document_types": master_document_types
            }

            template = Template(end_context)
            end_context = template.render(context_data)
            logger.info(f"Updated Tag Context: \n {end_context}")

            messages = [{
                'role': 'user',
                'content': [{'text': f"{end_context}"}]
            }]

            print("Bedrock: Extraction call started.")
            response = handle_bedrock_model(
                system_prompt=system_prompt,
                messages=messages,
                model_name=company_bot.llm_model,
                temperature=company_bot.bot_temperature,
                max_token=company_bot.max_token,
                company_bot=company_bot,
                tools=tool_context_data,
                aws_key=os.getenv('SG_REPO_AWS_ACCESS_KEY_ID'),
                aws_secret_key=os.getenv('SG_REPO_AWS_SECRET_ACCESS_KEY')
            )
            logger.info(f"Bedrock response type: {type(response)}")
            logger.info("Bedrock response:\n%s", json.dumps(response, indent=2))
            print(f"Bedrock response type: {type(response)}")
            print("--------\n\n")

            # Enhanced response type validation
            if not isinstance(response, dict):
                error_msg = ("AI processing failed - unable to extract structured data from document. "
                             "Please try uploading the file again.")
                logger.error(
                    f"LLM returned unexpected response type: {type(response)}. Expected dictionary. "
                    f"Response preview: {str(response)[:200] if response else 'None'}")

                if not is_subdoc:
                    # For main document, this is a critical error - stop processing
                    raise ValueError(error_msg)
                else:
                    # For subdocument, handle gracefully
                    default_response['exact_content'] = complete_content
                    default_response['extraction_error'] = error_msg
                    default_response['error'] = error_msg
                    default_response['error_type'] = 'ai_processing_failed'
                    default_response['title_extraction_failed'] = True
                    return default_response

            # Extract the actual data from response
            extracted_data = response.pop("parameters", response.pop("input", response))
            if not extracted_data or not isinstance(extracted_data, dict):
                error_msg = "AI processing failed - response structure is invalid. Please try uploading the file again."
                logger.error(
                    f"LLM response missing expected data structure. Response keys: {list(response.keys()) if response else 'None'}")

                if not is_subdoc:
                    raise ValueError(error_msg)

                default_response['exact_content'] = complete_content
                default_response['extraction_error'] = error_msg
                default_response['error'] = error_msg
                default_response['error_type'] = 'ai_processing_failed'
                default_response['title_extraction_failed'] = True
                return default_response

            # Preserve complete content
            extracted_data['exact_content'] = complete_content

            # Add images if available
            if extracted_images:
                extracted_data['images'] = extracted_images

            # Validate and enhance result
            result = self.validate_and_enhance_result(extracted_data, complete_content)

            if not result.get('title') or not result['title'].strip():
                error_msg = f"AI failed to extract title for {'subdocument' if is_subdoc else 'main document'}"
                logger.error(error_msg)
                if is_subdoc:
                    result['extraction_error'] = error_msg
                    result['error'] = error_msg
                    result['error_type'] = 'title_extraction_failed'
                    result['title_extraction_failed'] = True
                else:
                    # For main document, raise exception to stop processing
                    raise ValueError(error_msg)

            logger.info("Bedrock extraction successful")
            return result

        except ValueError as ve:
            # Re-raise ValueError for main document processing failures
            logger.error(f"LLM processing validation error: {str(ve)}")
            raise
        except Exception as e:
            error_msg = f"LLM processing failed with unexpected error: {str(e)}"
            logger.error(error_msg)
            default_response['exact_content'] = document_text
            if not is_subdoc:
                # For main document, raise the exception to stop processing
                raise ValueError(error_msg)
            else:
                # For subdocument, handle gracefully
                default_response['extraction_error'] = error_msg
                default_response['error'] = error_msg
                default_response['error_type'] = 'ai_processing_failed'
                default_response['title_extraction_failed'] = True
                return default_response