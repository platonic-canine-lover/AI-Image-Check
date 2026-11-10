"""Find AI labels in an image's ordinary metadata (XMP, EXIF, PNG text).

These are the labels generators and editors write without signing anything:
the IPTC digital source type in XMP, a tool's name in EXIF "Software", the
prompt and settings Stable Diffusion tools put in PNG text chunks. They are
good evidence when present, but nothing protects them: anyone can add or
remove one, so the report calls them unverified.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError

from . import sources


@dataclass
class Label:
    where: str     # "XMP", "EXIF Software", "PNG text 'parameters'", ...
    value: str     # what it says, shortened
    meaning: str   # "ai_made", "ai_edited" or "ai_tool"


# Tool names that only appear on AI output. Each must be specific enough not
# to match ordinary software: "Gemini" alone is also a camera app and a
# zodiac sign, so only "Made with Google AI" style phrases count for Google.
AI_TOOLS = [
    r"Adobe Firefly", r"Generative Fill", r"Generative Expand",
    # Any one separator: EXIF text is ASCII, so "DALL·E" arrives as "DALL?E".
    r"DALL[\W_]?E", r"ChatGPT", r"OpenAI",
    r"Midjourney", r"Stable Diffusion", r"ComfyUI", r"NovelAI", r"InvokeAI",
    r"Leonardo\.Ai", r"Ideogram", r"Imagen", r"Made with Google AI", r"Edited with Google AI",
    r"Galaxy AI", r"Runway(?:ML| Gen)", r"Black Forest Labs", r"FLUX\.1", r"xAI Aurora",
]
_TOOL_RE = re.compile(r"\b(?:" + "|".join(AI_TOOLS) + r")\b", re.IGNORECASE)
_SOURCE_RE = re.compile(r"digitalsourcetype/([A-Za-z]+)")

# Tool names count only in fields that say which software made or changed
# the image, never in captions or descriptions: "a photo of OpenAI's office"
# is not an AI label. XMP writes these as attributes or as elements.
_XMP_TOOL_FIELDS = ("xmp:CreatorTool", "stEvt:softwareAgent", "photoshop:Credit", "Iptc4xmpCore:Credit", "pdf:Producer")
_XMP_FIELD_RE = re.compile(
    r"(" + "|".join(re.escape(f) for f in _XMP_TOOL_FIELDS) + r")"
    r"""\s*(?:=\s*"([^"]*)"|>([^<]*)<)""")

# PNG text keys that image-generation front ends write: Automatic1111 and
# Forge ("parameters": prompt, then "Steps: … Sampler: …"), ComfyUI ("prompt",
# "workflow" as JSON), NovelAI ("Comment" with its settings).
_A1111_RE = re.compile(r"\bSteps:\s*\d+.*\bSampler:", re.DOTALL)
_COMFY_RE = re.compile(r'"class_type"\s*:')


def find(data: bytes) -> tuple[list[Label], str]:
    """Labels found in the image, and an error string if Pillow cannot read it."""
    try:
        img = Image.open(io.BytesIO(data))
    except (UnidentifiedImageError, OSError) as err:
        return [], f"not an image Pillow can read: {err}"
    labels: list[Label] = []
    with img:
        _xmp(img, labels)
        _exif(img, labels)
        _png_text(img, labels)
    return dedupe(labels), ""


def _xmp(img: Image.Image, out: list[Label]) -> None:
    raw = img.info.get("xmp") or img.info.get("XML:com.adobe.xmp") or b""
    xmp_labels(raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw), out)


def xmp_labels(text: str, out: list[Label], tool_re: re.Pattern = _TOOL_RE) -> None:
    """AI labels in an XMP packet, from an image or any other file."""
    for name in _SOURCE_RE.findall(text):
        if name in sources.AI_MADE:
            out.append(Label("XMP digital source type", name, "ai_made"))
        elif name in sources.AI_EDITED:
            out.append(Label("XMP digital source type", name, "ai_edited"))
    for field_m in _XMP_FIELD_RE.finditer(text):
        value = field_m.group(2) or field_m.group(3) or ""
        if m := tool_re.search(value):
            out.append(Label(f"XMP {field_m.group(1)}", m.group(0), "ai_tool"))


def _exif(img: Image.Image, out: list[Label]) -> None:
    exif = img.getexif()
    for tag, where in ((0x0131, "EXIF Software"),):
        value = exif.get(tag)
        if isinstance(value, bytes):
            value = value.decode("utf-8", "replace")
        if isinstance(value, str) and (m := _TOOL_RE.search(value)):
            out.append(Label(where, m.group(0), "ai_tool"))


def _png_text(img: Image.Image, out: list[Label]) -> None:
    if img.format != "PNG":
        return
    for key, value in (img.info or {}).items():
        if not isinstance(value, str) or key in ("xmp", "XML:com.adobe.xmp"):
            continue
        if key == "parameters" and _A1111_RE.search(value):
            out.append(Label("PNG text 'parameters'", "Stable Diffusion generation settings", "ai_made"))
        elif key in ("prompt", "workflow") and _COMFY_RE.search(value):
            out.append(Label(f"PNG text '{key}'", "ComfyUI workflow", "ai_made"))
        elif key in ("Software", "Comment") and (m := _TOOL_RE.search(value)):
            out.append(Label(f"PNG text '{key}'", m.group(0), "ai_tool"))


def dedupe(labels: list[Label]) -> list[Label]:
    seen, out = set(), []
    for label in labels:
        key = (label.where, label.value.lower(), label.meaning)
        if key not in seen:
            seen.add(key)
            out.append(label)
    return out
