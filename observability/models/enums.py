from django.db import models
from django.utils.translation import gettext_lazy as _


class TestCaseInputFormat(models.TextChoices):
    JSON = 'json', _('JSON')
    TEXT = 'text', _('TEXT')


class TCRunStatus(models.TextChoices):
    RUNNING = 'running', _('RUNNING')
    COMPLETED = 'completed', _('COMPLETED')
    FAILED = 'failed', _('FAILED')


class TCStatus(models.TextChoices):
    PASS = 'pass', _('PASS')
    FAILED = 'failed', _('FAILED')


class TCRunMetrics(models.TextChoices):
    ANSWER_RELEVANCY = 'answer_relevancy', _('ANSWER_RELEVANCY')
    FAITHFULLNESS = 'faithfullness', _('FAITHFULLNESS')
    CONTEXTUAL_PRECISION = 'contextual_precision', _('CONTEXTUAL_PRECISION')
    CONTEXTUAL_RECALL = 'contextual_recall', _('CONTEXTUAL_RECALL')
    CONTEXTUAL_RELEVANCY = 'contextual_relevancy', _('CONTEXTUAL_RELEVANCY')
    BIAS = 'bias', _('BIAS')
    TOXICITY = 'toxicity', _('TOXICITY')
    SUMMARIZATION = 'summarization', _('SUMMARIZATION')
    PROMPT_ALLIGNMENT = 'prompt_allignment', _('PROMPT_ALLIGNMENT')
    HALLUCINATION = 'hallucination', _('HALLUCINATION')
    JSON_CORRECTNESS = 'json_correctness', _('JSON_CORRECTNESS')
    GEVAL = 'geval', _('GEVAL')
