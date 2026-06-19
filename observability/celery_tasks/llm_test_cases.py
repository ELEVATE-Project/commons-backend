import traceback
from celery import shared_task

from chatbot.llm_models.llm_script import handle_bedrock_model
from chatbot.services.core.prompt_builder import PromptBuilder
from chatbot.utils.llm import LLM
from observability.utils.preparechats import get_chat_dict
from observability.models.enums import TestCaseInputFormat, TCRunMetrics, TCStatus
from chatbot.models import CompanyBot, LLMProvider, CompanyChat, CompanyBotTypeChoices, CompanyStateMachine
from chatbot.utils.env_parser import load_env_to_dict
from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric, ContextualPrecisionMetric, ContextualRecallMetric, ContextualRelevancyMetric, BiasMetric, ToxicityMetric, SummarizationMetric, PromptAlignmentMetric, HallucinationMetric, GEval
from observability.utils.deepeval import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCase, ConversationalTestCase, Turn
import json
from django.db.models import Avg
from chatbot.utils.chat_utils import get_guided_chat


def execute_test_case(
    test_case,
    company_bot: CompanyBot,
    deepeval_llm_model: str,
    deepeval_llm_provider: str,
    tc_run_id: int,
):

    model = company_bot.llm_model
    provider = company_bot.provider
    temperature = company_bot.bot_temperature
    provider_keys = company_bot.provider_keys
    system_prompt = company_bot.context

    # dynamic imports due to circular dependencies
    from observability.models import CompanyBotTCRun, TCBotRunMetrics, BotRunTestCaseMap

    # if provider == LLMProvider.BEDROCK_CONVERSE:
    #     response = handle_bedrock_model(company_bot, system_prompt)


    metrics_val = {}
    deepeval_model_name = deepeval_llm_model

    if deepeval_llm_provider != LLMProvider.OPENAI:
        deepeval_model_name = deepeval_llm_provider + "/" + deepeval_llm_model

    deepeval_model = DeepEvalBaseLLM(model=deepeval_model_name)

    metrics_threshold = {}

    eval_metrics = list(TCBotRunMetrics.objects.filter(
        bot_tc_run=test_case.pk).all())
    for metric in eval_metrics:
        metrics_threshold[metric.metric_name] = metric.metric_threshold_value
        metric_args = {
            "threshold": metric.metric_threshold_value,
            "model": deepeval_model,
            "include_reason": True
        }

        if metric.metric_name == TCRunMetrics.GEVAL:
            metrics_val[metric.metric_name] = GEval(
                **metric_args)

        if metric.metric_name == TCRunMetrics.ANSWER_RELEVANCY:
            metrics_val[metric.metric_name] = AnswerRelevancyMetric(
                **metric_args)

        elif metric.metric_name == TCRunMetrics.FAITHFULLNESS:
            metrics_val[metric.metric_name] = FaithfulnessMetric(**metric_args)

        elif metric.metric_name == TCRunMetrics.CONTEXTUAL_PRECISION:
            metrics_val[metric.metric_name] = ContextualPrecisionMetric(
                **metric_args)

        elif metric.metric_name == TCRunMetrics.CONTEXTUAL_RECALL:
            metrics_val[metric.metric_name] = ContextualRecallMetric(
                **metric_args)

        elif metric.metric_name == TCRunMetrics.CONTEXTUAL_RELEVANCY:
            metrics_val[metric.metric_name] = ContextualRelevancyMetric(
                **metric_args)

        elif metric.metric_name == TCRunMetrics.BIAS:
            metrics_val[metric.metric_name] = BiasMetric(
                **metric_args)

        elif metric.metric_name == TCRunMetrics.TOXICITY:
            metrics_val[metric.metric_name] = ToxicityMetric(
                **metric_args)

        elif metric.metric_name == TCRunMetrics.SUMMARIZATION:
            metrics_val[metric.metric_name] = SummarizationMetric(
                **metric_args, assessment_questions=metric.assessment_questions)

        elif metric.metric_name == TCRunMetrics.PROMPT_ALLIGNMENT:
            metrics_val[metric.metric_name] = PromptAlignmentMetric(
                model=deepeval_model,
                prompt_instructions=metric.prompt_instructions,
                threshold=metric.metric_threshold_value
            )

        elif metric.metric_name == TCRunMetrics.HALLUCINATION:
            metrics_val[metric.metric_name] = HallucinationMetric(
                **metric_args)

        # need to do: Add JSON Relevency metric as well
        else:
            pass

    llm = LLM(
        model=model,
        provider=provider,
        temperature=temperature,
        llm_env_conf=load_env_to_dict(provider_keys)
    )

    testcase_input = test_case.testcase_input
    test_case_message = []
    response_log = {
        "input": testcase_input,
        "expected_output": test_case.expected_output,
        "retrieval_context": test_case.retrieval_context,
        "system_prompt": system_prompt,
        "messages": None,
        "actual_output": None,
        "errors": [],
        "metric_results": []
    }
    company_chats = None
    if test_case.chat_session:
        company_chats = CompanyChat.objects.select_related('sender', 'receiver').filter(session=test_case.chat_session.session).order_by('created_at').values("receiver", "receiver__id", "translated_message", "message", "status", "created_at")

        if company_bot.bot_type == CompanyBotTypeChoices.STATE_MACHINE:
            state_machine = CompanyStateMachine.objects.get(company_bot=company_bot, step=test_case.chat_session.current_step)
            system_prompt = PromptBuilder.build_system_prompt(company_bot, state_machine)
            response_log["system_prompt"] = system_prompt

    if test_case.input_format == TestCaseInputFormat.JSON:
        try:
            if test_case.chat_session is not None:
                test_case_message = get_guided_chat(company_bot, company_chats)

            else:
                test_case_message = json.loads(test_case.message)

        except Exception as e:
            error_msg = f"[JSON Parse Error] TestCase {test_case.pk}: {str(e)}"
            print(error_msg)
            response_log["errors"].append(error_msg)
            pass

    actual_output = None
    try:
        if provider == LLMProvider.BEDROCK_CONVERSE:
            actual_output = handle_bedrock_model(
                company_bot=company_bot,
                system_prompt=system_prompt if isinstance(system_prompt, list) else [{ "text": system_prompt }],
                messages=test_case_message,
                max_token=company_bot.max_token,
                temperature=company_bot.bot_temperature,
                model_name=company_bot.llm_model
            )
        response_log["actual_output"] = actual_output
        print("Actual Output: ", actual_output)
    except Exception as e:
        traceback.print_exc()
        error_msg = f"[LLM Prompt Error] TestCase {test_case.pk}: {str(e)}"
        response_log["errors"].append(error_msg)
    try:
        if test_case.input_format == TestCaseInputFormat.JSON:
            test_case_llm = LLMTestCase(
                input=json.dumps(test_case_message),
                actual_output=json.dumps(actual_output) if type(actual_output) is dict else actual_output,
                expected_output=test_case.expected_output,
                retrieval_context=test_case.retrieval_context.split("\n"),
            )
        else:
            test_case_llm = LLMTestCase(
                input=testcase_input,
                actual_output=json.dumps(actual_output) if type(actual_output) is dict else actual_output,
                expected_output=test_case.expected_output,
                retrieval_context=test_case.retrieval_context.split("\n"),
            )
        for metric in metrics_val:
            try:
                print("Running metric evaluation for --> " + metric)
                metrics_val[metric].measure(test_case_llm)
                print(metrics_val[metric].reason, "<< REASON")
                print(metrics_val[metric].score, "<< SCORE")
                print(metrics_val[metric])

                response_log["metric_results"].append({
                    "metric_name": metric,
                    "score": metrics_val[metric].score,
                    "reason": metrics_val[metric].reason,
                    "status": "PASS" if metrics_val[metric].is_successful() else "FAILED"
                })

                run_tc_map = BotRunTestCaseMap(
                    bot_run=CompanyBotTCRun(pk=tc_run_id),
                    test_case=test_case,
                    metric_name=metric,
                    score=metrics_val[metric].score,
                    reason=metrics_val[metric].reason,
                    response_log = json.dumps(response_log, indent=2),
                    status=TCStatus.PASS if metrics_val[metric].is_successful(
                    ) else TCStatus.FAILED
                )
                run_tc_map.save()
            except Exception as metric_err:
                error_msg = f"[Metric Eval Error] Metric {metric}, TestCase {test_case.pk}: {str(metric_err)}"
                print(error_msg)
                response_log["errors"].append(error_msg)

        print(list(metrics_val.keys()))

        print("Eval Metrics printed: ", eval_metrics, len(eval_metrics))
    except Exception as eval_err:
        traceback.print_exc()
        error_msg = f"[Eval Init Error] TestCase {test_case.pk}: {str(eval_err)}"
        print(error_msg)
        response_log["errors"].append(error_msg)
    finally:
        try:
            existing_metrics = set(
                BotRunTestCaseMap.objects.filter(
                    bot_run_id=tc_run_id,
                    test_case=test_case
                ).values_list('metric_name', flat=True)
            )

            for metric in metrics_val:
                if metric not in existing_metrics:
                    BotRunTestCaseMap.objects.create(
                        bot_run=CompanyBotTCRun(pk=tc_run_id),
                        test_case=test_case,
                        metric_name=metric,
                        score=0,
                        reason="Execution failed. See response_log for errors.",
                        response_log=json.dumps(response_log, indent=2),
                        status=TCStatus.FAILED
                    )

            if not metrics_val and not existing_metrics:
               print("No metric found.")
        except Exception as final_save_err:
            print(f"[Final Save Error] TestCase {test_case.pk}: {str(final_save_err)}")


@shared_task
def run(company_bot_id: int, tc_run_id: int):
        # dynamic imports due to circular dependencies
        from observability.models import CompanyBotTestCases, CompanyBotTCRun, TCBotRunMetrics, BotRunTestCaseMap
        from observability.models.enums import TCRunStatus

        company_bot = CompanyBot.objects.get(pk=company_bot_id)
        bot_tc_run = CompanyBotTCRun.objects.get(pk=tc_run_id)
        company_test_cases = list(CompanyBotTestCases.objects.filter(
            company_bot=CompanyBot(pk=company_bot_id)
        ).all())

        print(company_test_cases)
        # loads the test cases
        try:
            for test_case in company_test_cases:
                try:
                    print("Running Test for: ", test_case)
                    execute_test_case(
                        test_case,
                        company_bot= company_bot,
                        tc_run_id=tc_run_id,
                        deepeval_llm_model=bot_tc_run.llm_model,
                        deepeval_llm_provider=bot_tc_run.provider,
                    )
                except Exception as e:
                    print(f"[TC Run Error] TestCase {test_case.pk}: {str(e)}")
                    traceback.print_exc()
                    continue

                # NOTE:
                # solution
                # DONE: deepeval llm terminologies
                # DONE: threshold to be exposed to db
                # DONE: test cases metrics should be customizable
                # DONE: metric scores to be stored in the db
                # DONE: metric should be at test case level
                # DONE: chat session to be added to TC Run Test Case (prepare messages for chat sessions)
                # DONE: test case pass fail status
                # need to do: Verifier and checker company bot and testing
                # need to do: Langfuse integration with observability
                # need to do: if  test cases fail how to improve it??

            results = BotRunTestCaseMap.objects.filter(
                bot_run=CompanyBotTCRun(pk=tc_run_id)
            ).values('metric_name').annotate(avg_score=Avg('score'))

            tc_avg_results = {}

            for res in results:
                print("Final Results...")
                print(res["avg_score"], res["metric_name"])
                tc_avg_results[res["metric_name"]] = res["avg_score"]

            bot_tc_run.status = TCRunStatus.COMPLETED
            bot_tc_run.metrics_result = json.dumps(tc_avg_results)
            bot_tc_run.save()
        except Exception as e:
            print("Error: ", e)
            traceback.print_exc()
            bot_tc_run.status = TCRunStatus.FAILED
            bot_tc_run.save()
