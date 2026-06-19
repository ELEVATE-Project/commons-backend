import boto3
import os
import time
import requests
from shikshalokam.models import Project



def upload_file_to_s3(
    *,
    file_name: str,
    file_content,
    content_type: str,
    project_id: int | None,
    folder_structure: str
) -> str | None:

    try:
        id_prefix = f"{project_id}/" if project_id else ""
        key = f"{folder_structure}{id_prefix}{int(time.time())}-{file_name}"

        s3_client = boto3.client(
            "s3",
            region_name=os.getenv("AWS_REGION"),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        )

        upload_url = s3_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": os.getenv("S3_BUCKET_NAME"),
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=3600,
        )

        response = requests.put(
            upload_url,
            data=file_content,
            headers={"Content-Type": content_type},
        )

        if response.status_code == 200:
            return key

        print(f"S3 upload failed with status {response.status_code}")
        return None

    except Exception as e:
        print(f"S3 upload error: {str(e)}")
        return None

def upload_media(
    *,
    project_id: int,
    media_type: str,
    file_name: str,
    file_content,
    content_type: str,
    folder_structure: str = "shikshagraha_commons/",
):

    s3_key = upload_file_to_s3(
        file_name=file_name,
        file_content=file_content,
        content_type=content_type,
        project_id=project_id,
        folder_structure=folder_structure,
    )

    if not s3_key:
        return None

    base = os.getenv("S3_MEDIA_URL")
    media_url = f"{base}{s3_key}"

    existing_other_params = (
        Project.objects.filter(id=project_id)
        .values_list("other_params", flat=True)
        .first()
        or {}
    )

    existing_other_params[media_type] = {
        "url": media_url,
        "file_name": file_name,
    }

    Project.objects.filter(id=project_id).update(
        other_params=existing_other_params
    )

    return {
        "media_type": media_type,
        "url": media_url,
        "file_name": file_name,
    }