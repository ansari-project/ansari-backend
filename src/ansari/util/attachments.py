"""Helpers for image attachments in chat messages.

Images are sent to the LLM only for the turn in which they are attached; they are never stored.
When a message is saved, each image block is replaced with a placeholder:
    {"type": "image_placeholder", "media_type": "image/png"}
so the UI can show that an image was attached and later turns can tell the LLM it is no longer available.
"""

import base64
import binascii
import copy

ALLOWED_IMAGE_MEDIA_TYPES = ("image/jpeg", "image/png", "image/gif", "image/webp")

IMAGE_PLACEHOLDER_TYPE = "image_placeholder"


def sniff_image_media_type(data: bytes) -> str | None:
    """Return the media type implied by the file's magic bytes, or None if unsupported."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def decode_and_validate_image(data_b64: str, media_type: str, max_bytes: int) -> bytes:
    """Decode a base64 image and check its type and size.

    Raises:
        ValueError: with a user-presentable message if the image is not acceptable.
    """
    if media_type not in ALLOWED_IMAGE_MEDIA_TYPES:
        raise ValueError(f"Unsupported image type '{media_type}'. Allowed: {', '.join(ALLOWED_IMAGE_MEDIA_TYPES)}")

    # Tolerate data URLs (e.g., "data:image/png;base64,....") sent by web clients
    if data_b64.startswith("data:") and "," in data_b64:
        data_b64 = data_b64.split(",", 1)[1]

    try:
        data = base64.b64decode(data_b64, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("Image data is not valid base64")

    if not data:
        raise ValueError("Image is empty")
    if len(data) > max_bytes:
        raise ValueError(f"Image is too large ({len(data)} bytes). Maximum is {max_bytes} bytes")

    actual_type = sniff_image_media_type(data)
    if actual_type != media_type:
        raise ValueError(f"Image content does not match declared type '{media_type}'")

    return data


def make_image_block(media_type: str, data: bytes) -> dict:
    """Build an Anthropic base64 image block."""
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": base64.b64encode(data).decode("ascii")},
    }


def is_base64_image_block(block) -> bool:
    return (
        isinstance(block, dict)
        and block.get("type") == "image"
        and isinstance(block.get("source"), dict)
        and block["source"].get("type") == "base64"
    )


def replace_images_with_placeholders(content):
    """Return `content` with base64 image blocks swapped for placeholders, so image data is never stored."""
    if not isinstance(content, list) or not any(is_base64_image_block(b) for b in content):
        return content
    return [
        {"type": IMAGE_PLACEHOLDER_TYPE, "media_type": block["source"]["media_type"]}
        if is_base64_image_block(block)
        else block
        for block in content
    ]


def count_image_placeholders(content) -> int:
    if not isinstance(content, list):
        return 0
    return sum(1 for b in content if isinstance(b, dict) and b.get("type") == IMAGE_PLACEHOLDER_TYPE)


def omitted_images_note(count: int) -> str:
    noun = "an image" if count == 1 else f"{count} images"
    return f"[The user attached {noun} to this message. It is no longer available; rely on your earlier reply.]"


def add_omitted_image_notes(messages: list[dict]) -> list[dict]:
    """Prepare display-format history (from `AnsariDB.get_thread`) for the LLM.

    Removes the `image_count` field (Claude rejects unknown fields) and, for user messages that had
    images, prepends a note so the LLM knows an image was there but can no longer be seen.
    """
    result = []
    for msg in messages:
        new_msg = {k: v for k, v in msg.items() if k != "image_count"}
        count = msg.get("image_count", 0)
        if msg.get("role") == "user" and count:
            text = msg.get("content") if isinstance(msg.get("content"), str) else ""
            new_msg["content"] = f"{omitted_images_note(count)}\n\n{text}" if text else omitted_images_note(count)
        result.append(new_msg)
    return result


def redact_images(value):
    """Return a deep copy with base64 image payloads replaced, for safe logging."""
    redacted = copy.deepcopy(value)

    def _walk(node):
        if isinstance(node, dict):
            if is_base64_image_block(node):
                data = node["source"].get("data", "")
                node["source"]["data"] = f"<{len(data)} base64 chars redacted>"
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(redacted)
    return redacted
