"""
Base model file - Re-exports all models for backward compatibility.
Actual model definitions are now in specialized files:
- template_models.py: Category, ProjectTemplate
- project_models.py: Project, Task, Evidence, LearningResources
"""

from shikshalokam.models.template_models import Category, ProjectTemplate
from shikshalokam.models.project_models import Project, Task, Evidence, LearningResources

__all__ = [
    'Category',
    'ProjectTemplate',
    'Project',
    'Task',
    'Evidence',
    'LearningResources',
]
