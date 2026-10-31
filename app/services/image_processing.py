"""Validate an uploaded image and check whether it is good enough to read.

Everything happens in memory. Nothing is written to disk.
The image is re-encoded as a clean JPEG, which also removes EXIF data
(such as GPS location) from phone photos.

The quality checks are simple heuristics using only Pillow. They catch obvious
problems (very dark, blank, very blurry, writing cut off at the edge). They cannot guarantee that OCR will work.
"""

import io
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps, ImageStat, UnidentifiedImageError

from app.core.errors import AppError

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
ALLOWED_FORMATS = {"JPEG", "PNG"}
MAX_OUTPUT_SIDE = 2000
ANALYSIS_SIDE = 1200
Image.MAX_IMAGE_PIXELS = 50_000_000  # protects against "decompression bomb" files

# Quality thresholds. They were tuned on synthetic test images, so the hard limits (ERROR)
# are deliberately gentle: we only reject photos that are clearly unusable.
DARK_ERROR = 35  # average brightness 0-255
DARK_WARN = 70
RANGE_ERROR = 20  # gap between ink and paper brightness (0-255)
RANGE_WARN = 70
SHARP_ERROR = 0.035  # relative sharpness, see _relative_sharpness (sharp text is about 0.25)
SHARP_WARN = 0.10
BORDER_RUNS_WARN = 2  # this many separate marks touching one edge = writing may be cut off
BORDER_MAX_INK = 0.6  # a mostly dark edge is a table or shadow, not writing


class ImageValidationError(AppError):
    status_code = 422
    code = "invalid_image"


@dataclass
class PreparedImage:
    jpeg_bytes: bytes
    width: int
    height: int
    warnings: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def _percentile(hist: list[int], q: float) -> int:
    """Brightness value below which a share q (0 to 1) of the pixels lie."""
    target = sum(hist) * q
    running = 0
    for value, count in enumerate(hist):
        running += count
        if running >= target:
            return value
    return 255


def _ink_paper_range(gray: Image.Image) -> tuple[int, int]:
    """Brightness of the ink (darkest 0.5%) and of the paper (the 90th percentile).

    Prescriptions are mostly empty paper, so the usual standard deviation is
    misleading. Comparing ink and paper directly works for sparse writing too.
    """
    hist = gray.histogram()
    return _percentile(hist, 0.005), _percentile(hist, 0.90)


def _relative_sharpness(gray: Image.Image, ink_paper_range: int) -> float:
    """How sharp the edges are compared with how dark the ink is.

    Sharp text has very strong edges (a value near 0.25). Blurred text has weak edges.
    Dividing by the ink contrast makes the number the same for bright and dim photos.
    """
    kernel = (0, 1, 0, 1, -4, 1, 0, 1, 0)  # Laplacian: responds to edges
    edges = gray.filter(ImageFilter.Kernel((3, 3), kernel, scale=8, offset=128))
    hist = edges.histogram()
    strongest = max(abs(_percentile(hist, 0.995) - 128), abs(_percentile(hist, 0.005) - 128))
    return strongest / max(ink_paper_range / 2, 1.0)


def _border_cuts(gray: Image.Image, ink_level: float) -> list[str]:
    """Sides of the photo where writing seems to run off the edge."""
    w, h = gray.size
    strip = max(3, int(min(w, h) * 0.012))
    boxes = {
        "top": (0, 0, w, strip),
        "bottom": (0, h - strip, w, h),
        "left": (0, 0, strip, h),
        "right": (w - strip, 0, w, h),
    }
    cut = []
    for side, box in boxes.items():
        part = gray.crop(box).point(lambda p: 255 if p < ink_level else 0)
        horizontal = side in ("top", "bottom")
        length = part.size[0] if horizontal else part.size[1]
        line = part.resize((length, 1) if horizontal else (1, length), Image.BOX)
        marks = [v > 8 for v in line.tobytes()]  # True where any ink touches the edge
        ink_share = sum(marks) / max(len(marks), 1)
        runs, gap, in_run = 0, 0, False
        for m in marks:
            if m:
                if not in_run:
                    runs += 1
                    in_run = True
                gap = 0
            elif in_run:
                gap += 1
                if gap > 8:  # a gap this long ends one mark
                    in_run = False
        if runs >= BORDER_RUNS_WARN and ink_share < BORDER_MAX_INK:
            cut.append(side)
    return cut


def measure_quality(img: Image.Image) -> dict:
    gray = ImageOps.grayscale(img)
    gray.thumbnail((ANALYSIS_SIDE, ANALYSIS_SIDE))
    ink, paper = _ink_paper_range(gray)
    spread = paper - ink
    return {
        "brightness": round(ImageStat.Stat(gray).mean[0], 1),
        "ink_paper_range": spread,
        "sharpness": round(_relative_sharpness(gray, spread), 3),
        "border_cuts": _border_cuts(gray, (ink + paper) / 2) if spread >= RANGE_ERROR else [],
    }


def prepare_image(
    data: bytes,
    filename: str,
    *,
    max_bytes: int,
    min_side: int,
    rotate: int = 0,
) -> PreparedImage:
    """Validate the upload, fix orientation, check quality, return clean JPEG bytes."""
    if not data:
        raise ImageValidationError("The file is empty. Please choose a prescription image.", code="empty_file")
    if len(data) > max_bytes:
        raise ImageValidationError(
            f"The image is too large. Please upload a file smaller than {max_bytes // (1024 * 1024)} MB.",
            code="file_too_large",
            status_code=413,
        )
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ImageValidationError(
            "Only JPG, JPEG and PNG images are allowed.", code="bad_file_type", status_code=415
        )
    if rotate not in (0, 90, 180, 270):
        raise ImageValidationError("Rotation must be 0, 90, 180 or 270 degrees.", code="bad_rotation")

    # Check the real content, not just the file name.
    try:
        with Image.open(io.BytesIO(data)) as probe:
            if probe.format not in ALLOWED_FORMATS:
                raise ImageValidationError(
                    "Only JPG, JPEG and PNG images are allowed.", code="bad_file_type", status_code=415
                )
            if probe.size[0] * probe.size[1] > Image.MAX_IMAGE_PIXELS:  # size is read from the header only
                raise ImageValidationError(
                    "This image has too many pixels. Please upload a smaller photo.", code="image_too_large"
                )
        img = Image.open(io.BytesIO(data))
        img.load()
    except ImageValidationError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError, ValueError):
        raise ImageValidationError(
            "This file could not be opened as an image. It may be damaged. Please upload another photo.",
            code="unreadable_image",
        )

    img = ImageOps.exif_transpose(img)  # respect the phone's orientation flag
    if img.mode in ("RGBA", "LA", "P"):
        rgba = img.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[-1])
        img = background
    else:
        img = img.convert("RGB")

    if rotate:
        img = img.rotate(-rotate, expand=True)  # clockwise, as shown by the Rotate buttons

    width, height = img.size
    if min(width, height) < min_side:
        raise ImageValidationError(
            f"The image is too small ({width}x{height}). Please upload a larger, clearer photo "
            f"(at least {min_side} pixels on the short side).",
            code="image_too_small",
        )

    metrics = measure_quality(img)
    warnings: list[str] = []

    if metrics["brightness"] < DARK_ERROR:
        raise ImageValidationError(
            "The photo is too dark to read. Please take a new photo in good light.", code="too_dark"
        )
    if metrics["ink_paper_range"] < RANGE_ERROR:
        raise ImageValidationError(
            "The photo looks blank or washed out. Please take a clearer photo with the whole "
            "prescription visible.",
            code="low_contrast",
        )
    if metrics["sharpness"] < SHARP_ERROR:
        raise ImageValidationError(
            "The photo is too blurry to read. Please hold the phone steady and upload a clearer photo.",
            code="too_blurry",
        )

    if metrics["brightness"] < DARK_WARN:
        warnings.append("The photo is quite dark. A brighter photo will give better results.")
    if metrics["brightness"] > 245 and metrics["ink_paper_range"] < 100:
        warnings.append("The photo looks overexposed. Avoid flash glare.")
    elif metrics["ink_paper_range"] < RANGE_WARN:
        warnings.append("The writing has low contrast against the paper. It may be hard to read.")
    if metrics["sharpness"] < SHARP_WARN:
        warnings.append("The photo is a little blurry. Check the extracted text carefully.")
    if metrics["border_cuts"]:
        warnings.append(
            "Writing may be cut off near the " + ", ".join(metrics["border_cuts"]) + " edge. "
            "Make sure the whole prescription is inside the photo."
        )
    if max(width, height) / max(1, min(width, height)) > 4:
        warnings.append("The image is very long and narrow. It may be cropped.")

    out = img.copy()
    out.thumbnail((MAX_OUTPUT_SIDE, MAX_OUTPUT_SIDE))
    buffer = io.BytesIO()
    out.save(buffer, format="JPEG", quality=90)  # new JPEG has no EXIF/GPS data
    return PreparedImage(
        jpeg_bytes=buffer.getvalue(),
        width=width,
        height=height,
        warnings=warnings,
        metrics=metrics,
    )
