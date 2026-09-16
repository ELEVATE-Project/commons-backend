def normalize_source_id(source_id):
    """
    Normalize source ID for consistent comparison.
    Converts to integer if possible, otherwise keeps as string.
    """
    if source_id is None:
        return None

    try:
        return int(source_id)
    except (ValueError, TypeError):
        return str(source_id).strip()


def filter_and_sort_chunks(chunks_response, filter_score, top_k=None):
    filtered_chunks = []

    if not chunks_response or not chunks_response.get("results"):
        return filtered_chunks

    for result in chunks_response.get("results", []):
        if not isinstance(result, dict):
            continue

        relevance_score = result.get('score', 0)

        if relevance_score >= filter_score:
            chunk_text = result.get('text', '')

            if chunk_text and len(chunk_text.strip()) > 20:
                source_id = result.get('source_id', '') or result.get('metadata', {}).get('source_id', '')

                normalized_id = normalize_source_id(source_id)

                filtered_chunks.append({
                    'chunk_text': chunk_text.strip(),
                    'source_id': normalized_id,
                    'original_source_id': source_id,
                    'relevance_score': relevance_score,
                    'full_result': result
                })

    filtered_chunks.sort(key=lambda x: x['relevance_score'], reverse=True)

    if top_k and len(filtered_chunks) > top_k:
        filtered_chunks = filtered_chunks[:top_k]

    return filtered_chunks


def prepare_chunks_for_template(filtered_chunks):
    chunks_data = []
    for idx, chunk in enumerate(filtered_chunks, 1):
        chunks_data.append({
            'index': idx,
            'text': chunk['chunk_text'],
            'source_id': chunk['source_id'],
            'score': chunk['relevance_score']
        })
    return chunks_data


def render_template_with_context(tag_context, context_data, fallback_template=None):
    from jinja2 import Template

    if tag_context:
        template = Template(tag_context)
        return template.render(context_data)
    elif fallback_template:
        template = Template(fallback_template)
        return template.render(context_data)
    else:
        return str(context_data)


def validate_inputs(user_input, company_bot, required_attrs=None):
    if not user_input or not isinstance(user_input, str):
        return {'valid': False, 'message': 'Invalid input: must be a non-empty string'}

    if not company_bot:
        return {'valid': False, 'message': 'Invalid company_bot: company_bot object is required'}

    if required_attrs:
        missing_attrs = [attr for attr in required_attrs if not hasattr(company_bot, attr)]
        if missing_attrs:
            return {'valid': False,
                    'message': f'Invalid company_bot: missing required attributes ({", ".join(missing_attrs)})'}

    return {'valid': True, 'message': 'Valid inputs'}
