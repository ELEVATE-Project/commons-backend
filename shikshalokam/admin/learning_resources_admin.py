from django.contrib import admin
from chatbot.filter.custom_date_from_filter import CustomAdvanceDateFilter
from shikshalokam.models import LearningResources


@admin.register(LearningResources)
class LearningResourcesAdmin(admin.ModelAdmin):
    list_display = ('project', 'name', 'created_at')
    list_filter = (CustomAdvanceDateFilter, 'project',)

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        obj.save()