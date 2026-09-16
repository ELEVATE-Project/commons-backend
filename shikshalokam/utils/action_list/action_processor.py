from shikshalokam.utils.chunks_utils import normalize_source_id


def post_process_actions_with_source(action_list, filtered_chunks, chunks_response):
    """
    Enrich action list with complete source information including chunks, scores, and metadata.
    """
    try:
        if not action_list or not isinstance(action_list, list):
            raise ValueError("Error in LLM returned action list")

        source_id_to_score = {}
        for chunk in filtered_chunks:
            source_id = chunk.get('source_id')
            if source_id is not None:
                source_id_to_score[source_id] = chunk['relevance_score']
                normalized = normalize_source_id(source_id)
                if normalized:
                    source_id_to_score[normalized] = chunk['relevance_score']

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
                        source_entry = {
                            'source_id': source_id,
                            'description': description,
                            'title': title,
                            'url': url,
                            'organization': organization_dict,
                            'chunks': [chunk_data]
                        }
                        source_map[source_id] = source_entry

                        normalized_id = normalize_source_id(source_id)
                        if normalized_id and normalized_id != source_id:
                            source_map[normalized_id] = source_entry
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
                            if score == 0:
                                normalized_id = normalize_source_id(source_id)
                                score = source_id_to_score.get(normalized_id, 0)

                            source_info = source_map.get(source_id)
                            if not source_info:
                                normalized_id = normalize_source_id(source_id)
                                source_info = source_map.get(normalized_id)

                            if not source_info:
                                source_info = {
                                    'source_id': source_id,
                                    'chunks': [],
                                    'description': '',
                                    'title': '',
                                    'url': '',
                                    'organization': {}
                                }

                            highlight_texts = []
                            for src in step_data.get("sources", []):
                                src_id_normalized = normalize_source_id(src.get("source_id"))
                                source_id_normalized = normalize_source_id(source_id)
                                if src_id_normalized == source_id_normalized and src.get("highlight_text"):
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
                total_score = 0
                for sid in all_source_ids:
                    score = source_id_to_score.get(sid, 0)
                    if score == 0:
                        normalized_id = normalize_source_id(sid)
                        score = source_id_to_score.get(normalized_id, 0)
                    total_score += score

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
