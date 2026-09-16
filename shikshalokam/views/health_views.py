from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import time

@csrf_exempt
@require_http_methods(["GET"])
def health_check(request):
    """Simple health check endpoint"""
    return JsonResponse({
        'status': 'healthy',
        'timestamp': int(time.time()),
        'service': 'shikshalokam-mohini'
    })
