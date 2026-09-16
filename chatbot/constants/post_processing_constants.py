from typing import Dict, List, Any


# -------------- REUSABLE FIELD DEFINITIONS ------------------

# -------------- CATEGORY CONSTANTS ------------------
CHALLENGE_CATEGORIES = [
    "Challenges",
    "Positive Observations",
    "Advocacy/Activity Logs",
    "Vague/Incomplete/Nonsense",
    "Redundant/Repetitive",
    "Solutions"
]

SOLUTION_CATEGORIES = [
    "Solution Proposals",
    "Implemented Success",
    "Challenge Restatement",
    "Vague Generalization",
    "Redundant/Repetitive",
]

# Fields for iterative processing (used by unique challenges, unique solutions, etc.)
ITERATIVE_PROCESSING_FIELDS: List[Dict[str, Any]] = [
    {
        'name': 'max_workers',
        'type': 'number',
        'label': 'Max Workers',
        'default': 2,
        'min': 1,
        'max': 4,
        'help_text': 'How many parallel workers to use for processing. Keep low (1-2) to avoid Celery conflicts.'
    },
    {
        'name': 'batch_size',
        'type': 'number',
        'label': 'Batch Size',
        'default': 100,
        'min': 1,
        'max': 1000,
        'help_text': 'How many items to process together in each batch.'
    },
    {
        'name': 'max_iterations',
        'type': 'number',
        'label': 'Max Iterations',
        'default': 10,
        'min': 1,
        'max': 50,
        'help_text': 'The system will keep filtering duplicates until this many rounds.'
    },
    {
        'name': 'filter_threshold',
        'type': 'number',
        'label': 'Filter Threshold (%)',
        'default': 10,
        'min': 1,
        'max': 100,
        'step': 0.1,
        'help_text': 'Stop processing when filtering is lower than this percentage. Lower percentage means aggressive filtering.'
    },
]


# -------------- PROCESSING TYPE CONFIGURATIONS ------------------

PROCESSING_TYPE_CONFIG: Dict[str, Dict[str, Any]] = {
    'unique_challenges': {
        'label': 'Unique Challenges',
        'template_name': 'admin/post_processing/forms/unique_challenges_form.html',
        'handler_method': '_run_unique_challenges_processing',
        'fields': ITERATIVE_PROCESSING_FIELDS
    },
    'unique_solutions': {
        'label': 'Unique Solutions',
        'template_name': 'admin/post_processing/forms/unique_solutions_form.html',
        'handler_method': '_run_unique_solutions_processing',
        'fields': ITERATIVE_PROCESSING_FIELDS
    },
}
