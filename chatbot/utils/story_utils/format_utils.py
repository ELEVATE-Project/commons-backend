import json
import random
import string
import json_repair


def format_response_json(response):
    response_json = response.replace('\n', '').replace('\t', '').replace(
        '\r', '').replace('\\n', '').replace('\\t', '').replace('\\r', '')
    if '{' in response_json:
        response_json = response_json[response_json.index('{'):]
    last_char = response_json[-1]
    if last_char != '}':
        response_json += '}'
    if isinstance(response_json, str):
        response_json = json_repair.repair_json(response_json, return_objects=True)

    return response_json


def get_formatted_story(story):
    if not story or not story.content:
        return None
    story_paragraphs = story.content.split("\n")
    res = []
    for paragraph in story_paragraphs:
        res.append(
            {
                'id': generate_random_string(10),
                'type': 'paragraph',
                'data':
                    {
                        'text': paragraph,
                    }
            }
        )
    return json.dumps(res)


def generate_random_string(length):
    characters = string.ascii_letters + string.digits
    rs = ''.join(random.choice(characters) for _ in range(length))
    return rs


def clean_escaped_text(text):
    text = text.replace("\\'", "")# \'  →  '
    text = text.replace('\\"', '')# \"  →  "
    text = text.replace("\\\\", "") # \\  →  \
    print("Text: ", text)
    return text
