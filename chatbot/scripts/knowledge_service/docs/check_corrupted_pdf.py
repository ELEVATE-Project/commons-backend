import os
import django
import boto3

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "shikshalokam.settings")
django.setup()

from chatbot.models import Media

s3 = boto3.client("s3", region_name="ap-south-1")
BUCKET = os.getenv('S3_BUCKET_NAME')


def is_valid_pdf(bucket, key):
    try:
        # Read first 1KB
        head = s3.get_object(
            Bucket=bucket,
            Key=key,
            Range="bytes=0-1023"
        )["Body"].read()

        if not head.startswith(b"%PDF"):
            return False, "Missing PDF header"

        # Read last 1KB
        tail = s3.get_object(
            Bucket=bucket,
            Key=key,
            Range="bytes=-1024"
        )["Body"].read()

        if b"%%EOF" not in tail:
            return False, "Missing PDF EOF"

        return True, None

    except Exception as e:
        return False, str(e)


def check_corrupted_pdfs(limit=None):
    qs = Media.objects.filter(file__iendswith=".pdf")

    if limit:
        qs = qs[:limit]

    corrupted = []

    print(f"\nValidating {qs.count()} PDF files...\n")

    for media in qs:
        key = media.file.name
        ok, reason = is_valid_pdf(BUCKET, key)

        if not ok:
            corrupted.append((media.id, reason))
            print(f"❌ CORRUPTED: Media {media.id} → {reason}")

    print("\n===== SUMMARY =====")
    print(f"Checked     : {qs.count()}")
    print(f"Corrupted   : {len(corrupted)}")

    return corrupted


# Run
# check_corrupted_pdfs()
