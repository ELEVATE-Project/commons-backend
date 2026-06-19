import json
import re

from bs4 import BeautifulSoup

from chatbot.models import SessionFlowName
from chatbot.utils.story_llama_utils import translate_field


def json_to_html(formatted_content):

    try:
        content_data = json.loads(formatted_content)
        print("type: ", type(content_data))
    except json.JSONDecodeError:
        return ""

    html_content = ""
    for block in content_data:
        print("block type: ", type(block))
        if isinstance(block, dict) and "type" in block and "data" in block:
            if block["type"] == "paragraph":
                text = block["data"].get("text", "")

                text = text.replace("\n\n", "<br><br>").replace("\n", "<br>")

                html_content += f"<p>{text}</p>"
        else:
            print(f"Unexpected block format: {block}")

    return html_content


def count_words_and_lines(text):

    word_count = 0
    lines = text.splitlines()

    for line in lines:
        word_count += len(line.split())

    return word_count, len(lines)


def split_content_based_on_words(content, max_words_per_page=400):
    soup = BeautifulSoup(content, "html.parser")
    chunks = []
    current_chunk = []
    word_counter = 0

    for element in soup.find_all(["p", "br"]):
        if element.name == "p":
            text = element.decode_contents()
            words = text.split()
            paragraph_word_count = len(words)
            i = 0

            while i < paragraph_word_count:
                remaining_space = max_words_per_page - word_counter
                if paragraph_word_count - i > remaining_space:
                    # Take a chunk of words that fit on the current page
                    part = " ".join(words[i : i + remaining_space])
                    current_chunk.append(f"<p>{part}</p>")
                    chunks.append("".join(current_chunk))
                    current_chunk = []
                    word_counter = 0
                    i += remaining_space
                else:
                    # The remaining words fit within the current page
                    part = " ".join(words[i:])
                    current_chunk.append(f"<p>{part}</p>")
                    word_counter += paragraph_word_count - i
                    break

        elif element.name == "br" and current_chunk:
            current_chunk.append("<br>")

    if current_chunk:
        chunks.append("".join(current_chunk))

    return chunks


def get_thirdpage_html(profile, story, project, voice_provider, story_vernacular, flow):
    profile_addresses=None
    # if profile and profile.first_name:
        # profile_addresses = profile.profile_address.all().first()

    # if flow and flow in [SessionFlowName.GuestMiStory]:
    #     address_string = story.other_params.get('location', '') if story.other_params else ''
    # else:
    #     address_components = [
    #         profile_addresses.district if profile_addresses and profile_addresses.district else "",
    #         profile_addresses.block if profile_addresses and profile_addresses.block else "",
    #         profile_addresses.state if profile_addresses and profile_addresses.state else ""
    #     ]
    #     address_string = ", ".join(filter(None, address_components))

    # author = story.other_params.get('user_name', '') if story.other_params else ''

    sanitized_content = json_to_html(story.formatted_content)
    should_show_story_heading = True

    content_chunks = split_content_based_on_words(sanitized_content)

    # if project and project.project_language and project.project_language != 'en':
    #     if address_string:
    #         address_string = translate_field(
    #             voice_provider=voice_provider, message_body=address_string, target_language=project.project_language
    #         )

    # translation_json = story_vernacular.translation_json
    # if translation_json:
    #     translation_json = translation_json.get('third_page', {})
    # else:
    #     translation_json = {}

    # if profile and profile.first_name:
    #     author_title = translation_json.get('title', '')
    # else:
    #     author_title = translation_json.get('title1', '')

    title = (
        f"{story.title or ''}"
    )

    html_pages = []
    for chunk in content_chunks:
        html_page = f"""
        <div class="story-company2-div page-break">
            <div class="story-in-thirdpage">
                {f'<p class="story-heading-third">{title}</p>' if should_show_story_heading else ''}
                {(f'<img src="https://static-media.gritworks.ai/fe-images/PNG/GritPersona/line_story.png" '
                  f'class="story-line-logo1-third" alt="line_story" />') if should_show_story_heading else ''}

                <div class="story-contentBox">
                    <div style="position: relative; width: 90%; height: auto;">
                        {chunk}
                    </div>
                    <img src="https://static-media.gritworks.ai/fe-images/PNG/GritPersona/line_story.png" 
                    class="story-line1-logo" alt="line_story" />
                </div>
            </div>
        </div>
        """
        html_pages.append(html_page)
        should_show_story_heading = False

    return "\n".join(html_pages)
