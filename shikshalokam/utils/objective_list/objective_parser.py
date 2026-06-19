from shikshalokam.utils.action_list.action_parser import unwrap_tool_values
from shikshalokam.utils.chunks_utils import normalize_source_id
import json_repair
import json
import logging

logger = logging.getLogger('django')


def normalize_objectives(objectives):
    """
    Normalizes objectives data.
    """
    if not objectives:
        raise ValueError("EMPTY_OBJECTIVES")

    if isinstance(objectives, str):
        try:
            objectives = json.loads(objectives)
        except Exception:
            try:
                objectives = json_repair.repair_json(
                    objectives, return_objects=True
                )
            except Exception:
                raise ValueError("OBJECTIVES_MALFORMED_JSON")

    return objectives


def validate_objectives(objectives):
    """
    Validates normalized objectives.
    """
    if not isinstance(objectives, list):
        raise ValueError("OBJECTIVES_NOT_LIST")

    if not objectives:
        raise ValueError("EMPTY_OBJECTIVES")

    for i, obj in enumerate(objectives):
        if not isinstance(obj, dict):
            raise ValueError(f"INVALID_OBJECTIVE_OBJECT_{i}")

        objective_text = obj.get("objective", obj.get("text", "")).strip()

        if not isinstance(objective_text, str) or not objective_text:
            raise ValueError(f"EMPTY_OBJECTIVE_TEXT_{i}")
        if objective_text.lower() in ("type", "value"):
            raise ValueError(f"INVALID_OBJECTIVE_TEXT_{i}")


def parse_llm_objective_response(response, filtered_chunks):
    """
    Parse LLM response into structured objective list with source validation.
    """
    try:
        print("llm response: ", response)
        if not response or not isinstance(response, dict):
            raise ValueError("INVALID_LLM_RESPONSE")

        if 'output' in response:
            content = response.get('output', {}).get('message', {}).get('content', [])
            if content and isinstance(content, list):
                for item in content:
                    if 'toolUse' in item:
                        tool_input = item['toolUse'].get('input', {})
                        if tool_input:
                            response = tool_input
                            break

        extracted_data = response.pop("parameters", response.pop("input", None))
        if extracted_data:
            extracted_data = unwrap_tool_values(extracted_data)
            response = extracted_data

        print("\nextracted_data: ", extracted_data)
        logger.info(f"extracted_data: {extracted_data}")

        objectives_from_response = (
                response.get('objectives') or
                response.get('objective_list') or
                response.get('objective') or
                []
        )

        if isinstance(objectives_from_response, dict):
            if 'value' in objectives_from_response:
                objectives_from_response = objectives_from_response['value']
            elif 'items' in objectives_from_response:
                objectives_from_response = objectives_from_response['items']

        print("objectives_from_response: ", objectives_from_response)
        logger.info(f"objectives_from_response: {objectives_from_response}")

        if not isinstance(objectives_from_response, list):
            objectives_from_response = [objectives_from_response] if objectives_from_response else []

        # Normalize and validate
        objectives_from_response = normalize_objectives(objectives_from_response)
        validate_objectives(objectives_from_response)

        objective_list = []

        # Create set of normalized source IDs for validation
        valid_source_ids = set()
        for chunk in filtered_chunks:
            normalized_id = normalize_source_id(chunk.get('source_id'))
            if normalized_id:
                valid_source_ids.add(normalized_id)

        print(f"Valid source IDs (normalized): {valid_source_ids}")

        for obj in objectives_from_response:
            if isinstance(obj, dict):
                objective_text = obj.get('objective', obj.get('text', ''))
                objective_text = objective_text.strip()
                sources = obj.get('sources', [])
                reason = obj.get('reason', '')

                if isinstance(sources, str):
                    if sources.strip() in ("[]", ""):
                        sources = []
                    else:
                        try:
                            sources = json.loads(sources)
                        except:
                            sources = []

                if sources is None:
                    sources = []

                if not isinstance(sources, list):
                    sources = [sources]

                filtered_sources = []
                validated_source_ids = []

                for src in sources:
                    if isinstance(src, dict):
                        raw_source_id = src.get("source_id")
                        normalized_id = normalize_source_id(raw_source_id)
                        highlight_text = src.get("highlight_text", "")

                        if normalized_id and normalized_id in valid_source_ids:
                            # Find original ID from chunks
                            original_id = None
                            for chunk in filtered_chunks:
                                if normalize_source_id(chunk.get('source_id')) == normalized_id:
                                    original_id = chunk.get('source_id')
                                    break

                            if original_id is not None:
                                filtered_sources.append({
                                    "source_id": original_id,
                                    "highlight_text": highlight_text
                                })
                                validated_source_ids.append(original_id)
                        else:
                            print(
                                f"Warning: source_id '{raw_source_id}' (normalized: '{normalized_id}') not found in valid chunks")

                has_sources = bool(sources)
                has_valid_sources = bool(validated_source_ids)

                if objective_text and (has_valid_sources or not has_sources):
                    objective_list.append({
                        'objective': objective_text.strip(),
                        'sources': filtered_sources,
                        'source_ids': validated_source_ids,
                        'reason': reason,
                        'is_evidence_optional': not has_sources
                    })

        print(f"\nParsed {len(objective_list)} objectives from response")
        return objective_list

    except ValueError as e:
        logger.error(f"Objectives validation failed: {str(e)}")
        raise
