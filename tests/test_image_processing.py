import io

import pytest
from PIL import Image

from app.services import image_processing as ip
from tests.helpers import blurred, darkened, make_prescription, to_bytes

MAX = 5 * 1024 * 1024


def prepare(data, name="rx.jpg", **kw):
    return ip.prepare_image(data, name, max_bytes=kw.pop("max_bytes", MAX), min_side=500, **kw)


def error_code(data, name="rx.jpg", **kw):
    with pytest.raises(ip.ImageValidationError) as info:
        prepare(data, name, **kw)
    return info.value.code


BASE = make_prescription()


# ---------- good photos ----------

def test_clear_image_passes_with_no_warnings():
    result = prepare(to_bytes(BASE))
    assert result.warnings == []
    assert result.metrics["sharpness"] > 0.15


def test_png_is_accepted():
    assert prepare(to_bytes(BASE, "PNG"), "rx.png").width == 1000


@pytest.mark.parametrize("scale", [0.6, 2.0, 3.5])
def test_clear_images_of_different_sizes_pass(scale):
    img = make_prescription(int(1000 * scale), int(1300 * scale), int(90 * scale), int(30 * scale))
    assert prepare(to_bytes(img)).warnings == []


def test_output_is_clean_jpeg_without_exif():
    img = BASE.copy()
    exif = Image.Exif()
    exif[0x010F] = "SecretPhoneMaker"
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    assert b"SecretPhoneMaker" in buf.getvalue()
    out = prepare(buf.getvalue())
    assert b"SecretPhoneMaker" not in out.jpeg_bytes
    assert Image.open(io.BytesIO(out.jpeg_bytes)).format == "JPEG"


def test_large_images_are_shrunk_for_ocr():
    big = make_prescription(3000, 3900, 270, 90)
    out = prepare(to_bytes(big))
    shrunk = Image.open(io.BytesIO(out.jpeg_bytes))
    assert max(shrunk.size) <= ip.MAX_OUTPUT_SIDE
    assert out.width == 3000  # the reported size is the original


def test_png_with_transparent_background_gets_white_background():
    """Transparent pixels would turn black in a plain JPEG conversion and hide the writing."""
    from PIL import ImageDraw

    from tests.helpers import LINES, _font

    rgba = Image.new("RGBA", (1000, 1300), (0, 0, 0, 0))
    draw = ImageDraw.Draw(rgba)
    for i, line in enumerate(LINES):
        draw.text((90, 90 + i * 66), line, fill=(20, 20, 60, 255), font=_font(30))
    out = prepare(to_bytes(rgba, "PNG"), "x.png")
    corner = Image.open(io.BytesIO(out.jpeg_bytes)).convert("L").getpixel((5, 5))
    assert corner > 240 and out.warnings == []


# ---------- orientation ----------

def test_exif_orientation_is_respected():
    img = make_prescription(1000, 800, 60, 28)  # landscape
    exif = Image.Exif()
    exif[0x0112] = 6  # "rotate 90 degrees clockwise to view"
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    out = prepare(buf.getvalue())
    assert (out.width, out.height) == (800, 1000)


def test_manual_rotation():
    out = prepare(to_bytes(make_prescription(1000, 800, 60, 28)), rotate=90)
    assert (out.width, out.height) == (800, 1000)


def test_invalid_rotation_rejected():
    assert error_code(to_bytes(BASE), rotate=45) == "bad_rotation"


# ---------- bad photos ----------

def test_blur_levels():
    assert prepare(to_bytes(blurred(BASE, 2))).warnings  # a little blurry -> warning
    assert error_code(to_bytes(blurred(BASE, 4))) == "too_blurry"
    assert error_code(to_bytes(blurred(BASE, 8))) == "too_blurry"


def test_dark_images():
    assert prepare(to_bytes(darkened(BASE, 0.3))).warnings  # dim -> warning
    assert error_code(to_bytes(darkened(BASE, 0.12))) == "too_dark"


def test_blank_image_rejected():
    assert error_code(to_bytes(Image.new("RGB", (1000, 1300), (250, 250, 250)))) == "low_contrast"


def test_too_small_image_rejected():
    assert error_code(to_bytes(BASE.resize((300, 390)))) == "image_too_small"


def test_cropped_writing_gets_a_warning():
    cropped = BASE.crop((60, 150, 700, 700)).resize((1000, 860))
    warnings = prepare(to_bytes(cropped)).warnings
    assert any("cut off" in w and "right" in w for w in warnings)


def test_dark_table_edge_is_not_called_cut_off_writing():
    img = BASE.copy()
    img.paste((30, 30, 30), (0, 0, 1000, 40))  # a strip of dark table along the top
    assert not any("cut off" in w for w in prepare(to_bytes(img)).warnings)


def test_very_long_narrow_image_warns():
    strip = make_prescription(600, 3000, 60, 24)
    assert any("long and narrow" in w for w in prepare(to_bytes(strip)).warnings)


# ---------- invalid uploads ----------

def test_empty_file():
    assert error_code(b"") == "empty_file"


def test_wrong_extension():
    assert error_code(to_bytes(BASE), "rx.gif") == "bad_file_type"
    assert error_code(to_bytes(BASE), "rx") == "bad_file_type"
    assert error_code(to_bytes(BASE), "rx.pdf") == "bad_file_type"


def test_extension_is_case_insensitive():
    assert prepare(to_bytes(BASE), "RX.JPG").width == 1000


def test_real_content_is_checked_not_just_the_name():
    gif = io.BytesIO()
    BASE.convert("P").save(gif, format="GIF")
    assert error_code(gif.getvalue(), "rx.jpg") == "bad_file_type"
    assert error_code(b"MZ\x90\x00 this is a program, not an image", "rx.png") == "unreadable_image"


def test_damaged_image():
    data = to_bytes(BASE)
    assert error_code(data[: len(data) // 3]) == "unreadable_image"


def test_too_large_file():
    with pytest.raises(ip.ImageValidationError) as info:
        prepare(to_bytes(BASE), max_bytes=1000)
    assert info.value.code == "file_too_large" and info.value.status_code == 413


def test_too_many_pixels_rejected():
    huge = Image.new("L", (9000, 6000), 255)  # 54 million pixels, tiny PNG
    assert error_code(to_bytes(huge, "PNG"), "x.png") == "image_too_large"
