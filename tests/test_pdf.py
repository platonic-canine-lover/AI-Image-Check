import json

import pytest

from aiimagecheck import check, cli, credentials, pdf, report

from conftest import MADE, jpeg, pdf as make_pdf, xmp

IPTC = "http://cv.iptc.org/newscodes/digitalsourcetype/"


def verdict(data, trust=None):
    return check.check_bytes(data, "x.pdf", trust)


def found(data):
    labels, doc, err = pdf.find(data)
    assert not err
    return {(l.where, l.value, l.meaning) for l in labels}, doc


def tampered() -> bytes:
    # Change the page height after signing: one byte outside the record.
    data = bytearray((MADE / "ai-created.pdf").read_bytes())
    at = data.index(b"80", data.index(b"/MediaBox"))
    data[at:at + 2] = b"81"
    return bytes(data)


# --- Content Credentials in a PDF ---

def test_signed_pdf_made_with_ai(test_trust):
    c = credentials.read((MADE / "ai-created.pdf").read_bytes())
    assert c.present and c.state == "Valid" and c.ai_made
    r = verdict((MADE / "ai-created.pdf").read_bytes())
    assert r.verdict == report.AI_MADE and r.headline == "Made with AI." and r.kind == report.PDF
    assert "Recorded AI tool: Example Document Generator." in r.reasons
    trusted = verdict((MADE / "ai-created.pdf").read_bytes(), test_trust)
    assert "a signer on the C2PA trust lists" in " ".join(trusted.reasons)


def test_signed_pdf_with_no_ai_recorded():
    r = verdict((MADE / "typed.pdf").read_bytes())
    assert r.verdict == report.NO_AI_RECORDED


def test_pdf_changed_after_signing_is_broken():
    r = verdict(tampered())
    assert r.verdict == report.BROKEN
    assert "this PDF or its record changed after signing" in r.headline
    assert r.credentials.problems == ["assertion.dataHash.mismatch"]
    assert "The broken record claims AI was used." in r.reasons


# --- what the PDF says made it ---

def test_document_info_is_reported_but_ordinary_software_is_not_a_label():
    data = make_pdf(creator="Microsoft Word", producer="macOS Quartz PDFContext")
    labels, doc = found(data)
    assert labels == set()
    assert (doc.creator, doc.producer) == ("Microsoft Word", "macOS Quartz PDFContext")
    r = verdict(data)
    assert r.verdict == report.NONE
    assert any("written in Microsoft Word and made into a PDF by macOS Quartz PDFContext" in x for x in r.reasons)
    assert r.to_dict()["document"] == {"creator": "Microsoft Word", "producer": "macOS Quartz PDFContext"}
    assert "written in: Microsoft Word" in r.to_text()


@pytest.mark.parametrize("info, want", [
    ({"producer": "ChatGPT"}, ("PDF info Producer", "ChatGPT", "ai_tool")),
    ({"creator": "Microsoft Copilot in Word"}, ("PDF info Creator", "Microsoft Copilot", "ai_tool")),
    ({"creator": "Anthropic Claude"}, ("PDF info Creator", "Anthropic", "ai_tool")),
    ({"creator": "Adobe Firefly"}, ("PDF info Creator", "Adobe Firefly", "ai_tool")),
])
def test_ai_tool_named_as_the_maker_is_an_unverified_label(info, want):
    data = make_pdf(**info)
    assert found(data)[0] == {want}
    r = verdict(data)
    assert r.verdict == report.AI_LABEL and "(unverified)" in r.headline


def test_xmp_packet_in_a_pdf():
    made = make_pdf(xmp=xmp(f'xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/" Iptc4xmpExt:DigitalSourceType="{IPTC}trainedAlgorithmicMedia"'))
    assert found(made)[0] == {("XMP digital source type", "trainedAlgorithmicMedia", "ai_made")}
    assert verdict(made).headline == "AI label found: made with AI (unverified)."

    tool = make_pdf(xmp=xmp('xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmp:CreatorTool="Google Gemini"'))
    labels, doc = found(tool)
    # Labelled where it was found, and shown as the stated maker.
    assert labels == {("XMP xmp:CreatorTool", "Google Gemini", "ai_tool")}
    assert doc.creator == "Google Gemini"


@pytest.mark.parametrize("name, data", [
    ("a title that mentions ChatGPT", make_pdf(title="How I use ChatGPT at work", creator="LibreOffice Writer")),
    ("Copilot or Gemini alone", make_pdf(creator="Gemini Office Suite", producer="Copilot PDF")),
    ("algorithmicMedia is not AI",
     make_pdf(xmp=xmp(f'xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/" Iptc4xmpExt:DigitalSourceType="{IPTC}algorithmicMedia"'))),
    ("a description that mentions OpenAI",
     make_pdf(xmp=xmp('xmlns:dc="http://purl.org/dc/elements/1.1/" dc:description="Notes on the OpenAI office"'))),
    ("no metadata at all", make_pdf()),
])
def test_no_false_labels(name, data):
    assert found(data)[0] == set()
    assert verdict(data).verdict == report.NONE


# --- wording ---

def test_no_evidence_never_says_a_person_wrote_it():
    r = verdict(make_pdf())
    assert r.headline == "No AI evidence found. That does not mean a person wrote it."
    assert "image" not in r.headline
    assert "document" not in r.to_dict(), "no empty document block"


@pytest.mark.parametrize("data", [
    make_pdf(), make_pdf(producer="ChatGPT"), (MADE / "ai-created.pdf").read_bytes(), (MADE / "typed.pdf").read_bytes(),
])
def test_every_readable_pdf_report_says_the_text_is_not_judged(data):
    assert any("cannot tell whether the words were written by AI" in x for x in verdict(data).reasons)


def test_metadata_goes_to_the_terminal_as_one_printable_line():
    doc = found(make_pdf(creator="Word\x1b[31m\nsecond line" + "x" * 500))[1]
    assert "\x1b" not in doc.creator and "\n" not in doc.creator and len(doc.creator) == 200


# --- files that are not what they seem ---

def test_damaged_pdf_is_unreadable_not_a_crash():
    r = verdict(b"%PDF-1.7\nnot really a PDF")
    assert r.verdict == report.UNREADABLE and r.headline == "Could not read this PDF."
    assert verdict(make_pdf()[:300]).verdict == report.UNREADABLE


def test_password_protected_pdf_says_so():
    from io import BytesIO
    from pypdf import PdfReader, PdfWriter
    writer = PdfWriter(clone_from=PdfReader(BytesIO(make_pdf(producer="ChatGPT"))))
    writer.encrypt("secret", algorithm="RC4-128")  # needs no extra library
    out = BytesIO()
    writer.write(out)
    r = verdict(out.getvalue())
    assert r.verdict == report.UNREADABLE and "password-protected" in r.reasons[0]


def test_images_are_still_images():
    assert not pdf.is_pdf(jpeg())
    r = check.check_bytes(jpeg(), "x.jpg")
    assert r.kind == report.IMAGE and "image is real" in r.headline and "document" not in r.to_dict()


# --- command line ---

def test_cli_checks_images_and_pdfs_together(capsys):
    assert cli.main(["--json", str(MADE / "ai-created.pdf"), str(MADE / "ai-edited.jpg")]) == 0
    data = json.loads(capsys.readouterr().out)
    assert [(d["kind"], d["verdict"]) for d in data] == [("pdf", "ai_made"), ("image", "ai_edited")]
