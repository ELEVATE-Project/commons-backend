import json
import csv
from io import StringIO
from django.apps import apps
from django.views.generic import TemplateView
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator
from django.http import JsonResponse, HttpResponse
from django.views import View
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils.text import capfirst
from django.core.serializers.json import DjangoJSONEncoder


@method_decorator(staff_member_required, name='dispatch')
class GenericBatchUploadView(TemplateView):
    """Generic batch upload view that works with any model"""
    template_name = 'admin/generic_batch_upload.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get model from URL parameters
        app_label = self.kwargs.get('app_label')
        model_name = self.kwargs.get('model_name')

        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            context['error'] = f"Model {app_label}.{model_name} not found"
            return context

        # Get model metadata
        model_data = self.get_model_metadata(model)

        context['model_data'] = json.dumps(model_data, cls=DjangoJSONEncoder)
        context['model_name'] = model._meta.model_name
        context['model_verbose_name'] = model._meta.verbose_name_plural
        context['back_url'] = f"/admin/{app_label}/{model_name}/"
        context['template_url'] = f"/admin/{app_label}/{model_name}/batch-template/"
        context['import_url'] = f"/admin/{app_label}/{model_name}/batch-import/"

        return context

    def get_model_metadata(self, model):
        """Extract model field metadata for the frontend"""
        fields = []

        # Fields to always exclude
        excluded_fields = [
            'id', 'created_at', 'updated_at', 'created', 'modified',
            'created_by', 'updated_by', 'deleted_at', 'is_deleted'
        ]

        for field in model._meta.get_fields():
            # Skip auto-generated and excluded fields
            if field.auto_created or field.name in excluded_fields:
                continue

            # Skip reverse relations
            if field.many_to_many and not field.concrete:
                continue

            # Convert verbose_name to string to avoid JSON serialization issues
            verbose_name = str(field.verbose_name)

            field_info = {
                'name': field.name,
                'verbose_name': capfirst(verbose_name),
                'type': field.get_internal_type(),
                'required': not field.blank and not field.null,
                'max_length': getattr(field, 'max_length', None),
                'default_selected': not field.blank,  # Select non-blank fields by default
                'help_text': str(getattr(field, 'help_text', ''))
            }

            # Handle choices - convert to serializable format
            if hasattr(field, 'choices') and field.choices:
                field_info['choices'] = [
                    [str(choice[0]), str(choice[1])]
                    for choice in field.choices
                ]
            else:
                field_info['choices'] = None

            # Handle foreign keys
            if field.many_to_one or field.one_to_one:
                field_info['type'] = 'ForeignKey'
                field_info['related_model'] = field.related_model._meta.label

            # Handle many-to-many
            if field.many_to_many:
                field_info['type'] = 'ManyToManyField'
                field_info['related_model'] = field.related_model._meta.label

            fields.append(field_info)

        return {
            'model': model._meta.label,
            'fields': fields
        }


@method_decorator(staff_member_required, name='dispatch')
class GenericBatchTemplateView(View):
    """Generate CSV template for batch upload"""

    def post(self, request, app_label, model_name):
        try:
            data = json.loads(request.body)
            fields = data.get('fields', [])

            if not fields:
                return JsonResponse({'error': 'No fields selected'}, status=400)

            # Get model
            model = apps.get_model(app_label, model_name)

            # Create CSV
            output = StringIO()
            writer = csv.writer(output)

            # Write headers
            headers = []
            for field_name in fields:
                try:
                    field = model._meta.get_field(field_name)
                    headers.append(field_name)
                except:
                    headers.append(field_name)

            writer.writerow(headers)

            # Add a sample row with field descriptions
            sample_row = []
            for field_name in fields:
                try:
                    field = model._meta.get_field(field_name)

                    if field.choices:
                        # Show available choices with both value and display name
                        choices_str = '|'.join([f'{choice[0]}' for choice in field.choices])
                        sample_row.append(f'[Options: {choices_str}]')
                    elif field.get_internal_type() == 'DateField':
                        sample_row.append('YYYY-MM-DD')
                    elif field.get_internal_type() == 'DateTimeField':
                        sample_row.append('YYYY-MM-DD HH:MM:SS')
                    elif field.get_internal_type() == 'BooleanField':
                        sample_row.append('true|false')
                    elif field.get_internal_type() == 'IntegerField':
                        sample_row.append('123')
                    elif field.get_internal_type() == 'EmailField':
                        sample_row.append('email@example.com')
                    else:
                        sample_row.append(f'Sample {field.verbose_name}')
                except:
                    sample_row.append('Sample value')

            writer.writerow(sample_row)

            # Create response
            response = HttpResponse(output.getvalue(), content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="{model_name}_template.csv"'

            return response

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)


@method_decorator(staff_member_required, name='dispatch')
class GenericBatchImportView(View):
    """Process batch import of data with optimizations"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fk_cache = {}  # Cache for foreign key lookups
        self.m2m_cache = {}  # Cache for many-to-many lookups

    def post(self, request, app_label, model_name):
        try:
            data = json.loads(request.body)
            model_label = data.get('model')
            rows = data.get('data', [])

            if not rows:
                return JsonResponse({'error': 'No data provided'}, status=400)

            # Get model
            model = apps.get_model(app_label, model_name)

            # Clear caches for this batch
            self.fk_cache = {}
            self.m2m_cache = {}

            # Pre-load foreign keys for optimization
            self.preload_foreign_keys(model, rows)

            results = []
            total_rows = len(rows)

            # Process each row
            with transaction.atomic():
                for index, row_data in enumerate(rows):
                    try:
                        # Process the row
                        result = self.process_row(model, row_data, request.user)
                        result['progress'] = f"{index + 1}/{total_rows}"
                        results.append(result)
                    except Exception as e:
                        results.append({
                            'success': False,
                            'message': str(e),
                            'row_index': index,
                            'progress': f"{index + 1}/{total_rows}"
                        })

            # Calculate summary
            success_count = sum(1 for r in results if r['success'])
            error_count = len(results) - success_count

            return JsonResponse({
                'success': True,
                'results': results,
                'summary': {
                    'total': len(results),
                    'success': success_count,
                    'errors': error_count
                }
            })

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

    def preload_foreign_keys(self, model, rows):
        """Pre-load foreign keys to reduce queries"""
        fk_fields = {}

        # Identify FK fields and collect values
        for field in model._meta.fields:
            if field.many_to_one or field.one_to_one:
                fk_fields[field.name] = {
                    'field': field,
                    'values': set()
                }

        # Collect all FK values from rows
        for row in rows:
            for field_name, field_info in fk_fields.items():
                if field_name in row and row[field_name]:
                    field_info['values'].add(str(row[field_name]))

        # Batch load FKs
        for field_name, field_info in fk_fields.items():
            if field_info['values']:
                related_model = field_info['field'].related_model

                # Try loading by PK first
                pk_values = []
                for val in field_info['values']:
                    try:
                        pk_values.append(int(val))
                    except (ValueError, TypeError):
                        pass

                if pk_values:
                    for obj in related_model.objects.filter(pk__in=pk_values):
                        cache_key = f"{related_model._meta.label}:{obj.pk}"
                        self.fk_cache[cache_key] = obj

                # Try loading by name for remaining values
                if hasattr(related_model, 'name'):
                    name_values = [v for v in field_info['values']
                                   if f"{related_model._meta.label}:{v}" not in self.fk_cache]
                    if name_values:
                        for obj in related_model.objects.filter(name__in=name_values):
                            cache_key = f"{related_model._meta.label}:{obj.name}"
                            self.fk_cache[cache_key] = obj

    def process_row(self, model, row_data, user):
        """Process a single row of data with caching"""
        try:
            # Clean empty strings
            cleaned_data = {}

            for field_name, value in row_data.items():
                if value == '':
                    # Check if field can be null/blank
                    try:
                        field = model._meta.get_field(field_name)
                        if field.null:
                            cleaned_data[field_name] = None
                        elif field.blank:
                            cleaned_data[field_name] = ''
                        # Skip if field doesn't allow empty values
                    except:
                        pass
                else:
                    cleaned_data[field_name] = self.convert_field_value(model, field_name, value)

            # Handle foreign keys with caching
            for field_name, value in list(cleaned_data.items()):
                try:
                    field = model._meta.get_field(field_name)

                    if field.many_to_one or field.one_to_one:
                        if value:
                            related_model = field.related_model
                            cache_key = f"{related_model._meta.label}:{value}"

                            # Check cache first
                            if cache_key in self.fk_cache:
                                cleaned_data[field_name] = self.fk_cache[cache_key]
                            else:
                                # If not in cache, try to fetch (shouldn't happen with preloading)
                                try:
                                    obj = related_model.objects.get(pk=value)
                                    self.fk_cache[cache_key] = obj
                                    cleaned_data[field_name] = obj
                                except related_model.DoesNotExist:
                                    if hasattr(related_model, 'name'):
                                        try:
                                            obj = related_model.objects.get(name=value)
                                            self.fk_cache[cache_key] = obj
                                            cleaned_data[field_name] = obj
                                        except related_model.DoesNotExist:
                                            raise ValidationError(f"{field_name}: Related object not found")
                                    else:
                                        raise ValidationError(f"{field_name}: Related object not found")

                    elif field.many_to_many:
                        # Handle many-to-many separately after object creation
                        m2m_value = cleaned_data.pop(field_name)
                        # Store for later processing
                        cleaned_data[f'_m2m_{field_name}'] = m2m_value

                except Exception as e:
                    if field_name in cleaned_data:
                        # Keep the value for now, let model validation handle it
                        pass

            # Create object
            obj = model(**{k: v for k, v in cleaned_data.items() if not k.startswith('_m2m_')})

            # Handle special fields before validation
            if hasattr(obj, 'created_by'):
                try:
                    field = model._meta.get_field('created_by')
                    related_model = field.related_model

                    # If created_by expects a specific model (like Profile)
                    if related_model:
                        # Try to get the related instance based on the user
                        if hasattr(related_model, 'objects'):
                            # Common patterns: email, user, username
                            if hasattr(user, 'email'):
                                try:
                                    obj.created_by = related_model.objects.get(email=user.email)
                                except:
                                    try:
                                        obj.created_by = related_model.objects.get(user=user)
                                    except:
                                        pass
                except:
                    # If anything fails, just skip setting created_by
                    pass

            # Handle other auto-set fields
            if hasattr(obj, 'source_type') and not getattr(obj, 'source_type', None):
                # Try to find MANUAL choice
                try:
                    field = model._meta.get_field('source_type')
                    if hasattr(field, 'choices'):
                        for choice_value, choice_display in field.choices:
                            if 'MANUAL' in str(choice_value).upper():
                                obj.source_type = choice_value
                                break
                except:
                    pass

            if hasattr(obj, 'company') and not getattr(obj, 'company', None):
                # Try to set company from created_by profile
                if hasattr(obj, 'created_by') and obj.created_by:
                    if hasattr(obj.created_by, 'company'):
                        obj.company = obj.created_by.company

            # Validate
            obj.full_clean()

            # Save
            obj.save()

            # Handle many-to-many fields with batch loading
            for key, value in cleaned_data.items():
                if key.startswith('_m2m_'):
                    field_name = key[5:]  # Remove '_m2m_' prefix
                    if value:
                        # Assume comma-separated IDs or names
                        values = [v.strip() for v in str(value).split(',')]
                        field = model._meta.get_field(field_name)
                        related_model = field.related_model

                        # Collect PK and name values
                        pk_values = []
                        name_values = []

                        for val in values:
                            try:
                                pk_values.append(int(val))
                            except (ValueError, TypeError):
                                name_values.append(val)

                        # Batch load related objects
                        related_objects = []

                        if pk_values:
                            related_objects.extend(
                                related_model.objects.filter(pk__in=pk_values)
                            )

                        if name_values and hasattr(related_model, 'name'):
                            related_objects.extend(
                                related_model.objects.filter(name__in=name_values)
                            )

                        getattr(obj, field_name).set(related_objects)

            return {
                'success': True,
                'message': f'Created {model._meta.verbose_name} successfully',
                'object_id': obj.pk
            }

        except ValidationError as e:
            return {
                'success': False,
                'message': f'Validation error: {e.message_dict if hasattr(e, "message_dict") else str(e)}'
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'Error: {str(e)}'
            }

    def convert_field_value(self, model, field_name, value):
        """Convert string value to appropriate field type"""
        try:
            field = model._meta.get_field(field_name)

            if field.get_internal_type() == 'BooleanField':
                return value.lower() in ['true', '1', 'yes', 'on']
            elif field.get_internal_type() == 'IntegerField':
                return int(value) if value else None
            elif field.get_internal_type() == 'FloatField':
                return float(value) if value else None
            elif field.get_internal_type() == 'DecimalField':
                from decimal import Decimal
                return Decimal(value) if value else None
            elif field.get_internal_type() in ['DateField', 'DateTimeField']:
                if not value:
                    return None
                # Handle various date formats
                from django.utils.dateparse import parse_date, parse_datetime
                if field.get_internal_type() == 'DateTimeField':
                    return parse_datetime(value)
                else:
                    return parse_date(value)

            return value

        except:
            return value
