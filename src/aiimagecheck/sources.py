"""What the IPTC "digital source type" values mean for this tool.

C2PA actions and IPTC/XMP metadata both describe where an image came from
with the same IPTC vocabulary (https://cv.iptc.org/newscodes/digitalsourcetype/).
Only two values say generative AI. "algorithmicMedia" is NOT one of them: it
means made purely by an algorithm with no training data (a gradient, a
fractal), and treating it as AI would be a false accusation.
"""

IPTC_PREFIX = "http://cv.iptc.org/newscodes/digitalsourcetype/"

AI_MADE = {"trainedAlgorithmicMedia"}
AI_EDITED = {"compositeWithTrainedAlgorithmicMedia"}

# Plain-English readings for the report. Unknown values are shown as they are.
DESCRIPTIONS = {
    "trainedAlgorithmicMedia": "made by generative AI",
    "compositeWithTrainedAlgorithmicMedia": "combines AI-generated elements with other material",
    "algorithmicMedia": "made by an algorithm without AI training data (not AI)",
    "digitalCapture": "captured by a digital camera",
    "computationalCapture": "captured by a camera with computational processing (e.g. a phone's HDR)",
    "negativeFilm": "scanned from film",
    "positiveFilm": "scanned from film",
    "print": "scanned from a print",
    "humanEdits": "edited by a person",
    "algorithmicallyEnhanced": "enhanced by an algorithm",
    "compositeCapture": "a composite of several captures",
    "composite": "a composite of several images",
    "compositeSynthetic": "a composite including synthetic elements",
    "digitalCreation": "created digitally by a person",
    "screenCapture": "a screenshot",
    "dataDrivenMedia": "generated from data",
    "virtualRecording": "a recording of a virtual scene",
}


def short_name(value: str) -> str:
    """'http://cv.iptc.org/.../trainedAlgorithmicMedia' -> 'trainedAlgorithmicMedia'."""
    value = (value or "").strip()
    return value.rsplit("/", 1)[-1] if "/" in value else value


def describe(value: str) -> str:
    name = short_name(value)
    return DESCRIPTIONS.get(name, name)
