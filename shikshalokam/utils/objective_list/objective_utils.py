from chatbot.llm_models.llm_script import handle_bedrock_model, handle_openai_model
from chatbot.models import CompanyBot, LLMProvider
from shikshalokam.utils.action_list.action_validator import validate_and_fix_action_list
from shikshalokam.utils.chunks_utils import validate_inputs, filter_and_sort_chunks, prepare_chunks_for_template, \
    render_template_with_context
import logging
from shikshalokam.utils.objective_list.objective_parser import parse_llm_objective_response
import json_repair

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
                print(f"Error while fetching chunks: {chunks_response.get('error')}")
                logger.info(f"Error while fetching chunks: {chunks_response.get('error')}")

        except Exception as db_error:
            print(f"Error while fetching chunks: {db_error}")
            logger.info(f"Error while fetching chunks: {db_error}")
            return {
                'status': 'error',
                'status_code': 500,
                'objective_list': [],
                'chunks_response': None,
                'message': f'Database query failed: {str(db_error)}'
            }

        filtered_chunks = []
        if chunks_response and chunks_response.get("results"):
            filtered_chunks = filter_and_sort_chunks(
                chunks_response, company_bot.filter_score, company_bot.top_k
            )

        logger.info(f"filtered_chunks: {filtered_chunks}")

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

            if company_bot and company_bot.provider == LLMProvider.OPENAI:
                messages = [
                    {
                        'role': 'user',
                        'content': rendered_content
                    }
                ]

                context = company_bot.context
                context += f"\n{company_bot.end_context}" if company_bot.end_context else ""
                system_prompt = [{"role": "system", "content": context}]

                tools = None
                tool_choice = None
                try:
                    tool_context = json_repair.repair_json(company_bot.tool_context, return_objects=True)
                    if tool_context:
                        tools = tool_context.get("tool")
                        tool_choice = tool_context.get("tool_choice", "auto")

                    logger.info("Using state machine tool_context")
                except Exception as e:
                    logger.error(f"Failed to parse state machine tool_context: {e}")

                logger.info("-----------------OPENAI OBJECTIVES---------------------------------", )
                logger.info(f"openai system_prompt: {system_prompt}")
                logger.info(f"openai messages: {messages}")
                response = handle_openai_model(
                    messages=messages, system_prompt=system_prompt, max_token=company_bot.max_token,
                    temperature=company_bot.bot_temperature, company_bot=company_bot,
                    top_p=company_bot.filter_score if company_bot.filter_score else None,
                    tool_choice=tool_choice, tools=tools, stream=False, is_json_response=True
                )
            else:
                messages = [{
                    'role': 'user',
                    'content': [{'text': rendered_content}]
                }]

                system_prompt = [{'text': company_bot.context}]
                tool_context = company_bot.tool_context
                tool_context = json_repair.repair_json(tool_context, return_objects=True)

                response = handle_bedrock_model(
                    system_prompt=system_prompt, messages=messages, model_name=company_bot.llm_model,
                    temperature=company_bot.bot_temperature, max_token=company_bot.max_token, company_bot=company_bot,
                    tools=tool_context, top_p=company_bot.filter_score,
                )

            try:
                validate_bot = CompanyBot.objects.filter(route='/validate_objective_list').first()
                if validate_bot:
                    response = validate_and_fix_action_list(
                        messages=messages, response_json=response, company_bot=validate_bot
                    )
                    logger.info("Validation applied using validate_bot")
                else:
                    logger.info("No validate_bot found with route='/validate_objective_list', skipping validation")

            except CompanyBot.DoesNotExist:
                logger.error("validate_bot not found, proceeding without validation")
            except Exception as validation_error:
                logger.error(f"Validation failed: {validation_error}, proceeding with original response")

            if not response:
                return {
                    'status': 'error',
                    'status_code': 500,
                    'objective_list': [],
                    'chunks_response': chunks_response,
                    'message': 'Invalid response from LLM'
                }

            objective_list = parse_llm_objective_response(response, filtered_chunks)
            logger.info(f"objective_list: {objective_list}")

            if not objective_list:
                raise ValueError("LLM returned empty objectives list")

        except ValueError as e:
            return {
                'status': 'error',
                'status_code': 422,
                'objective_list': [],
                'chunks_response': chunks_response,
                'message': str(e)
            }

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
