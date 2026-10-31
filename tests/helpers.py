"""Make synthetic prescription-like images for tests. No real patient data is used."""

import io

from PIL import Image, ImageDraw, ImageFilter, ImageFont

LINES = [
    "Dr. A. Kumar, MBBS            Date: 12/10/2026",
    "Patient: Test Person   Age: 30",
    "Rx",
    "1. Tab Paracetamol 500mg 1-0-1 after food x 5 days",
    "2. Cap Omeprazole 20 mg OD before breakfast",
    "3. Syp Cough syrup 5ml TDS",
    "4. Tab Metformin 500mg 1-0-1 after food",
]


def _font(size: int):
    for name in ("DejaVuSans.ttf", "LiberationSans-Regular.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make_prescription(width=1000, height=1300, margin=90, font_size=30) -> Image.Image:
    img = Image.new("RGB", (width, height), (250, 248, 240))
    draw = ImageDraw.Draw(img)
    font = _font(font_size)
    y = margin
    for line in LINES:
        draw.text((margin, y), line, fill=(20, 20, 60), font=font)
        y += int(font_size * 2.2)
    return img


def to_bytes(img: Image.Image, fmt="JPEG") -> bytes:
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def blurred(img: Image.Image, radius: float) -> Image.Image:
    return img.filter(ImageFilter.GaussianBlur(radius))


def darkened(img: Image.Image, factor: float) -> Image.Image:
    return Image.eval(img, lambda p: int(p * factor))
