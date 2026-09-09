import os
from django.core.exceptions import ValidationError

def validate_image_file(file_obj):
    """
    Rasm fayllarini tekshirish (JPG, JPEG, PNG, WEBP, SVG) - Max 5MB
    """
    if not file_obj:
        return
    
    allowed_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.svg']
    ext = os.path.splitext(file_obj.name)[1].lower()
    if ext not in allowed_extensions:
        raise ValidationError(f"Faqat rasm fayllari yuklanishi mumkin ({', '.join(allowed_extensions)}). Siz yuklagan fayl turi: {ext}")
        
    max_size = 5 * 1024 * 1024  # 5 MB
    if file_obj.size > max_size:
        raise ValidationError("Rasm hajmi 5MB dan oshmasligi lozim.")


def validate_document_file(file_obj):
    """
    Hujjat va o'quv materiallari fayllarini tekshirish - Max 50MB
    """
    if not file_obj:
        return
        
    allowed_extensions = ['.pdf', '.docx', '.doc', '.xls', '.xlsx', '.zip', '.rar', '.txt', '.png', '.jpg', '.jpeg', '.webp']
    ext = os.path.splitext(file_obj.name)[1].lower()
    if ext not in allowed_extensions:
        raise ValidationError(f"Ruxsat etilmagan hujjat formati: {ext}. Ruxsat etilgan turlar: {', '.join(allowed_extensions)}")
        
    max_size = 50 * 1024 * 1024  # 50 MB
    if file_obj.size > max_size:
        raise ValidationError("Hujjat hajmi 50MB dan oshmasligi lozim.")


def validate_pdf_file(file_obj):
    """
    Faqat PDF kitob va savol kitobchalari uchun - Max 100MB
    """
    if not file_obj:
        return
        
    ext = os.path.splitext(file_obj.name)[1].lower()
    if ext != '.pdf':
        raise ValidationError(f"Faqat PDF formati qabul qilinadi. Siz yuklagan fayl turi: {ext}")
        
    max_size = 100 * 1024 * 1024  # 100 MB
    if file_obj.size > max_size:
        raise ValidationError("PDF fayl hajmi 100MB dan oshmasligi lozim.")


def validate_video_file(file_obj):
    """
    Video darslar uchun - Max 200MB
    """
    if not file_obj:
        return
        
    allowed_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.webm']
    ext = os.path.splitext(file_obj.name)[1].lower()
    if ext not in allowed_extensions:
        raise ValidationError(f"Ruxsat etilmagan video formati: {ext}. Ruxsat etilgan turlar: {', '.join(allowed_extensions)}")
        
    max_size = 200 * 1024 * 1024  # 200 MB
    if file_obj.size > max_size:
        raise ValidationError("Video hajmi 200MB dan oshmasligi lozim.")


def check_file_upload(file_obj, validator_func):
    """
    Viewlar ichida qulay tekshirish uchun yordamchi funksiya.
    Qaytaradi: (is_valid: bool, error_message: str yoki None)
    """
    if not file_obj:
        return True, None
    try:
        validator_func(file_obj)
        return True, None
    except ValidationError as e:
        msg = e.messages[0] if hasattr(e, 'messages') and e.messages else str(e)
        return False, msg
