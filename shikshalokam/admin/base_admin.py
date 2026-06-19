# Import all admin classes for backward compatibility
from shikshalokam.admin.category_admin import CategoryAdmin
from shikshalokam.admin.project_admin import ProjectAdmin, TaskAdmin, EvidenceAdmin
from shikshalokam.admin.learning_resources_admin import LearningResourcesAdmin

__all__ = [
    'CategoryAdmin',
    'ProjectAdmin',
    'TaskAdmin',
    'EvidenceAdmin',
    'LearningResourcesAdmin',
]
