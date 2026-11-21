import os
import uuid

from flask import current_app
from werkzeug.utils import secure_filename

MAX_BYTES = 5 * 1024 * 1024

# extension -> allowed file signatures (first bytes of a real file of that type)
SIGNATURES = {
    "pdf": [b"%PDF"],
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
    "png": [b"\x89PNG\r\n\x1a\n"],
}

# (key, label, required)
DOC_TYPES = [
    ("affiliation", "Board affiliation certificate", True),
    ("recognition", "State government recognition certificate", True),
    ("principal_id", "Principal's ID proof", True),
    ("trust", "Society or trust registration certificate", False),
    ("address_proof", "Address proof", False),
]


def _ext(filename):
    return filename.rsplit(".", 1)[-1].lower() if filename and "." in filename else ""


def check_upload(storage):
    """Return an error message, or None if the file is acceptable."""
    ext = _ext(storage.filename)
    if ext not in SIGNATURES:
        return "Only PDF, JPG or PNG files are allowed."

    stream = storage.stream
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(0)
    if size == 0:
        return "The file is empty."
    if size > MAX_BYTES:
        return "The file is larger than 5 MB."

    head = stream.read(8)
    stream.seek(0)
    if not any(head.startswith(sig) for sig in SIGNATURES[ext]):
        return "The file content does not match its type."
    return None


def save_upload(storage):
    """Save the file under a random name. Returns (stored_name, original_name, size)."""
    ext = _ext(storage.filename)
    folder = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(folder, exist_ok=True)
    stored = f"{uuid.uuid4().hex}.{ext}"
    path = os.path.join(folder, stored)
    storage.save(path)
    original = secure_filename(storage.filename) or f"document.{ext}"
    return stored, original, os.path.getsize(path)


def delete_upload(stored_name):
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], stored_name)
    try:
        os.remove(path)
    except OSError:
        pass