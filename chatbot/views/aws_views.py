from rest_framework.decorators import api_view
from rest_framework.response import Response
from chatbot.services.storage import StorageFactory
from chatbot.services.storage.base_storage_handler import UploadConfig
import time


@api_view(["POST"])
def get_presigned_url(request):
    """
    Generate a presigned URL for file upload using the configured cloud storage provider.
    
    Request body:
        - fileName: Name of the file to upload
        - fileType: MIME type of the file
        - storyId: Optional story identifier
        - folder_structure: Folder path prefix for organizing files
    
    Returns:
        - uploadUrl: Presigned URL for uploading the file
        - s3ObjectKey: Object key/path in storage
        - s3Url: Public URL for accessing the uploaded file
    """
    file_name = request.data.get("fileName")
    file_type = request.data.get("fileType")
    story_id = request.data.get("storyId")
    folder_structure = request.data.get("folder_structure")

    print(f"file_name: {file_name}, file_type: {file_type}, story_id: {story_id}")
    
    if not file_name or not file_type:
        return Response({"error": "Missing fileName or fileType"}, status=400)

    # Add timestamp to filename for uniqueness
    timestamp_ms = int(time.time() * 1000)
    file_name_with_timestamp = f"{timestamp_ms}-{file_name}"

    # Create upload configuration
    upload_config = UploadConfig(
        file_name=file_name_with_timestamp,
        file_type=file_type,
        folder_structure=folder_structure or '',
        entity_id=story_id if story_id else None,
        expires_in=3600
    )

    try:
        # Get storage handler from factory
        storage_handler = StorageFactory.get_storage_handler()
        
        # Generate presigned URL using the storage handler
        result = storage_handler.generate_presigned_url(upload_config)
        
        if not result.success:
            return Response({"error": result.error or "Failed to generate presigned URL"}, status=500)
        
        return Response({
            "uploadUrl": result.upload_url,
            "s3ObjectKey": result.object_key,
            "s3Url": result.object_url,
        })
    
    except ValueError as e:
        # Handle configuration errors
        return Response({"error": str(e)}, status=500)
    except Exception as e:
        # Handle unexpected errors
        return Response({"error": f"Internal server error: {str(e)}"}, status=500)


@api_view(["PUT"])
def upload_media_local(request, object_key):
    """
    Direct file upload endpoint for LOCAL storage provider.
    This endpoint mimics AWS S3's presigned URL behavior where client PUTs file directly.
    
    URL pattern: /api/storage/upload-local/<path:object_key>
    
    Args:
        request: HTTP PUT request with file in body
        object_key: Pre-generated object key from presigned URL (includes folder/timestamp/filename)
    
    Returns:
        - s3ObjectKey: Object key/path in storage
        - s3Url: Public URL for accessing the uploaded file
        - success: Boolean indicating upload success
    """
    if not request.body:
        return Response({"error": "No file data received"}, status=400)

    print(f"Uploading file to local storage: {object_key}")

    try:
        # Get storage handler
        storage_handler = StorageFactory.get_storage_handler()
        
        # Create a file-like object from request body
        from io import BytesIO
        file_obj = BytesIO(request.body)
        
        # Get file path from object_key
        import os
        from django.conf import settings
        
        storage_location = getattr(settings, 'MEDIA_ROOT', os.path.join(settings.BASE_DIR, 'media'))
        file_path = os.path.join(storage_location, object_key)
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Write file to disk
        with open(file_path, 'wb') as destination:
            destination.write(file_obj.read())
        
        # Get public URL
        public_url = storage_handler.get_public_url(object_key)
        
        print(f"Successfully uploaded file to local storage: {object_key}")
        
        return Response({
            "s3ObjectKey": object_key,
            "s3Url": public_url,
            "success": True
        })
    
    except ValueError as e:
        # Handle configuration errors
        return Response({"error": str(e)}, status=500)
    except Exception as e:
        # Handle unexpected errors
        import traceback
        traceback.print_exc()
        return Response({"error": f"Internal server error: {str(e)}"}, status=500)

