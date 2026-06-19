from django.views.generic import TemplateView
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator
from django.http import JsonResponse
import json
import os
import traceback
from chatbot.utils.shiksha_chaupal.iterative_challenge_processor import run_iterative_challenge_filtering
from chatbot.utils.admin_config.config import (
    get_all_processing_types,
    get_processing_type_by_value,
    ProcessingType
)
from chatbot.celery_tasks.post_processing_tasks import run_unique_challenges_task, run_unique_solutions_task
from celery.result import AsyncResult


@method_decorator(staff_member_required, name='dispatch')
class PostProcessingView(TemplateView):
    """Post Processing view for Story model admin"""
    template_name = 'admin/post_processing/post_processing.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['model_name'] = 'Story'
        # Dynamically get all processing types from config
        context['processing_types'] = get_all_processing_types()
        return context
    
    def get(self, request, *args, **kwargs):
        """Handle GET requests - either render template or check task status"""
        task_id = request.GET.get('task_id')
        
        if task_id:
            # Check task status
            return self._check_task_status(task_id)
        
        # Normal template rendering
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        """Handle POST request for running the processing script"""
        try:
            processing_type = request.POST.get('processing_type', '')
            
            # Get processing type enum and validate
            processing_type_enum = get_processing_type_by_value(processing_type)
            if not processing_type_enum:
                return JsonResponse({
                    'success': False,
                    'error': f'Unknown processing type: {processing_type}'
                })
            
            # Dynamically extract and validate fields based on config
            config = self._extract_form_data(request, processing_type_enum)
            
            # Check for validation errors
            if 'error' in config:
                return JsonResponse({
                    'success': False,
                    'error': config['error']
                })
            
            # Common fields: file upload and date range
            input_file = request.FILES.get('input_file', None)
            date_from = request.POST.get('date_from', '').strip()
            date_till = request.POST.get('date_till', '').strip()
            
            # Validate at least one input source
            has_file = input_file is not None
            has_date_range = bool(date_from and date_till)
            
            if not has_file and not has_date_range:
                return JsonResponse({
                    'success': False,
                    'error': 'Please provide either an input file or a date range to begin processing.'
                })
            
            # Add common fields to config
            config.update({
                'processing_type': processing_type,
                'date_from': date_from,
                'date_till': date_till,
                'input_file': input_file.name if input_file else None,
                'has_file': has_file,
                'has_date_range': has_date_range
            })

            # Run the appropriate processing using dynamic routing
            # Get the handler method name from config
            handler_method_name = processing_type_enum.handler_method
            handler_method = getattr(self, handler_method_name, None)
            
            if handler_method:
                result = handler_method(config, input_file)
                return JsonResponse(result)
            else:
                return JsonResponse({
                    'success': False,
                    'error': f'Handler method {handler_method_name} not found for {processing_type}'
                })

        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'success': False,
                'error': str(e)
            })
    
    def _extract_form_data(self, request, processing_type_enum):
        """
        Dynamically extract and validate form fields based on processing type config.
        """
        from chatbot.utils.admin_config.config import get_processing_type_config
        
        config_data = get_processing_type_config(processing_type_enum)
        field_definitions = config_data.get('fields', [])
        
        extracted_data = {}
        
        for field_def in field_definitions:
            field_name = field_def['name']
            field_type = field_def['type']
            default_value = field_def.get('default')
            
            # Get value from request
            raw_value = request.POST.get(field_name)
            
            # Use default if not provided
            if raw_value is None or raw_value == '':
                extracted_data[field_name] = default_value
                continue
            
            # Type conversion and validation
            try:
                if field_type == 'number':
                    # Check if it has step (float) or is integer
                    if 'step' in field_def and field_def['step'] != 1:
                        converted_value = float(raw_value)
                    else:
                        converted_value = int(raw_value)
                    
                    # Validate min/max
                    if 'min' in field_def and converted_value < field_def['min']:
                        return {'error': f"{field_def['label']} must be at least {field_def['min']}"}
                    if 'max' in field_def and converted_value > field_def['max']:
                        return {'error': f"{field_def['label']} must be at most {field_def['max']}"}
                    
                    extracted_data[field_name] = converted_value
                
                elif field_type == 'select':
                    # Validate choice is in allowed choices
                    valid_choices = [choice['value'] for choice in field_def.get('choices', [])]
                    if valid_choices and raw_value not in valid_choices:
                        return {'error': f"Invalid value for {field_def['label']}"}
                    extracted_data[field_name] = raw_value
                
                elif field_type == 'text':
                    extracted_data[field_name] = raw_value.strip()
                
                else:
                    # Default: store as-is
                    extracted_data[field_name] = raw_value
                    
            except (ValueError, TypeError) as e:
                return {'error': f"Invalid value for {field_def['label']}: {str(e)}"}
        
        return extracted_data

    def _run_unique_challenges_processing(self, config, input_file):
        """Trigger async task for unique challenges processing."""
        
        # Prepare input file content if uploaded
        input_file_content = None
        
        if config.get('has_file') and input_file:
            try:
                # Read the uploaded file content
                content = input_file.read().decode('utf-8')
                input_file_content = content
            except Exception as e:
                return {
                    'success': False,
                    'error': f'Unable to read the uploaded file. Please ensure it is a valid JSON format.'
                }
        
        # Trigger the async Celery task
        try:
            import traceback
            
            task = run_unique_challenges_task.delay(config, input_file_content)
            
            print(f"✅ Task triggered successfully. Task ID: {task.id}")
            
            return {
                'success': True,
                'task_id': task.id,
                'message': 'Task has been started.'
            }
        except Exception as e:
            print(f"❌ Failed to trigger task: {str(e)}")
            traceback.print_exc()
            return {
                'success': False,
                'error': f'Failed to start task: {str(e)}'
            }

    def _run_unique_solutions_processing(self, config, input_file):
        """Trigger async task for unique solutions processing."""
        
        # Prepare input file content if uploaded
        input_file_content = None
        
        if config.get('has_file') and input_file:
            try:
                input_file_content = input_file.read().decode('utf-8')
                print(f"✅ Read input file: {input_file.name}")
            except Exception as e:
                return {'success': False, 'error': f'Failed to read file: {str(e)}'}
        
        # Trigger the async Celery task
        try:
            print(f"✅ Triggering unique solutions task with config: {config}")
            
            task = run_unique_solutions_task.delay(config, input_file_content)
            
            print(f"✅ Task triggered successfully. Task ID: {task.id}")
            
            return {
                'success': True,
                'task_id': task.id,
                'message': 'Task has been started.'
            }
        except Exception as e:
            print(f"❌ Failed to trigger task: {str(e)}")
            traceback.print_exc()
            return {
                'success': False,
                'error': f'Failed to start task: {str(e)}'
            }

    def _check_task_status(self, task_id):
        """Check the status of a Celery task."""
        try:
            task_result = AsyncResult(task_id)
            
            if task_result.state == 'PENDING':
                return JsonResponse({
                    'state': 'PENDING',
                    'status': 'Task is waiting to be processed...'
                })
            elif task_result.state == 'SUCCESS':
                result = task_result.result
                if result.get('success'):
                    return JsonResponse({
                        'state': 'SUCCESS',
                        'success': True,
                        'status': 'completed',
                        'message': result.get('message'),
                        'output_file': result.get('output_file'),
                        'iterations': result.get('iterations'),
                        'final_count': result.get('final_count'),
                        'category_counts': result.get('category_counts', {}),
                        'stats': result.get('stats', [])
                    })
                else:
                    return JsonResponse({
                        'state': 'SUCCESS',
                        'success': False,
                        'error': result.get('error', 'Processing failed')
                    })
            elif task_result.state == 'FAILURE':
                # Get detailed error information
                error_info = task_result.info
                error_message = str(error_info)
                
                # If it's an exception, get more details
                if hasattr(error_info, '__class__'):
                    error_message = f"{error_info.__class__.__name__}: {str(error_info)}"
                
                print(f"❌ Task FAILURE detected. Error: {error_message}")
                print(f"📊 Task result info: {task_result.info}")
                
                return JsonResponse({
                    'state': 'FAILURE',
                    'success': False,
                    'error': error_message
                })
            else:
                return JsonResponse({
                    'state': task_result.state,
                    'status': f'Task state: {task_result.state}'
                })
                
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Error checking task status: {str(e)}'
            })
    
    def _print_processing_output(self, config):
        processing_type = config.get('processing_type', '')
        
        print("\n" + "=" * 60)
        print("🚀 POST PROCESSING")
        print("=" * 60)
        
        if processing_type in ['unique_challenges', 'unique_solutions']:
            type_label = 'Challenges' if processing_type == 'unique_challenges' else 'Solutions'
            print(f"\n📋 Configuration:")
            print(f"   Type: Unique {type_label}")
            print(f"   MAX_WORKERS: {config.get('max_workers')}")
            print(f"   BATCH_SIZE: {config.get('batch_size')}")
            print(f"   MAX_ITERATIONS: {config.get('max_iterations')}")
            print(f"   FILTER_THRESHOLD: {config.get('filter_threshold')}%")
            
            if config.get('has_file'):
                print(f"   Input File: {config.get('input_file')}")
            
            if config.get('has_date_range'):
                print(f"   Date Range: {config.get('date_from')} to {config.get('date_till')}")
           
            print(f"\n✅ Processing complete!")
        else:
            print(f"❓ Unknown processing type: {processing_type}")
        
        print("=" * 60 + "\n")
