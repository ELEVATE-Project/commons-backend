import traceback
from chatbot.llm_models.llm_script import handle_openai_model
from chatbot.models import (Profile, CompanyChat, CompanyBot, StoryLanguageChoices,
                                                StoryStatusChoices, LLMModel)
from chatbot.models.story_models import Story
# from chatbot.utils.story_utils import get_company_context, DEFAULT_PROMPT, get_formatted_story


def re_create_story_object(profile_id, session):
    try:
        pass
        # profile = Profile.objects.get(id=profile_id)
        # company = profile.company
        # company_context = get_company_context(profile, company)
        # company_chats = CompanyChat.objects.filter(session=session).order_by('created_at')
        # print('company_chats: ', company_chats)
        # if len(company_chats) <= 10:
        #     return "", ""
        # ai_user = Profile.objects.get(id=1)
        # company_bot = CompanyBot.objects.filter(company=profile.company)
        # if company_bot.count() > 0:
        #     company_bot = company_bot[0]
        #     end_context = company_bot.end_context
        #     if end_context is None or end_context == "":
        #         end_context = DEFAULT_PROMPT
        # else:
        #     end_context = DEFAULT_PROMPT
        # end_context += company_context
        # end_context += """
        #     OUTPUT JSON FORMAT:
        #     {{
        #         "title": "Title of the story",
        #         "content": "Content of the story in more than 600 tokens",
        #         "tweet": "Tweet for the story in less than 200 characters with minimum 5 hashtags",
        #         "objective": "Objective of the micro improvement",
        #         "action_steps": "5 Action steps taken by the user to implement the micro improvement",
        #         "impact": "Impact created from this micro improvement",
        #         "micro_improvement": "Why is this microprovement important"
        #     }}
        # """
        # print(end_context)
        # messages = [{
        #     'role': 'system',
        #     'content': end_context
        # }]
        # for chat in company_chats:
        #     if chat.receiver == ai_user:
        #         messages.append({
        #             'role': 'user',
        #             'content': chat.message
        #         })
        #     else:
        #         messages.append({
        #             'role': 'assistant',
        #             "content": chat.message
        #         })
        # messages.append({
        #     'role': 'system',
        #     'content': 'REMEMBER RETURN THE STORY IN MORE THAN 600 TOKENS.'
        # })
        #
        # response_json = handle_openai_model(
        #     messages=messages, max_token=4096, temperature=0.0, model_name=LLMModel.GPT4_O
        # )
        #
        # print(response_json)
        #
        # story_data = {
        #     'title': response_json['title'],
        #     'content': response_json['content'],
        #     'tweet': response_json['tweet'],
        #     'objective': response_json['objective'],
        #     'action_steps': response_json['action_steps'],
        #     'impact': response_json['impact'],
        #     'micro_improvement': response_json['micro_improvement']
        # }
        # story, created = Story.objects.update_or_create(
        #     session=session,
        #     defaults={
        #         'title': story_data['title'],
        #         'content': story_data['content'],
        #         'tweet': story_data['tweet'],
        #         'author': profile,
        #         'objective': story_data['objective'],
        #         'action_steps': story_data['action_steps'],
        #         'impact': story_data['impact'],
        #         'micro_improvement': story_data['micro_improvement'],
        #         'language': StoryLanguageChoices.ENGLISH,
        #         'stage': StoryStatusChoices.COMPLETED
        #     }
        # )
        # if not created:
        #     story.title = story_data['title']
        #     story.content = story_data['content']
        #     story.tweet = story_data['tweet']
        #     story.objective = story_data['objective']
        #     story.action_steps = story_data['action_steps']
        #     story.impact = story_data['impact']
        #     story.micro_improvement = story_data['micro_improvement']
        #     story.stage = StoryStatusChoices.COMPLETED
        #     story.save()
        # formatted_content = get_formatted_story(story)
        # story.formatted_content = formatted_content
        # story.save(update_fields=['formatted_content'])
        # return story.id, story.content
    except Exception as e:
        traceback.print_exc()
        return "", ""
