# utils.py
import boto3
from django.conf import settings

def generate_presigned_url(object_name, expiration=3600):
    """Backblaze B2 uchun signed URL yaratish."""
    s3_client = boto3.client(
        's3',
        region_name=settings.AWS_S3_REGION_NAME,
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )
    try:
        response = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
                'Key': object_name,
            },
            ExpiresIn=expiration  # URLning amal qilish muddati (sekundlarda)
        )
        return response
    except Exception as e:
        print(f"Xato: {e}")
        return None