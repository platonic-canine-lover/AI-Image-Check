from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

FIXTURES = Path(__file__).parent / "fixtures"
CAI = FIXTURES / "caidata"
MADE = FIXTURES / "made"
GENERATORS = FIXTURES / "generators"


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Never read the trust lists cached on the machine running the tests."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))


@pytest.fixture
def test_trust() -> dict:
    """Trust settings whose only anchor is the C2PA TEST root, so 'Trusted'
    can be tested offline with the fixtures signed by it."""
    pem = (CAI / "es256_certs.pem").read_text()
    root = "-----BEGIN CERTIFICATE-----" + pem.split("-----BEGIN CERTIFICATE-----")[-1]
    return {"verify": {"verify_trust": True}, "trust": {"trust_anchors": root}}


def jpeg(**save_kwargs) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "teal").save(buf, "JPEG", **save_kwargs)
    return buf.getvalue()


def png(text: dict[str, str] | None = None) -> bytes:
    from PIL.PngImagePlugin import PngInfo
    info = PngInfo()
    for k, v in (text or {}).items():
        info.add_itxt(k, v)
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "teal").save(buf, "PNG", pnginfo=info)
    return buf.getvalue()


def xmp(body: str) -> bytes:
    return ('<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
            f'<rdf:Description {body}/></rdf:RDF></x:xmpmeta>').encode()


def pdf(xmp: bytes | None = None, **info: str) -> bytes:
    """A one-page PDF with the given document information fields
    (creator=, producer=, title=) and, optionally, an XMP packet."""
    from pypdf import PdfReader, PdfWriter
    buf = io.BytesIO()
    Image.new("RGB", (60, 80), "white").save(buf, "PDF", **info)
    if xmp is None:
        return buf.getvalue()
    writer = PdfWriter(clone_from=PdfReader(buf))
    writer.xmp_metadata = xmp
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
