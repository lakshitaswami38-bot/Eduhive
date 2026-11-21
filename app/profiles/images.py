import io
import os
import uuid
import warnings

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError

Image.MAX_IMAGE_PIXELS = 25_000_000  # protects the server from huge "decompression bomb" images
MAX_BYTES = 5 * 1024 * 1024
ALLOWED_FORMATS = {"JPEG", "PNG"}


class ImageError(Exception):
    """A photo the user uploaded cannot be accepted. The message is safe to show."""


def process_image(storage, max_side, prefer_png=False):
    """Check an uploaded photo and re-encode it. Returns (bytes, extension).

    Re-encoding gives us a clean file, shrinks big photos, and drops hidden
    metadata (phone photos often carry the GPS location where they were taken).
    Logos are kept as PNG (sharp edges). Other photos become JPEG unless transparent.
    """
    stream = storage.stream
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(0)
    if size == 0:
        raise ImageError("The file is empty.")
    if size > MAX_BYTES:
        raise ImageError("The photo is larger than 5 MB.")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            probe = Image.open(stream)
            image_format = probe.format
            probe.verify()
            stream.seek(0)
            image = Image.open(stream)
            image = ImageOps.exif_transpose(image)
            image.load()
    except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning,
            OSError, SyntaxError, ValueError):
        raise ImageError("This file is not a valid JPG or PNG photo.")

    if image_format not in ALLOWED_FORMATS:
        raise ImageError("Only JPG or PNG photos are allowed.")

    image.thumbnail((max_side, max_side))
    has_alpha = image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info)
    out = io.BytesIO()
    if has_alpha or prefer_png:
        image.convert("RGBA").save(out, "PNG", optimize=True)
        return out.getvalue(), "png"
    image.convert("RGB").save(out, "JPEG", quality=85, optimize=True)
    return out.getvalue(), "jpg"


def photo_folder():
    return os.path.join(current_app.config["UPLOAD_FOLDER"], "photos")


def save_image(data, extension):
    os.makedirs(photo_folder(), exist_ok=True)
    stored = f"{uuid.uuid4().hex}.{extension}"
    with open(os.path.join(photo_folder(), stored), "wb") as handle:
        handle.write(data)
    return stored


def delete_image(stored_name):
    try:
        os.remove(os.path.join(photo_folder(), stored_name))
    except OSError:
        pass