from chatbot.llm_models.llm_script import handle_bedrock_model
import json_repair
import json
from jinja2 import Template


def validate_objective_utils(user_input, user_problem_statement, company_bot):
    try:
        prompt = company_bot.context
        context_data = {
            "objectives": user_input,
            "problem_statement": user_problem_statement
        }
        template = Template(company_bot.tag_context)
        tag_context = template.render(context_data)

        messages = [{
            'role': 'user',
            'content': [{'text': f"{tag_context}"}]
        }]

        prompt = [{'text': prompt}]

        tool_context = company_bot.tool_context
        tool_context = json_repair.repair_json(tool_context, return_objects=True)
        response = handle_bedrock_model(
            system_prompt=prompt, messages=messages, model_name=company_bot.llm_model,
            temperature=company_bot.bot_temperature, max_token=company_bot.max_token, company_bot=company_bot,
            tools=tool_context, top_p=company_bot.filter_score,
        )

        tool_response = None

        if 'output' in response:
            content = response.get('output', {}).get('message', {}).get('content', [])
            if content and isinstance(content, list):
                for item in content:
                    if 'toolUse' in item:
                        tool_input = item['toolUse'].get('input', {})
                        if tool_input:
                            tool_response = tool_input
                            break

        if not tool_response and 'content' in response:
            for content_block in response['content']:
                if content_block.get('toolUse'):
                    tool_response = content_block['toolUse'].get('input', {})
                    break

        if not tool_response:
            tool_response = parse_llm_response(response)

        extracted_data = tool_response.pop("parameters", tool_response.pop("input", None))
        if extracted_data:
            from shikshalokam.utils.action_list.action_parser import unwrap_tool_values
            extracted_data = unwrap_tool_values(extracted_data)
            tool_response = extracted_data

        if isinstance(tool_response.get('valid'), str):
            tool_response['valid'] = tool_response['valid'].lower() == 'true'

        if isinstance(tool_response.get('problem_statement_in_scope'), str):
            tool_response['problem_statement_in_scope'] = tool_response['problem_statement_in_scope'].lower() == 'true'

        if isinstance(tool_response.get('objectives_validation'), str):
            import json
            tool_response['objectives_validation'] = json.loads(tool_response['objectives_validation'])
            for obj in tool_response['objectives_validation']:
                if isinstance(obj.get('aligned'), str):
                    obj['aligned'] = obj['aligned'].lower() == 'true'
                if isinstance(obj.get('within_scope'), str):
                    obj['within_scope'] = obj['within_scope'].lower() == 'true'

        return {
            'success': True,
            'data': tool_response
        }
    except Exception as e:
        print("Got error : ", e)
        return {
            'success': False,
            'error': str(e)
        }


def validate_actions_utils(user_input, user_objective, problem_statement, company_bot):
    try:
        print('user_input: ', user_input)
        prompt = company_bot.context

        context_data = {
            "actionList": user_input,
            "objective": user_objective,
            "problem_statement": problem_statement
        }
        template = Template(company_bot.tag_context)
        tag_context = template.render(context_data)

        messages = [{
            'role': 'user',
            'content': [{'text': f"{tag_context}"}]
        }]

        prompt = [{'text': prompt}]

        tool_context = company_bot.tool_context
        tool_context = json_repair.repair_json(tool_context, return_objects=True)
        response = handle_bedrock_model(
            system_prompt=prompt, messages=messages, model_name=company_bot.llm_model,
            temperature=company_bot.bot_temperature, max_token=company_bot.max_token, company_bot=company_bot,
            tools=tool_context, top_p=company_bot.filter_score,
        )

        tool_response = None

        if 'output' in response:
            content = response.get('output', {}).get('message', {}).get('content', [])
            if content and isinstance(content, list):
                for item in content:
                    if 'toolUse' in item:
                        tool_input = item['toolUse'].get('input', {})
                        if tool_input:
                            tool_response = tool_input
                            break

        if not tool_response and 'content' in response:
            for content_block in response['content']:
                if content_block.get('toolUse'):
                    tool_response = content_block['toolUse'].get('input', {})
                    break

        if not tool_response:
            tool_response = parse_llm_response(response)

        extracted_data = tool_response.pop("parameters", tool_response.pop("input", None))
        if extracted_data:
            from shikshalokam.utils.action_list.action_parser import unwrap_tool_values
            extracted_data = unwrap_tool_values(extracted_data)
            tool_response = extracted_data

        if isinstance(tool_response.get('valid'), str):
            tool_response['valid'] = tool_response['valid'].lower() == 'true'

        if isinstance(tool_response.get('problem_statement_in_scope'), str):
            tool_response['problem_statement_in_scope'] = tool_response['problem_statement_in_scope'].lower() == 'true'

        if isinstance(tool_response.get('objective_in_scope'), str):
            tool_response['objective_in_scope'] = tool_response['objective_in_scope'].lower() == 'true'

        if isinstance(tool_response.get('actions_validation'), str):
            import json
            tool_response['actions_validation'] = json.loads(tool_response['actions_validation'])
            for action in tool_response['actions_validation']:
                if isinstance(action.get('aligned_with_objective'), str):
                    action['aligned_with_objective'] = action['aligned_with_objective'].lower() == 'true'
                if isinstance(action.get('aligned_with_problem'), str):
                    action['aligned_with_problem'] = action['aligned_with_problem'].lower() == 'true'
                if isinstance(action.get('within_scope'), str):
                    action['within_scope'] = action['within_scope'].lower() == 'true'

        return {
            'success': True,
            'data': tool_response
        }
    except Exception as e:
        print("Got error : ", e)
        return {
            'success': False,
            'error': str(e)
        }


def validate_title_utils(user_input, user_objective, problem_statement, user_actions, company_bot):
    try:
        print('user_input: ', user_input)
        prompt = company_bot.context

        context_data = {
            "title": user_input,
            "actionList": user_actions,
            "objective": user_objective,
            "problem_statement": problem_statement
        }
        template = Template(company_bot.tag_context)
        tag_context = template.render(context_data)

        messages = [{
            'role': 'user',
            'content': [{'text': f"{tag_context}"}]
        }]

        prompt = [{'text': prompt}]

        import json_repair
        tool_context = company_bot.tool_context
        tool_context = json_repair.repair_json(tool_context, return_objects=True)
        response = handle_bedrock_model(
            system_prompt=prompt, messages=messages, model_name=company_bot.llm_model,
            temperature=company_bot.bot_temperature, max_token=company_bot.max_token, company_bot=company_bot,
            tools=tool_context, top_p=company_bot.filter_score,
        )

        parsed_response = parse_llm_response(response)
        response = parsed_response.get('within_scope')
        return response
    except Exception as e:
        print("Got error : ", e)
        return False


def parse_llm_response(response):
    if not response or not isinstance(response, dict):
        return {}

    extracted_data = response.pop("parameters", response.pop("input", None))
    if extracted_data and isinstance(extracted_data, dict):
        return extracted_data

    if isinstance(response, str):
        try:
            return json_repair.repair_json(response, return_objects=True)
        except:
            try:
                return json.loads(response)
            except:
                return {}

    return response
