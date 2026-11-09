"""Build the signed test images in tests/fixtures/made/.

They are signed with the C2PA project's public TEST certificate (in
fixtures/caidata, MIT-licensed from contentauth/c2pa-python), so they
validate but are never on a real trust list. Run from the repo root:

    python tests/make_fixtures.py
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import c2pa

HERE = Path(__file__).parent / "fixtures"
CAI = HERE / "caidata"
OUT = HERE / "made"
IPTC = "http://cv.iptc.org/newscodes/digitalsourcetype/"


def signer() -> c2pa.Signer:
    info = c2pa.C2paSignerInfo(alg=b"es256", sign_cert=(CAI / "es256_certs.pem").read_bytes(),
                               private_key=(CAI / "es256_private.key").read_bytes(), ta_url=None)
    return c2pa.Signer.from_info(info)


def sign(dest: Path, source: Path, actions: list[dict], parent: Path | None = None) -> None:
    manifest = {
        "claim_generator_info": [{"name": "ai-image-check test fixtures", "version": "1"}],
        "title": dest.name,
        "format": "image/jpeg",
        "assertions": [{"label": "c2pa.actions.v2", "data": {"actions": actions}}],
    }
    with c2pa.Builder(manifest) as b, signer() as s:
        if parent:
            with open(parent, "rb") as f:
                b.add_ingredient({"title": parent.name, "relationship": "parentOf", "label": "parent"}, "image/jpeg", f)
        with open(source, "rb") as src:
            out = io.BytesIO()
            b.sign(s, "image/jpeg", src, out)
    dest.write_bytes(out.getvalue())


def main() -> None:
    OUT.mkdir(exist_ok=True)
    plain = CAI / "A.jpg"
    opened = {"action": "c2pa.opened", "parameters": {"ingredientIds": ["parent"]}}

    # Made by a generator.
    sign(OUT / "ai-created.jpg", plain, [
        {"action": "c2pa.created", "softwareAgent": {"name": "Example Image Generator"},
         "digitalSourceType": IPTC + "trainedAlgorithmicMedia"}])
    # An ordinary photo with a generative fill.
    sign(OUT / "ai-edited.jpg", plain, [opened,
        {"action": "c2pa.edited", "softwareAgent": {"name": "Example Generative Fill"},
         "digitalSourceType": IPTC + "compositeWithTrainedAlgorithmicMedia"}], parent=plain)
    # The AI image, then cropped in an ordinary editor: the AI use is in the
    # earlier manifest only, and must still be found.
    sign(OUT / "ai-then-cropped.jpg", OUT / "ai-created.jpg", [opened,
        {"action": "c2pa.cropped", "softwareAgent": {"name": "Example Photo Editor"}}], parent=OUT / "ai-created.jpg")
    # A camera photo: credentials, no AI.
    sign(OUT / "camera.jpg", plain, [
        {"action": "c2pa.created", "softwareAgent": {"name": "Example Camera"},
         "digitalSourceType": IPTC + "digitalCapture"}])

    for f in sorted(OUT.glob("*.jpg")):
        with c2pa.Reader(str(f)) as r:
            print(f.name, json.loads(r.json()).get("validation_state"))


if __name__ == "__main__":
    main()
