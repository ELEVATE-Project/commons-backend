from django.contrib import admin
from chatbot.filter.custom_date_from_filter import CustomAdvanceDateFilter
from shikshalokam.models.project_vernacular_model import ProjectVernacular


@admin.register(ProjectVernacular)
class ProjectVernacularAdmin(admin.ModelAdmin):
    list_display = ('project', 'language', 'created_at')
    list_filter = (CustomAdvanceDateFilter, 'project', 'language', 'project__project_id')

    raw_id_fields = ('project', 'task')

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        obj.save()
