import os
import io
from django.http import JsonResponse, HttpResponse
from PIL import Image, UnidentifiedImageError
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def convert_image(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)

    image_file = request.FILES.get('image')
    if not image_file:
        return JsonResponse({'error': 'No image provided'}, status=400)

    try:
        # Try opening the image (supports HEIF via pillow-heif)
        image = Image.open(image_file)
        output_io = io.BytesIO()

        # Convert to JPEG
        image.save(output_io, format='JPEG')
        output_io.seek(0)

        # Create new filename
        original_name = os.path.splitext(image_file.name)[0]
        output_filename = f"{original_name}.jpg"

        # Return as downloadable JPEG
        response = HttpResponse(output_io, content_type='image/jpeg')
        response['Content-Disposition'] = f'attachment; filename="{output_filename}"'
        return response

    except UnidentifiedImageError:
        return JsonResponse({'error': 'Unidentified image file'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Conversion failed: {str(e)}'}, status=500)
