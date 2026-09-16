# Observability App Overview

## Introduction

The Observability app in Shikshalokam Backend is designed to provide comprehensive monitoring and evaluation of bot runs, test cases, and their metrics. It plays a critical role in ensuring the quality and reliability of chatbot interactions by automating the testing of LLM-based chatbots and capturing detailed run-time metrics.

## Purpose

- To track and evaluate chatbot test cases using automated, programmable metrics.
- To run asynchronous celery tasks for executing LLM test cases.
- To provide developer tools for managing bot runs, mappings to test cases, and metric tracking.
- To integrate with DeepEval for fine-grained metric evaluations like relevancy, toxicity, hallucination, and more.

## Key Components

### Admin
Provides Django admin interfaces for managing bot runs, test case mappings, and their statuses.

### Celery Tasks
Includes asynchronous tasks that execute test cases against LLMs, calculate metric scores, and store results.

### Utils
Utility functions for preparing chat message formats and scaffolding deep evaluation clients.

### Views
Contains REST API views for triggering test prompts and related developer-facing endpoints.

### URLs
Defines URL routing for observability endpoints, including debug toolbar integration.

### Models
Handles database models for test cases, runs, metrics, and mappings (docs in separate `models.md`).

### Tests
Placeholder and initial test cases for the observability app, intended to grow with feature development.

## Observability Workflow Summary
1. Developer configures test cases and metrics.
2. A bot run triggers async celery tasks to evaluate test cases.
3. Each test case is executed with the specified LLM and metrics are calculated.
4. Results are logged, saved, and aggregated.
5. Developers can view and analyze test run results via Django admin and API.

---
