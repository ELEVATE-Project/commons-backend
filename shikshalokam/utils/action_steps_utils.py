from chatbot.llm_models.llm_script import handle_bedrock_model
from shikshalokam.utils.chunks_utils import validate_inputs, filter_and_sort_chunks, prepare_chunks_for_template, \
    render_template_with_context
import json_repair
import json


def generate_action_list_utils(query, objective_text, company_bot):
    try:
        from chatbot.utils.chat_query_handler import query_text_search

        required_attrs = ['top_k', 'filter_score', 'context', 'tag_context', 'llm_model', 'bot_temperature',
                          'max_token']

        if not query or not isinstance(query, str):
            return {
                'status': 'error',
                'status_code': 400,
                'action_list': [],
                'chunks_response': None,
                'message': 'Invalid query: must be a non-empty string'
            }

        validation = validate_inputs(objective_text, company_bot, required_attrs)
        if not validation['valid']:
            return {
                'status': 'error',
                'status_code': 400,
                'action_list': [],
                'chunks_response': None,
                'message': validation['message']
            }

        try:
            chunks_response = query_text_search(
                query=objective_text, priority="P1", limit=company_bot.top_k
            )

            if chunks_response.get('error'):
                return {
                    'status': 'error',
                    'status_code': chunks_response.get('status_code', 500),
                    'action_list': [],
                    'chunks_response': None,
                    'message': chunks_response.get('message', 'API request failed')
                }

        except Exception as db_error:
            return {
                'status': 'error',
                'status_code': 500,
                'action_list': [],
                'chunks_response': None,
                'message': f'Database query failed: {str(db_error)}'
            }

        if not chunks_response or not chunks_response.get("results"):
            return {
                'status': 'ok',
                'status_code': 200,
                'action_list': [],
                'total_actions': 0,
                'total_chunks_used': 0,
                'total_chunks_found': 0,
                'total_results': 0,
                'chunks_response': chunks_response,
                'message': 'No chunks found from text-search API'
            }

        filtered_chunks = filter_and_sort_chunks(
            chunks_response, company_bot.filter_score, company_bot.top_k
        )

        if not filtered_chunks:
            total_chunks = len(chunks_response.get("results", []))
            return {
                'status': 'ok',
                'status_code': 200,
                'action_list': [],
                'total_actions': 0,
                'total_chunks_used': 0,
                'total_chunks_found': total_chunks,
                'total_results': total_chunks,
                'chunks_response': chunks_response,
                'message': f'No chunks met filter criteria'
            }

        try:
            chunks_data = prepare_chunks_for_template(filtered_chunks)

            context_data = {
                'user_query': query,
                'objective': objective_text,
                'chunks': chunks_data,
                'total_chunks': len(chunks_data)
            }

            rendered_content = render_template_with_context(
                company_bot.tag_context, context_data
            )

            messages = [{
                'role': 'user',
                'content': [{'text': rendered_content}]
            }]

            system_prompt = [{'text': company_bot.context}] if company_bot.context else [
                {'text': 'Generate action plans.'}]

            tool_context = company_bot.tool_context
            tool_context = json_repair.repair_json(tool_context, return_objects=True)

            response = handle_bedrock_model(
                system_prompt=system_prompt, messages=messages, model_name=company_bot.llm_model,
                temperature=company_bot.bot_temperature, max_token=company_bot.max_token, company_bot=company_bot,
                tools=tool_context, top_p=company_bot.filter_score,
            )

            if not response:
                return {
                    'status': 'error',
                    'status_code': 500,
                    'action_list': [],
                    'chunks_response': chunks_response,
                    'message': 'Invalid response from LLM'
                }

            action_list = parse_llm_action_response(response, filtered_chunks)

        except Exception as llm_error:
            return {
                'status': 'error',
                'status_code': 500,
                'action_list': [],
                'chunks_response': chunks_response,
                'message': f'Error generating actions: {str(llm_error)}'
            }

        total_results = chunks_response.get('total_results', 0)
        return {
            'status': 'ok',
            'status_code': 200,
            'action_list': action_list,
            'filtered_chunks': filtered_chunks,
            'total_actions': len(action_list),
            'total_chunks_used': len(filtered_chunks),
            'total_chunks_found': total_results,
            'total_results': total_results,
            'chunks_response': chunks_response,
            'message': f'Successfully generated {len(action_list)} action plans'
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            'status': 'error',
            'status_code': 500,
            'action_list': [],
            'total_actions': 0,
            'total_chunks_used': 0,
            'total_chunks_found': 0,
            'total_results': 0,
            'chunks_response': None,
            'message': f'Internal server error: {str(e)}'
        }


def parse_llm_action_response(response, filtered_chunks):
    print("llm response: ", response)
    if not response or not isinstance(response, dict):
        return []

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
    if extracted_data and isinstance(extracted_data, dict):
        response = extracted_data

    print("\nextracted_data: ", extracted_data)

    action_plans = (
            response.get('action_plans') or
            response.get('action_plan') or
            response.get('action_list') or
            response.get('actions') or
            []
    )

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
    valid_source_ids = {chunk['source_id'] for chunk in filtered_chunks}

    for plan in action_plans:
        if isinstance(plan, dict):
            plan_name = plan.get('plan_name', '')
            duration_weeks = plan.get('duration_weeks', plan.get('duration', 3))
            action_steps_data = plan.get('actionSteps', []) or plan.get('action_steps', []) or plan.get('steps', [])

            processed_steps = []
            all_source_ids = set()
            all_sources = []

            for step_data in action_steps_data:
                if isinstance(step_data, dict):
                    step_text = step_data.get('step', step_data.get('text', ''))
                    sources = step_data.get('sources', [])
                    reason = step_data.get('reason', '')

                    step_source_ids = []
                    step_sources = []

                    for src in sources:
                        if isinstance(src, dict):
                            source_id = src.get('source_id')
                            highlight_text = src.get('highlight_text', '')

                            if source_id and source_id in valid_source_ids:
                                step_source_ids.append(source_id)
                                all_source_ids.add(source_id)
                                step_sources.append({
                                    'source_id': source_id,
                                    'highlight_text': highlight_text
                                })

                    processed_steps.append({
                        'step': step_text,
                        'sources': step_sources,
                        'source_ids': step_source_ids,
                        'reason': reason
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


def post_process_actions_with_source(action_list, filtered_chunks, chunks_response):
    try:
        if not action_list:
            return {
                'status': 'ok',
                'status_code': 200,
                'action_list': [],
                'message': 'No actions to process'
            }

        if not isinstance(action_list, list):
            return {
                'status': 'error',
                'status_code': 400,
                'action_list': [],
                'message': 'Invalid action_list: must be a list'
            }

        source_id_to_score = {chunk['source_id']: chunk['relevance_score'] for chunk in filtered_chunks}

        source_map = {}
        if chunks_response and chunks_response.get("results"):
            try:
                for result in chunks_response["results"]:
                    if not isinstance(result, dict):
                        print(f"Skipping invalid result in post_process: {result}")
                        continue

                    source_id = result.get('source_id', '') or result.get('metadata', {}).get('source_id', '')

                    if not source_id:
                        print(f"Skipping result without source_id: {result}")
                        continue

                    chunk_text = result.get('text', '')
                    metadata = result.get('metadata', {})
                    description = metadata.get('summary', '')
                    title = metadata.get('title', '') or metadata.get('TITLE', '')
                    url = metadata.get('url', '')
                    organization_slug = metadata.get('company', '')
                    highlight_text = result.get('highlight_text', '')

                    organization_dict = {}
                    if organization_slug:
                        try:
                            from chatbot.models import Company
                            company = Company.objects.filter(slug=organization_slug).first()
                            if company:
                                organization_dict = {
                                    'name': company.name,
                                    'slug': company.slug
                                }
                            else:
                                organization_dict = {
                                    'name': organization_slug,
                                    'slug': organization_slug
                                }
                        except Exception as org_error:
                            print(f"Error fetching company for slug '{organization_slug}': {str(org_error)}")
                            organization_dict = {
                                'name': organization_slug,
                                'slug': organization_slug
                            }

                    chunk_data = {
                        'highlight_text': highlight_text,
                        'chunk': chunk_text
                    }

                    if source_id not in source_map:
                        source_map[source_id] = {
                            'source_id': source_id,
                            'description': description,
                            'title': title,
                            'url': url,
                            'organization': organization_dict,
                            'chunks': [chunk_data]
                        }
                    else:
                        source_map[source_id]['chunks'].append(chunk_data)

                        if not source_map[source_id]['description'] and description:
                            source_map[source_id]['description'] = description
                        if not source_map[source_id]['title'] and title:
                            source_map[source_id]['title'] = title
                        if not source_map[source_id]['url'] and url:
                            source_map[source_id]['url'] = url
                        if not source_map[source_id]['organization'] and organization_dict:
                            source_map[source_id]['organization'] = organization_dict

            except Exception as map_error:
                print(f"Error creating source_map: {str(map_error)}")
                return {
                    'status': 'error',
                    'status_code': 500,
                    'action_list': [],
                    'message': f'Error mapping source data: {str(map_error)}'
                }

        processed_actions = []
        for action_plan in action_list:
            try:
                if not isinstance(action_plan, dict):
                    print(f"Skipping invalid action plan: {action_plan}")
                    continue

                processed_steps = []
                for step_data in action_plan.get('actionSteps', []):
                    if isinstance(step_data, dict):
                        step_sources = []
                        for source_id in step_data.get('source_ids', []):
                            score = source_id_to_score.get(source_id, 0)
                            source_info = source_map.get(source_id, {
                                'source_id': source_id,
                                'chunks': [],
                                'description': '',
                                'title': '',
                                'url': '',
                                'organization': {}
                            })

                            highlight_texts = []
                            for src in step_data.get("sources", []):
                                if src.get("source_id") == source_id and src.get("highlight_text"):
                                    highlight_texts.append(src.get("highlight_text"))

                            chunks_with_highlights = []
                            for i, chunk_data in enumerate(source_info.get('chunks', [])):
                                chunk_entry = {
                                    'chunk': chunk_data.get('chunk', ''),
                                    'highlight_text': chunk_data.get('highlight_text', '')
                                }
                                if i < len(highlight_texts):
                                    chunk_entry['highlight_text'] = highlight_texts[i]
                                chunks_with_highlights.append(chunk_entry)

                            step_sources.append({
                                'source_id': source_id,
                                'score': score,
                                'chunks': chunks_with_highlights,
                                'description': source_info.get('description', ''),
                                'title': source_info.get('title', ''),
                                'url': source_info.get('url', ''),
                                'organization': source_info.get('organization', {}),
                                'chunk_count': len(chunks_with_highlights)
                            })

                        processed_steps.append({
                            'step': step_data.get('step', ''),
                            'reason': step_data.get('reason', ''),
                            'sources': step_sources
                        })
                    elif isinstance(step_data, str):
                        processed_steps.append({
                            'step': step_data,
                            'reason': '',
                            'sources': []
                        })

                all_source_ids = action_plan.get('all_source_ids', [])
                total_score = sum(source_id_to_score.get(sid, 0) for sid in all_source_ids)
                avg_score = total_score / len(all_source_ids) if all_source_ids else 0

                processed_action = {
                    'plan_name': action_plan.get('plan_name', ''),
                    'duration_weeks': action_plan.get('duration_weeks', 3),
                    'actionSteps': processed_steps,
                    'score': avg_score,
                    'source_count': len(all_source_ids)
                }
                processed_actions.append(processed_action)

            except Exception as action_error:
                print(f"Error processing action: {str(action_error)}")
                continue

        return {
            'status': 'ok',
            'status_code': 200,
            'action_list': processed_actions,
            'message': f'Successfully processed {len(processed_actions)} actions with source information'
        }

    except Exception as e:
        print(f"Unexpected error in post_process_actions_with_source: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'status': 'error',
            'status_code': 500,
            'action_list': [],
            'message': f'Internal server error: {str(e)}'
        }
