import re
import json_repair


def _split_steps_by_char_limit(steps, first_page_limit, full_page_limit):
    """Split a list of action-step strings into page-sized batches.
    """
    if not steps:
        return []

    batches = []
    current_batch = []
    current_chars = 0
    limit = first_page_limit  # first batch uses the smaller limit

    for step in steps:
        step_len = len(step)
        if current_batch and current_chars + step_len > limit:
            # current batch is full – start a new one
            batches.append(current_batch)
            current_batch = [step]
            current_chars = step_len
            limit = full_page_limit  # subsequent pages get the larger limit
        else:
            current_batch.append(step)
            current_chars += step_len

    if current_batch:
        batches.append(current_batch)

    return batches


def _build_steps_ol(steps, start_index=1):
    """Return an <ol> HTML string for the given steps, starting numbering at *start_index*."""
    return (
        f"<ol start='{start_index}' style='list-style-type: decimal; padding: 0; margin: 0;'>"
        + ''.join(f"<li>{step}</li>" for step in steps)
        + "</ol>"
    )


def get_story_secondpage_html(story, project, story_vernacular):
    print("story.action_steps: ", story.action_steps)
    translation_json = story_vernacular.translation_json
    if translation_json:
        translation_json = translation_json.get('second_page', {})
    else:
        translation_json = {}

    second_page_action_steps_char_limit = translation_json.get('SECOND_PAGE_ACTION_STEPS_CHAR_LIMIT', 950)
    full_page_action_steps_char_limit = translation_json.get('FULL_PAGE_ACTION_STEPS_CHAR_LIMIT', 2200)
    second_page_total_char_limit = translation_json.get('SECOND_PAGE_TOTAL_CHAR_LIMIT', 1500)

    if isinstance(story.action_steps, str):
        try:
            if story.action_steps.strip().startswith("["):
                story.action_steps = json_repair.repair_json(story.action_steps, return_objects=True)
                print("story.action_steps after repair: ", story.action_steps)
            else:
                story.action_steps = [story.action_steps]
        except Exception as e:
            print(f"Error repairing JSON: {e}")
            story.action_steps = [translation_json.get('no_action_step_text', "")]

    action_steps = (
        [clean_escaped_text(step) for step in story.action_steps] if isinstance(story.action_steps, list)
        else [clean_escaped_text(story.action_steps)] if isinstance(story.action_steps, str)
        else [translation_json.get('no_action_step_text', "")]
    )
    print("action step type: ", type(action_steps))
    print("action_steps: ", action_steps)
    # steps = action_steps[0]
    if action_steps and isinstance(action_steps, list) and len(action_steps) == 1 and isinstance(action_steps[0], str):
        steps_text = action_steps[0]
        split_steps = re.findall(r'\d+\.\s*[^0-9]+', steps_text)
        split_steps = [step.strip() for step in split_steps if step.strip()]
        if not split_steps:
            split_steps = action_steps
    elif action_steps and isinstance(action_steps, str):
        steps_text = " ".join(action_steps)
        split_steps = re.findall(r'\d+\.\s*[^.]+', steps_text)
        split_steps = [step.strip() for step in split_steps if step.strip()]
    else:
        split_steps = [step.strip() for step in action_steps if step.strip()]
    print("\n\nsplit_steps: ", split_steps)

    # ── Split action steps into page-sized batches ───────────────────────
    step_batches = _split_steps_by_char_limit(
        split_steps,
        first_page_limit=second_page_action_steps_char_limit,
        full_page_limit=full_page_action_steps_char_limit,
    )

    # Build HTML for the first batch (shown on the second page)
    if step_batches:
        first_batch_html = _build_steps_ol(step_batches[0], start_index=1)
    else:
        first_batch_html = None

    print("\n\nfirst_batch steps_html: ", first_batch_html)
    print("story.objective: ", story.objective)
    if project:
        problem_statement = project.get('actual_problem_statement', '')
    elif story:
        problem_statement = story.other_params.get('problem_statement', '') if story and story.other_params else ''
    else:
        problem_statement = ''

    problem_statement = capitalize_first_letter(problem_statement)
    story.objective = capitalize_first_letter(story.objective or translation_json.get('no_objective_text', ""))
    story.impact = capitalize_first_letter(story.impact or translation_json.get('no_impact_text', ""))
    print("translation_json: ", translation_json)
    print("problem_statement:", repr(problem_statement))  # Use repr() to see if it's empty string or None
    print("Fallback text:", repr(translation_json.get('no_problem_statement_text', "")))
    print("Final result:", repr(problem_statement or translation_json.get('no_problem_statement_text', "")))

   
    impact_section = f"""
        <div class="story-second-page-section">
            <h2>{translation_json.get('heading5', "")}</h2>
            <p>{story.impact or translation_json.get('no_impact_text', "")}</p>
        </div>"""

    impact_standalone = f"""
    <div class="story-impact-wrapper">
        {impact_section}
    </div>
    """

  
    overflow_batches = step_batches[1:] if step_batches else []
    has_overflow = len(overflow_batches) > 0

    ps_text = problem_statement or translation_json.get('no_problem_statement_text', '')
    obj_text = story.objective or translation_json.get('no_objective_text', '')
    impact_text = story.impact or translation_json.get('no_impact_text', '')
    first_batch_chars = sum(len(s) for s in step_batches[0]) if step_batches else 0
    impact_chars = len(impact_text)
    second_page_chars = len(ps_text) + len(obj_text) + first_batch_chars + impact_chars
    print(f"second_page_chars (incl. impact): {second_page_chars}, limit: {second_page_total_char_limit}")

    # Impact goes inline only when there's no overflow AND all 4 sections fit
    impact_fits_on_page = not has_overflow and second_page_chars <= second_page_total_char_limit

    page_html = f"""
    <div class="story-second-page-container">
        <h1>{translation_json.get('heading1', "")}</h1>
        <div class="story-second-page-section">
            <h2>{translation_json.get('heading2', "")}</h2>
            <p>{ps_text}</p>
        </div>
        <div class="story-second-page-section">
            <h2>{translation_json.get('heading3', "")}</h2>
            <p>{obj_text}</p>
        </div>
        <div class="story-second-page-section story-action-steps">
            <h2>{translation_json.get('heading4', "")}</h2>
            {first_batch_html or translation_json.get('no_action_step_text', "")}
        </div>
        {impact_section if impact_fits_on_page else ''}
    </div>
    """


    running_index = len(step_batches[0]) + 1 if step_batches else 1
    for batch in overflow_batches:
        overflow_ol = _build_steps_ol(batch, start_index=running_index)
        page_html += f"""
    <div class="story-second-page-container story-action-steps-overflow">
        <div class="story-second-page-section story-action-steps">
            {overflow_ol}
        </div>
    </div>
        """
        running_index += len(batch)


    if not impact_fits_on_page:
        page_html += impact_standalone

    return page_html


def clean_escaped_text(text):
    text = text.replace("\\'", "")# \'  →  '
    text = text.replace('\\"', '')# \"  →  "
    text = text.replace("\\\\", "") # \\  →  \
    print("Text: ", text)
    return text


def capitalize_first_letter(text):
    """Capitalize the first alphabetical character in the string, safely."""
    if not text:
        return text
    text = text.lstrip()
    if not text:
        return text
    return text[0].upper() + text[1:]
