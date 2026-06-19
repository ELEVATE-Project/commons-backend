# Observability Celery Tasks

## Overview

The Observability app uses asynchronous Celery tasks to manage the execution and evaluation of chat bot test cases.

These tasks facilitate running LLM (Large Language Model) test cases, compute evaluation metrics for each test run, and persist the results for later analysis.

## Key Components

### execute_test_case function

This function is responsible for executing a single test case against a specified LLM model.

- Inputs include the test case object, LLM model name, various providers, system prompts, test run IDs, temperature, and provider keys.
- Dynamically imports required models to avoid circular dependencies.
- Uses the DeepEvalBaseLLM wrapper to load evaluation models.
- Defines a set of metrics to evaluate test output, including relevancy, faithfulness, precision, recall, bias, toxicity, summarization, prompt alignment, hallucination, etc.
- Executes the LLM prompt and captures the actual output and errors.
- Runs metric evaluations and persists results and status in the `BotRunTestCaseMap` model.

### run Celery Task

This shared_task function orchestrates the complete test run for a given bot:

- Retrieves the company bot and active test run details.
- Fetches all test cases associated with the bot.
- Iterates through each test case, calling `execute_test_case` for evaluation.
- Aggregates metric scores and updates run status accordingly.
- Handles errors gracefully and updates test run status to FAILED when necessary.

## Additional Notes

- This module leverages the `deepeval` package for sophisticated evaluation metrics.
- Integration with chatbot models and utility functions such as environment parsers and chat message formatters is essential.
- Results are stored with detailed logs, enabling detailed post-run analyses.

---

These celery tasks enable automated, scalable, and in-depth testing of chatbot behaviors, helping developers maintain quality assurance efficiently.
