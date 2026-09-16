from import_export.admin import ExportActionMixin, ImportMixin
from django.contrib import admin
from chatbot.filter.custom_date_from_filter import CustomAdvanceDateFilter
from shikshalokam.models.project_models import Project, Task, Evidence
from shikshalokam.resource import ExpertProjectResource


@admin.register(Project)
class ProjectAdmin(ImportMixin, ExportActionMixin, admin.ModelAdmin):
    resource_class = ExpertProjectResource
    list_display = ('project_id', 'actual_title', 'actual_duration', 'generated_by', 'created_at', )
    list_filter = (
        CustomAdvanceDateFilter, 'project_id', 'author', 'generated_by', 'actual_title',
        'expected_title', 'story__session'
    )
    raw_id_fields = ('author', 'story')
    readonly_fields = ('solution_download_count', )
    # inlines = [TaskInline, EvidenceInline]

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        obj.save()

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            if not instance.pk:
                instance.created_by = request.user
            instance.save()
        formset.save_m2m()

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('project_template', 'author').prefetch_related('task', 'evidence')


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('task_name', 'created_at', 'mandatory_task')
    list_filter = (CustomAdvanceDateFilter, 'task_id', 'project__project_id')
    search_fields = ('task_name', )
    raw_id_fields = ('project',)

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        obj.save()


@admin.register(Evidence)
class EvidenceAdmin(admin.ModelAdmin):
    list_display = ('evidence_link', 'created_at')
    list_filter = (CustomAdvanceDateFilter, 'task__task_name', 'project__project_id',)
    search_fields = ('evidence_link', )

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        obj.save()