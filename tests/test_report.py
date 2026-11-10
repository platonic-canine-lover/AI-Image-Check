import pytest

from aiimagecheck import check, report

from conftest import CAI, GENERATORS, MADE, jpeg, xmp

IPTC = "http://cv.iptc.org/newscodes/digitalsourcetype/"


def verdict(path_or_bytes, trust=None):
    data = path_or_bytes if isinstance(path_or_bytes, bytes) else path_or_bytes.read_bytes()
    return check.check_bytes(data, "x", trust)


@pytest.mark.parametrize("path, want, headline", [
    (MADE / "ai-created.jpg", report.AI_MADE, "Made with AI."),
    (MADE / "ai-then-cropped.jpg", report.AI_MADE, "Made from an AI-generated image."),
    (MADE / "ai-edited.jpg", report.AI_EDITED, "Edited with AI."),
    (MADE / "camera.jpg", report.NO_AI_RECORDED, "Content Credentials found; they record no AI use."),
    (CAI / "C.jpg", report.NO_AI_RECORDED, None),
    (CAI / "XCA.jpg", report.BROKEN, None),
    (CAI / "E-sig-CA.jpg", report.BROKEN, None),
    (CAI / "A.jpg", report.NONE, None),
    (GENERATORS / "chatgpt-diwali.png", report.AI_MADE, "Made with AI."),
])
def test_verdicts(path, want, headline):
    r = verdict(path)
    assert r.verdict == want
    if headline:
        assert r.headline == headline


def test_no_evidence_never_says_real():
    r = verdict(CAI / "A.jpg")
    assert "does not mean the image is real" in r.headline
    assert any("strip" in reason for reason in r.reasons)


def test_signer_wording_depends_on_trust(test_trust):
    untrusted = " ".join(verdict(MADE / "ai-created.jpg").reasons)
    assert "unconfirmed" in untrusted and "trust lists not loaded" in untrusted
    trusted = " ".join(verdict(MADE / "ai-created.jpg", test_trust).reasons)
    assert "a signer on the C2PA trust lists" in trusted and "unconfirmed" not in trusted


def test_signed_but_not_on_the_lists_says_so():
    # Trust checking on, with an anchor that is not the test root: the
    # record is intact but the signer is unknown.
    pem = (CAI / "es256_certs.pem").read_text()
    leaf_only = pem.split("-----END CERTIFICATE-----")[0] + "-----END CERTIFICATE-----\n"
    r = verdict(MADE / "ai-created.jpg", {"verify": {"verify_trust": True}, "trust": {"trust_anchors": leaf_only}})
    text = " ".join(r.reasons)
    assert r.verdict == report.AI_MADE
    assert "NOT on the C2PA trust lists" in text


def test_a_label_without_credentials_is_unverified():
    data = jpeg(xmp=xmp(f'xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/" Iptc4xmpExt:DigitalSourceType="{IPTC}trainedAlgorithmicMedia"'))
    r = verdict(data)
    assert r.verdict == report.AI_LABEL
    assert "(unverified)" in r.headline


def test_garbage_is_unreadable():
    assert verdict(b"not an image at all").verdict == report.UNREADABLE


def test_json_carries_the_original_thumbnail_only_when_asked():
    r = verdict(MADE / "ai-edited.jpg")
    plain = r.to_dict()["credentials"]["ingredients"][0]
    assert plain["hasThumbnail"] and "thumbnail" not in plain
    full = r.to_dict(thumbnails=True)["credentials"]["ingredients"][0]
    assert full["thumbnail"].startswith("data:image/")
