from chatbot.llm_models.llm_script import handle_bedrock_model
from shikshalokam.utils.chunks_utils import validate_inputs, filter_and_sort_chunks, prepare_chunks_for_template, \
    render_template_with_context
import json_repair
import json
import logging

logger = logging.getLogger('django')


def generate_objective_utils(user_problem_statement, company_bot):
    try:
        from chatbot.utils.chat_query_handler import query_text_search

        required_attrs = ['top_k', 'filter_score', 'context', 'tag_context', 'llm_model', 'bot_temperature',
                          'max_token']
        validation = validate_inputs(user_problem_statement, company_bot, required_attrs)

        if not validation['valid']:
            return {
                'status': 'error',
                'status_code': 400,
                'objective_list': [],
                'chunks_response': None,
                'message': validation['message']
            }

        try:
            chunks_response = query_text_search(
                query=user_problem_statement,
                priority="P1",
                limit=company_bot.top_k
            )

            if chunks_response.get('error'):
                return {
                    'status': 'error',
                    'status_code': chunks_response.get('status_code', 500),
                    'objective_list': [],
                    'chunks_response': None,
                    'message': chunks_response.get('message', 'API request failed')
                }

        except Exception as db_error:
            return {
                'status': 'error',
                'status_code': 500,
                'objective_list': [],
                'chunks_response': None,
                'message': f'Database query failed: {str(db_error)}'
            }

        if not chunks_response or not chunks_response.get("results"):
            return {
                'status': 'ok',
                'status_code': 200,
                'objective_list': [],
                'total_objectives': 0,
                'total_chunks_used': 0,
                'total_chunks_found': 0,
                'total_results': 0,
                'chunks_response': chunks_response,
                'message': 'No chunks found from text-search API'
            }

        filtered_chunks = filter_and_sort_chunks(
            chunks_response, company_bot.filter_score, company_bot.top_k
        )

        logger.info(f"filtered_chunks: {filtered_chunks}")

        if not filtered_chunks:
            total_chunks = len(chunks_response.get("results", []))
            max_score = max([r.get('score', 0) for r in chunks_response.get("results", [])], default=0)

            return {
                'status': 'ok',
                'status_code': 200,
                'objective_list': [],
                'total_objectives': 0,
                'total_chunks_used': 0,
                'total_chunks_found': total_chunks,
                'total_results': total_chunks,
                'chunks_response': chunks_response,
                'message': f'No chunks met filter criteria. Found {total_chunks} chunks, max score: {max_score:.4f}, threshold: {company_bot.filter_score}'
            }

        try:
            chunks_data = prepare_chunks_for_template(filtered_chunks)

            context_data = {
                'user_problem_statement': user_problem_statement,
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

            system_prompt = [{'text': company_bot.context}]
            import json_repair
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
                    'objective_list': [],
                    'chunks_response': chunks_response,
                    'message': 'Invalid response from LLM'
                }

            objective_list = parse_llm_objective_response(response, filtered_chunks)

        except Exception as llm_error:
            return {
                'status': 'error',
                'status_code': 500,
                'objective_list': [],
                'chunks_response': chunks_response,
                'message': f'Error generating objectives: {str(llm_error)}'
            }

        total_results = chunks_response.get('total_results', 0)
        return {
            'status': 'ok',
            'status_code': 200,
            'objective_list': objective_list,
            'filtered_chunks': filtered_chunks,
            'total_objectives': len(objective_list),
            'total_chunks_used': len(filtered_chunks),
            'total_chunks_found': total_results,
            'total_results': total_results,
            'chunks_response': chunks_response,
            'message': f'Successfully generated {len(objective_list)} objectives from {len(filtered_chunks)} chunks'
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            'status': 'error',
            'status_code': 500,
            'objective_list': [],
            'total_objectives': 0,
            'total_chunks_used': 0,
            'total_chunks_found': 0,
            'total_results': 0,
            'chunks_response': None,
            'message': f'Internal server error: {str(e)}'
        }


def parse_llm_objective_response(response, filtered_chunks):
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

    print("\n extracted_data: ", extracted_data)
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

    if isinstance(objectives_from_response, str):
        try:
            objectives_from_response = json_repair.repair_json(objectives_from_response, return_objects=True)
        except:
            try:
                objectives_from_response = json.loads(objectives_from_response)
            except:
                objectives_from_response = []

    if not isinstance(objectives_from_response, list):
        objectives_from_response = [objectives_from_response] if objectives_from_response else []

    objective_list = []
    valid_source_ids = {chunk['source_id'] for chunk in filtered_chunks}

    for obj in objectives_from_response:
        if isinstance(obj, dict):
            objective_text = obj.get('objective', obj.get('text', ''))
            sources = obj.get('sources', [])
            source_ids = [src.get("source_id") for src in sources if src.get("source_id")]
            reason = obj.get('reason', '')

            if not isinstance(source_ids, list):
                source_ids = [source_ids] if source_ids else []

            validated_source_ids = [sid for sid in source_ids if sid in valid_source_ids]

            if objective_text and validated_source_ids:
                filtered_sources = [
                    src for src in sources
                    if src.get("source_id") in validated_source_ids
                ]

                objective_list.append({
                    'objective': objective_text.strip(),
                    'sources': filtered_sources,
                    'source_ids': validated_source_ids,
                    'reason': reason
                })

    return objective_list


def post_process_objectives_with_source(objective_list, filtered_chunks, chunks_response):
    try:
        if not objective_list:
            return {
                'status': 'ok',
                'status_code': 200,
                'objective_list': [],
                'message': 'No objectives to process'
            }

        if not isinstance(objective_list, list):
            return {
                'status': 'error',
                'status_code': 400,
                'objective_list': [],
                'message': 'Invalid objective_list: must be a list'
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
                    'objective_list': [],
                    'message': f'Error mapping source data: {str(map_error)}'
                }

        processed_objectives = []
        for objective in objective_list:
            try:
                if not isinstance(objective, dict):
                    print(f"Skipping invalid objective: {objective}")
                    continue

                source_ids = objective.get('source_ids', [])
                if not isinstance(source_ids, list):
                    source_ids = [source_ids] if source_ids else []

                sources = []
                total_score = 0
                for source_id in source_ids:
                    if isinstance(source_id, list):
                        source_id = source_id[0] if source_id else ''
                    score = source_id_to_score.get(source_id, 0)
                    total_score += score
                    source_info = source_map.get(source_id, {
                        'source_id': source_id,
                        'chunks': [],
                        'description': '',
                        'title': '',
                        'url': '',
                        'organization': {}
                    })

                    highlight_texts = []
                    for src in objective.get("sources", []):
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

                    sources.append({
                        'source_id': source_id,
                        'score': score,
                        'chunks': chunks_with_highlights,
                        'description': source_info.get('description', ''),
                        'title': source_info.get('title', ''),
                        'url': source_info.get('url', ''),
                        'organization': source_info.get('organization', {}),
                        'chunk_count': len(chunks_with_highlights)
                    })

                avg_score = total_score / len(source_ids) if source_ids else 0

                processed_objective = {
                    'text': objective.get('objective', objective.get('text', '')),
                    'reason': objective.get('reason', ''),
                    'score': avg_score,
                    'sources': sources,
                    'source_count': len(sources)
                }
                processed_objectives.append(processed_objective)

            except Exception as obj_error:
                print(f"Error processing objective: {str(obj_error)}")
                continue

        return {
            'status': 'ok',
            'status_code': 200,
            'objective_list': processed_objectives,
            'message': f'Successfully processed {len(processed_objectives)} objectives with source information'
        }

    except Exception as e:
        print(f"Unexpected error in post_process_objectives_with_source: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'status': 'error',
            'status_code': 500,
            'objective_list': [],
            'message': f'Internal server error: {str(e)}'
        }
