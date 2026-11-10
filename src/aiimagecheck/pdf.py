"""Find what a PDF says about the software that made it.

A PDF names its makers in two places: the document information dictionary
("Creator" is the app the document was written in, "Producer" the software
that turned it into a PDF) and, often, an XMP packet saying the same. Like
image metadata, none of it is signed: it is what the file says, and anyone
can change it. The report shows both fields as they are, and counts one as
an AI label only when it names an AI tool or carries an IPTC AI source type.

This reads the file's records only. It does not read the text, and cannot
say whether a person or a model wrote it. Pictures inside the PDF are not
checked either.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

from pypdf import PdfReader

from . import labels
from .labels import Label

# Names that mean an AI tool when they appear as the software that made a
# document, on top of the image tools. "Gemini" and "Copilot" alone are too
# common as ordinary words and product names, so only the full names count.
DOC_TOOLS = [r"Anthropic", r"Google Gemini", r"Microsoft Copilot"]
_TOOL_RE = re.compile(r"\b(?:" + "|".join(labels.AI_TOOLS + DOC_TOOLS) + r")\b", re.IGNORECASE)
_XMP_VALUE_RE = r"""\s*(?:=\s*"([^"]*)"|>([^<]*)<)"""
_MAX_FIELD = 200  # characters of a field shown in the report


@dataclass
class Document:
    creator: str = ""    # the app the document was written in
    producer: str = ""   # the software that wrote the PDF


def is_pdf(data: bytes) -> bool:
    # The header may follow a little leading junk; readers accept that.
    return b"%PDF-" in data[:1024]


def find(data: bytes) -> tuple[list[Label], Document, str]:
    """AI labels, the document's stated makers, and an error if unreadable."""
    doc = Document()
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted and not reader.decrypt(""):
            return [], doc, "this PDF is password-protected, so its metadata can't be read"
        info = reader.metadata or {}
        doc.creator, doc.producer = _clean(info.get("/Creator")), _clean(info.get("/Producer"))
        packet = reader.root_object.get("/Metadata")
        xmp = packet.get_object().get_data().decode("utf-8", "replace") if packet is not None else ""
    except Exception as err:  # pypdf raises many unrelated types on damaged files
        return [], Document(), f"not a PDF that can be read: {_clean(str(err)) or type(err).__name__}"

    found: list[Label] = []
    for where, value in (("PDF info Creator", doc.creator), ("PDF info Producer", doc.producer)):
        if m := _TOOL_RE.search(value):
            found.append(Label(where, m.group(0), "ai_tool"))
    doc.creator = doc.creator or _xmp_field(xmp, "xmp:CreatorTool")
    doc.producer = doc.producer or _xmp_field(xmp, "pdf:Producer")
    labels.xmp_labels(xmp, found, tool_re=_TOOL_RE)
    return labels.dedupe(found), doc, ""


def _xmp_field(xmp: str, name: str) -> str:
    m = re.search(re.escape(name) + _XMP_VALUE_RE, xmp)
    return _clean(m.group(1) or m.group(2)) if m else ""


def _clean(value) -> str:
    """A metadata field as one printable line: it goes to a terminal."""
    if value is None:
        return ""
    return "".join(ch for ch in str(value) if ch.isprintable()).strip()[:_MAX_FIELD]
