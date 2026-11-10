from aiimagecheck import credentials

from conftest import CAI, GENERATORS, MADE


def read(path, trust=None):
    return credentials.read(path.read_bytes(), trust=trust)


def test_no_credentials():
    c = read(CAI / "A.jpg")
    assert not c.present and not c.error


def test_algorithmic_media_is_not_ai():
    # A gradient made by a program: "algorithmicMedia", no training data.
    c = read(CAI / "C.jpg")
    assert c.present and c.state == "Valid"
    assert [a.source_type for a in c.actions] == ["algorithmicMedia"]
    assert not c.ai_made and not c.ai_edited


def test_ai_created():
    c = read(MADE / "ai-created.jpg")
    assert c.ai_made and not c.ai_edited
    assert c.actions[0].software == "Example Image Generator"


def test_ai_edited_keeps_the_original_thumbnail():
    c = read(MADE / "ai-edited.jpg")
    assert c.ai_edited and not c.ai_made
    assert c.original is not None and c.original.thumbnail.startswith(b"\xff\xd8")  # a JPEG


def test_ai_in_an_earlier_manifest_is_still_found():
    c = read(MADE / "ai-then-cropped.jpg")
    assert c.ai_made
    created = [a for a in c.actions if a.action == "c2pa.created"]
    assert created and not created[0].active


def test_tampered_image_and_broken_signature_are_invalid():
    assert read(CAI / "XCA.jpg").problems == ["assertion.dataHash.mismatch"]
    assert read(CAI / "E-sig-CA.jpg").problems == ["claimSignature.mismatch"]
    assert read(CAI / "XCA.jpg").state == "Invalid"


def test_trust_turns_valid_into_trusted(test_trust):
    assert read(MADE / "ai-created.jpg").state == "Valid"
    c = read(MADE / "ai-created.jpg", trust=test_trust)
    assert c.state == "Trusted" and c.trust_checked
    assert "signingCredential.untrusted" not in c.problems


def test_not_an_image():
    c = credentials.read(b"plain text, not an image")
    assert not c.present


def test_real_chatgpt_image_reads_valid_without_trust_lists():
    # OpenAI's certificate carries a C2PA signing use the library does not
    # accept by default; without the built-in list this read as "Invalid"
    # (certificate missing required EKU), i.e. a genuine image called broken.
    c = read(GENERATORS / "chatgpt-diwali.png")
    assert c.present and c.state == "Valid" and not c.problems
    assert c.ai_made and not c.ai_edited
    assert c.signer == "OpenAI OpCo, LLC" and not c.trust_checked
    created = [a for a in c.actions if a.action == "c2pa.created"]
    assert created[0].software == "ChatGPT gpt-image"
    assert created[0].source_type == "trainedAlgorithmicMedia"


def test_trust_settings_without_their_own_eku_list_get_the_built_in_one(test_trust):
    c = read(GENERATORS / "chatgpt-diwali.png", trust=test_trust)
    # Only the C2PA test root is trusted here, so OpenAI is valid but untrusted.
    assert c.state == "Valid" and c.trust_checked and not c.problems
