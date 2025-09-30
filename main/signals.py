# main/signals.py
from django.db.models.signals import pre_save
from django.dispatch import receiver
from .models import CustomUser
import boto3
from django.conf import settings

@receiver(pre_save, sender=CustomUser)
def delete_old_profile_image(sender, instance, **kwargs):
    if not instance.pk:  # Yangi ob'ekt bo‘lsa, hech narsa qilmaymiz
        return

    try:
        old_user = CustomUser.objects.get(pk=instance.pk)
    except CustomUser.DoesNotExist:
        return

    old_image = old_user.profile_image
    new_image = instance.profile_image

    if old_image and old_image != new_image:  # Eski rasm bor va yangi rasm bilan farqli bo‘lsa
        s3_client = boto3.client(
            's3',
            region_name=settings.AWS_S3_REGION_NAME,
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        try:
            # Backblaze B2’dan eski faylni o‘chirish
            s3_client.delete_object(
                Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                Key=old_image.name  # Fayl nomi, masalan: media/profiles/username_profile.jpg
            )
        except s3_client.exceptions.ClientError as e:
            print(f"Eski rasmni o‘chirishda xato: {e}")  # Production’da logging ishlatish tavsiya etiladi