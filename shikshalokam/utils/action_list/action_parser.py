from shikshalokam.utils.chunks_utils import normalize_source_id
import json_repair
import json
import logging

logger = logging.getLogger('django')


def unwrap_tool_values(obj):
    """Recursively unwrap tool schema values."""
    if isinstance(obj, dict):
        # Tool schema leaf
        if "value" in obj and "type" in obj and len(obj) == 2:
            return unwrap_tool_values(obj["value"])

        return {k: unwrap_tool_values(v) for k, v in obj.items()}

    if isinstance(obj, list):
        return [unwrap_tool_values(v) for v in obj]

    return obj


def normalize_action_steps(action_steps):
    """
    Normalizes actionSteps.
    """
    if not action_steps:
        raise ValueError("EMPTY_ACTION_STEPS")

    if isinstance(action_steps, str):
        try:
            action_steps = json.loads(action_steps)
        except Exception:
            try:
                action_steps = json_repair.repair_json(
                    action_steps, return_objects=True
                )
            except Exception:
                raise ValueError("ACTION_STEPS_MALFORMED_JSON")

    return action_steps


def validate_action_steps(action_steps):
    """
    Validates normalized actionSteps.
    """
    if not isinstance(action_steps, list):
        raise ValueError("ACTION_STEPS_NOT_LIST")

    if not action_steps:
        raise ValueError("EMPTY_ACTION_STEPS")

    for i, step in enumerate(action_steps):
        if not isinstance(step, dict):
            raise ValueError(f"INVALID_STEP_OBJECT_{i}")

        step_text = step.get("step", "").strip()

        if not isinstance(step_text, str) or not step_text:
            raise ValueError(f"EMPTY_STEP_TEXT_{i}")
        if step_text.lower() in ("type", "value"):
            raise ValueError(f"INVALID_STEP_TEXT_{i}")


def parse_llm_action_response(response, filtered_chunks):
    """
    Parse LLM response into structured action list with source validation.
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

        action_plans = (
                response.get('action_plans') or
                response.get('action_plan') or
                response.get('action_list') or
                response.get('actions') or
                []
        )

        if not action_plans:
            if response.get('plan_name') and response.get('actionSteps'):
                action_plans = [response]
            elif response.get('plan_name') and (response.get('action_steps') or response.get('steps')):
                action_plans = [response]

        if isinstance(action_plans, dict):
            if 'value' in action_plans:
                action_plans = action_plans['value']
            elif 'items' in action_plans:
                action_plans = action_plans['items']

        if isinstance(action_plans, str):
            try:
                action_plans = json_repair.repair_json(action_plans, return_objects=True)
            except:
                try:
                    action_plans = json.loads(action_plans)
                except:
                    action_plans = []

        if not isinstance(action_plans, list):
            action_plans = [action_plans] if action_plans else []

        action_list = []

        # Create set of normalized source IDs for validation
        valid_source_ids = set()
        for chunk in filtered_chunks:
            normalized_id = normalize_source_id(chunk.get('source_id'))
            if normalized_id:
                valid_source_ids.add(normalized_id)

        print(f"Valid source IDs (normalized): {valid_source_ids}")

        for plan in action_plans:
            if isinstance(plan, dict):
                plan_name = plan.get('plan_name', '')
                duration_weeks = (plan.get('duration_weeks') or
                                  plan.get('overall_duration_weeks') or
                                  plan.get('duration', 13))

                action_steps_data = (plan.get('actionSteps', []) or
                                     plan.get('action_steps', []) or
                                     plan.get('steps', []))

                action_steps_data = normalize_action_steps(action_steps_data)
                validate_action_steps(action_steps_data)

                processed_steps = []
                all_source_ids = set()
                all_sources = []

                for step_data in action_steps_data:
                    if isinstance(step_data, dict):
                        step_text = step_data.get('step', step_data.get('text', ''))

                        sources = step_data.get('sources', [])
                        if sources is None:
                            sources = []
                        if isinstance(sources, str):
                            if sources.strip() in ("[]", ""):
                                sources = []
                            else:
                                try:
                                    sources = json.loads(sources)
                                except:
                                    sources = []
                        if not isinstance(sources, list):
                            sources = [sources]

                        reason = step_data.get('reason', '')

                        has_sources = bool(sources)
                        has_valid_sources = False
                        step_source_ids = []
                        step_sources = []

                        for src in sources:
                            if isinstance(src, dict):
                                raw_source_id = src.get('source_id')
                                normalized_id = normalize_source_id(raw_source_id)
                                highlight_text = src.get('highlight_text', '')
                                confidence_score = src.get('confidence_score', 0)

                                if normalized_id and normalized_id in valid_source_ids:
                                    original_id = None
                                    has_valid_sources = True
                                    for chunk in filtered_chunks:
                                        if normalize_source_id(chunk.get('source_id')) == normalized_id:
                                            original_id = chunk.get('source_id')
                                            break

                                    if original_id is not None:
                                        step_source_ids.append(original_id)
                                        all_source_ids.add(original_id)
                                        if confidence_score in [5, "5"]:
                                            step_sources.append({
                                                'source_id': original_id,
                                                'highlight_text': highlight_text
                                            })
                                else:
                                    print(
                                        f"Warning: source_id '{raw_source_id}' (normalized: '{normalized_id}') not found in valid chunks")

                        step_text = step_text.strip()

                        if step_text:
                            processed_steps.append({
                                'step': step_text,
                                'sources': step_sources,
                                'source_ids': step_source_ids,
                                'reason': reason,
                                'is_evidence_optional': not has_sources
                            })

                        all_sources.extend(step_sources)

                    elif isinstance(step_data, str):
                        processed_steps.append({
                            'step': step_data,
                            'sources': [],
                            'source_ids': [],
                            'reason': ''
                        })

                if processed_steps:
                    action_list.append({
                        'plan_name': plan_name,
                        'duration_weeks': duration_weeks,
                        'actionSteps': processed_steps,
                        'all_source_ids': list(all_source_ids),
                        'all_sources': all_sources
                    })

        print(f"\nParsed {len(action_list)} action plans from response")
        return action_list

    except ValueError as e:
        logger.error(f"ActionSteps validation failed: {str(e)}")
        raise
