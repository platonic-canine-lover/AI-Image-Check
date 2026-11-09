import pytest

from aiimagecheck import labels

from conftest import CAI, jpeg, png, xmp

IPTC = "http://cv.iptc.org/newscodes/digitalsourcetype/"


def meanings(data):
    found, err = labels.find(data)
    assert not err
    return {(l.meaning, l.value) for l in found}


@pytest.mark.parametrize("name, data, want", [
    ("XMP source type: AI made",
     jpeg(xmp=xmp(f'xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/" Iptc4xmpExt:DigitalSourceType="{IPTC}trainedAlgorithmicMedia"')),
     {("ai_made", "trainedAlgorithmicMedia")}),
    ("XMP source type: AI edited",
     jpeg(xmp=xmp(f'xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/" Iptc4xmpExt:DigitalSourceType="{IPTC}compositeWithTrainedAlgorithmicMedia"')),
     {("ai_edited", "compositeWithTrainedAlgorithmicMedia")}),
    ("XMP creator tool", jpeg(xmp=xmp('xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmp:CreatorTool="Adobe Firefly"')),
     {("ai_tool", "Adobe Firefly")}),
    ("XMP history software agent, element form",
     jpeg(xmp=b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><stEvt:softwareAgent>Midjourney v7</stEvt:softwareAgent></x:xmpmeta>'),
     {("ai_tool", "Midjourney")}),
])
def test_metadata_labels(name, data, want):
    assert meanings(data) == want


def exif_jpeg(software: str) -> bytes:
    from PIL import Image
    e = Image.Exif()
    e[0x0131] = software
    return jpeg(exif=e.tobytes())


def test_exif_software():
    # EXIF text is ASCII: Pillow stores "DALL·E" as "DALL?E", as real files do.
    assert meanings(exif_jpeg("DALL·E 3")) == {("ai_tool", "DALL?E")}
    assert meanings(exif_jpeg("DALL-E 2")) == {("ai_tool", "DALL-E")}
    assert meanings(exif_jpeg("Adobe Photoshop 26.1")) == set(), "an ordinary editor is not an AI label"


def test_png_generator_settings():
    a1111 = "a cat in a hat\nNegative prompt: blurry\nSteps: 30, Sampler: DPM++ 2M, CFG scale: 7, Seed: 1"
    assert meanings(png({"parameters": a1111})) == {("ai_made", "Stable Diffusion generation settings")}
    comfy = '{"3": {"class_type": "KSampler", "inputs": {}}}'
    assert meanings(png({"prompt": comfy})) == {("ai_made", "ComfyUI workflow")}
    assert meanings(png({"Software": "NovelAI"})) == {("ai_tool", "NovelAI")}


@pytest.mark.parametrize("name, data", [
    ("a caption that mentions OpenAI",
     jpeg(xmp=xmp('xmlns:dc="http://purl.org/dc/elements/1.1/" dc:description="Photo of the OpenAI office in London"'))),
    ("algorithmicMedia is not AI",
     jpeg(xmp=xmp(f'xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/" Iptc4xmpExt:DigitalSourceType="{IPTC}algorithmicMedia"'))),
    ("a PNG 'parameters' chunk without generation settings", png({"parameters": "width=800"})),
    ("a PNG description that mentions Midjourney", png({"Description": "I tried Midjourney once"})),
    ("no metadata at all", jpeg()),
    ("the official sample with no credentials", (CAI / "A.jpg").read_bytes()),
])
def test_no_false_labels(name, data):
    assert meanings(data) == set()


def test_not_an_image():
    found, err = labels.find(b"not an image")
    assert found == [] and err
