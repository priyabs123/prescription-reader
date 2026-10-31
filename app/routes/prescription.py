from fastapi import APIRouter, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.errors import AppError
from app.schemas.prescription import (
    ConfigResponse,
    ExplainRequest,
    ExplainResponse,
    HealthResponse,
    UploadResponse,
)
from app.services import explanation_service, image_processing, ocr_service
from app.services.translation_service import SUPPORTED_LANGUAGES

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check():
    return HealthResponse(status="ok", app=settings.app_name)


@router.get("/config", response_model=ConfigResponse)
def get_config():
    """Tells the frontend what this server can do (so the page can show helpful hints)."""
    provider = ocr_service.resolve_provider()
    return ConfigResponse(
        app_name=settings.app_name,
        max_upload_mb=settings.max_upload_mb,
        languages=SUPPORTED_LANGUAGES,
        ocr_available=provider is not None,
        ocr_provider=provider,
        general_info_enabled=bool(settings.gemini_api_key and settings.enable_general_info),
    )


@router.post("/upload", response_model=UploadResponse)
async def upload_prescription(file: UploadFile = File(...), rotate: int = Form(0)):
    """Validate the image, check quality, run OCR. The image is never saved to disk."""
    max_bytes = settings.max_upload_mb * 1024 * 1024
    data = await file.read(max_bytes + 1)  # read one extra byte so we can detect "too large"
    await file.close()

    prepared = await run_in_threadpool(
        image_processing.prepare_image,
        data,
        file.filename or "",
        max_bytes=max_bytes,
        min_side=settings.min_image_side_px,
        rotate=rotate,
    )
    del data

    result = await run_in_threadpool(ocr_service.run_ocr, prepared.jpeg_bytes)
    text = result.text
    if not text:
        raise AppError(
            "No text could be found in this image. Please upload a clearer photo, "
            "or type the prescription text into the box.",
            code="no_text_found",
            status_code=422,
        )
    return UploadResponse(
        provider=result.provider,
        text=text,
        uncertain_words=result.uncertain_words,
        quality_warnings=prepared.warnings,
        notes=result.notes,
        image_width=prepared.width,
        image_height=prepared.height,
    )


@router.post("/explain", response_model=ExplainResponse)
async def explain_prescription(body: ExplainRequest):
    """Explain text the user has reviewed and confirmed."""
    if not body.user_confirmed:
        raise AppError(
            "Please confirm that you have checked the text against your prescription first.",
            code="not_confirmed",
            status_code=400,
        )
    return await run_in_threadpool(explanation_service.explain_text, body.text, body.language)
