def normalize_sources_from_chunks(chunks):

    sources_list = []

    if not isinstance(chunks, dict):
        return sources_list

    all_sources = (
        chunks.get("objective_chunk", []) +
        chunks.get("action_chunk", [])
    )

    for src in all_sources:
        title = src.get("title")
        url = src.get("url")
        org = src.get("organization", {}).get("name")

        parts = []
        if title:
            parts.append(title)
        if org:
            parts.append(f"({org})")
        if url:
            parts.append(url)

        if parts:
            sources_list.append(" ".join(parts))

    return sources_list


def format_project_timeline(project_duration):

    if not project_duration:
        return ""

    duration_str = str(project_duration).strip().lower()

    if "week" in duration_str:
        return str(project_duration).strip()

    try:
        duration_value = int(project_duration)
        return f"{duration_value} week" if duration_value == 1 else f"{duration_value} weeks"
    except (ValueError, TypeError):
        return str(project_duration)
