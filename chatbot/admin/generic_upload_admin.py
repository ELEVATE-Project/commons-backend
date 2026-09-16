import json
from django.urls import path, reverse
from django.template.response import TemplateResponse
from django.http import JsonResponse


class BatchUploadMixin:
    """
    Mixin to add batch upload functionality to any ModelAdmin

    Usage:
        class YourModelAdmin(BatchUploadMixin, admin.ModelAdmin):
            list_display = ['name', 'email', ...]
            # Enable batch upload
            enable_batch_upload = True
            # Optional: customize which fields are available for import
            batch_upload_fields = ['name', 'email', 'phone']
    """

    enable_batch_upload = False

    batch_upload_fields = None

    batch_upload_exclude = []

    def get_urls(self):
        """Add batch upload URLs"""
        urls = super().get_urls()

        if not self.enable_batch_upload:
            return urls

        my_urls = [
            path('batch-upload/',
                 self.admin_site.admin_view(self.batch_upload_view),
                 name=f'{self.model._meta.app_label}_{self.model._meta.model_name}_batch_upload'),
            path('batch-template/',
                 self.admin_site.admin_view(self.batch_template_view),
                 name=f'{self.model._meta.app_label}_{self.model._meta.model_name}_batch_template'),
            path('batch-import/',
                 self.admin_site.admin_view(self.batch_import_view),
                 name=f'{self.model._meta.app_label}_{self.model._meta.model_name}_batch_import'),
        ]

        return my_urls + urls

    def changelist_view(self, request, extra_context=None):
        """Add batch upload button to changelist"""
        extra_context = extra_context or {}

        if self.enable_batch_upload:
            extra_context.update({
                'has_batch_upload': True,
                'batch_upload_url': reverse(
                    f'admin:{self.model._meta.app_label}_{self.model._meta.model_name}_batch_upload'
                )
            })

        return super().changelist_view(request, extra_context=extra_context)

    def batch_upload_view(self, request):
        """Render batch upload page"""
        from chatbot.views.admin.generic_upload_views import GenericBatchUploadView

        view = GenericBatchUploadView()
        view.kwargs = {
            'app_label': self.model._meta.app_label,
            'model_name': self.model._meta.model_name
        }

        # Add admin-specific context
        context = view.get_context_data()
        context.update({
            'opts': self.model._meta,
            'has_view_permission': self.has_view_permission(request),
            'has_add_permission': self.has_add_permission(request),
            'has_change_permission': self.has_change_permission(request),
        })

        # Apply field restrictions if set
        if self.batch_upload_fields:
            model_data = json.loads(context['model_data'])
            model_data['fields'] = [
                f for f in model_data['fields']
                if f['name'] in self.batch_upload_fields
            ]
            context['model_data'] = json.dumps(model_data)

        # Apply exclusions
        if self.batch_upload_exclude:
            model_data = json.loads(context['model_data'])
            model_data['fields'] = [
                f for f in model_data['fields']
                if f['name'] not in self.batch_upload_exclude
            ]
            context['model_data'] = json.dumps(model_data)

        return TemplateResponse(
            request,
            'admin/generic_batch_upload.html',
            context
        )

    def batch_template_view(self, request):
        """Generate template file"""
        from chatbot.views.admin.generic_upload_views import GenericBatchTemplateView

        view = GenericBatchTemplateView()
        return view.post(
            request,
            self.model._meta.app_label,
            self.model._meta.model_name
        )

    def batch_import_view(self, request):
        """Process batch import"""
        from chatbot.views.admin.generic_upload_views import GenericBatchImportView

        view = GenericBatchImportView()
        return view.post(
            request,
            self.model._meta.app_label,
            self.model._meta.model_name
        )


class SmartBatchUploadMixin(BatchUploadMixin):
    """
    Enhanced version with additional features:
    - Auto-detect foreign key relationships
    - Handle file uploads
    - Custom field processors
    - Performance optimizations
    """

    # Define custom field processors
    field_processors = {}

    # Enable batch loading for better performance
    batch_load_foreign_keys = True

    # Cache size limit (to prevent memory issues)
    max_cache_size = 1000

    def process_field_value(self, field_name, value, row_data):
        """
        Override this to add custom field processing

        Example:
            def process_field_value(self, field_name, value, row_data):
                if field_name == 'category':
                    # Auto-create category if doesn't exist
                    cat, created = Category.objects.get_or_create(name=value)
                    return cat
                return super().process_field_value(field_name, value, row_data)
        """
        if field_name in self.field_processors:
            return self.field_processors[field_name](value, row_data)
        return value

    def pre_batch_import(self, request, data):
        """
        Override to add pre-import validation or processing

        Example:
            def pre_batch_import(self, request, data):
                # Check if user has permission to import this many records
                if len(data) > 1000 and not request.user.is_superuser:
                    raise PermissionError("Only superusers can import more than 1000 records")
        """
        pass

    def post_batch_import(self, request, results):
        """
        Override to add post-import actions

        Example:
            def post_batch_import(self, request, results):
                # Send email notification
                successful = sum(1 for r in results if r['success'])
                if successful > 0:
                    send_import_notification(request.user, successful)
        """
        pass

    def batch_import_view(self, request):
        """Enhanced batch import with hooks for customization"""
        from chatbot.views.admin.generic_upload_views import GenericBatchImportView
        import json

        if request.method == 'POST':
            try:
                # Parse request data
                data = json.loads(request.body)
                rows = data.get('data', [])

                # Call pre-import hook
                self.pre_batch_import(request, rows)

                # Create view instance
                view = GenericBatchImportView()

                # Enable optimizations if set
                if hasattr(self, 'batch_load_foreign_keys'):
                    view.batch_load_foreign_keys = self.batch_load_foreign_keys

                # Process the import
                response = view.post(
                    request,
                    self.model._meta.app_label,
                    self.model._meta.model_name
                )

                # If successful, call post-import hook
                if response.status_code == 200:
                    response_data = json.loads(response.content)
                    if response_data.get('success'):
                        self.post_batch_import(request, response_data.get('results', []))

                return response

            except PermissionError as e:
                return JsonResponse({'error': str(e)}, status=403)
            except Exception as e:
                return JsonResponse({'error': str(e)}, status=400)

        return JsonResponse({'error': 'Method not allowed'}, status=405)


class AdvancedBatchUploadMixin(SmartBatchUploadMixin):
    """
    Advanced features for complex use cases:
    - Custom validators
    - Duplicate handling
    - Update existing records
    """

    # Enable updating existing records
    allow_update_existing = False

    # Fields to use for matching existing records
    update_lookup_fields = []

    # How to handle duplicates: 'skip', 'update', 'error'
    duplicate_handling = 'error'

    def find_existing_record(self, model, row_data):
        """
        Find existing record based on lookup fields

        Example:
            update_lookup_fields = ['email']  # Will match by email
            update_lookup_fields = ['name', 'company']  # Will match by both
        """
        if not self.update_lookup_fields:
            return None

        lookup_kwargs = {}
        for field in self.update_lookup_fields:
            if field in row_data and row_data[field]:
                lookup_kwargs[field] = row_data[field]

        if not lookup_kwargs:
            return None

        try:
            return model.objects.get(**lookup_kwargs)
        except model.DoesNotExist:
            return None
        except model.MultipleObjectsReturned:
            # If multiple records match, treat as not found
            return None

    def validate_row(self, row_data, row_index):
        """
        Custom validation for each row

        Override this to add custom validation logic
        Return tuple: (is_valid, error_message)
        """
        return True, None

    def handle_duplicate(self, existing_record, new_data):
        """
        Handle duplicate records based on duplicate_handling setting

        Override this for custom duplicate handling
        """
        if self.duplicate_handling == 'skip':
            return {
                'success': True,
                'message': 'Skipped - record already exists',
                'action': 'skipped'
            }
        elif self.duplicate_handling == 'update':
            # Update existing record
            for field, value in new_data.items():
                if not field.startswith('_'):  # Skip internal fields
                    setattr(existing_record, field, value)
            existing_record.save()
            return {
                'success': True,
                'message': 'Updated existing record',
                'action': 'updated',
                'object_id': existing_record.pk
            }
        else:  # 'error'
            return {
                'success': False,
                'message': 'Duplicate record found',
                'action': 'error'
            }
