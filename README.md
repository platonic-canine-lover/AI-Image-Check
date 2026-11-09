# AI Image Check

Says whether an image's **own records** show it was made or edited with AI,
and, when the record kept one, shows the image it was made from.

```
$ aiimagecheck tests/fixtures/made/ai-edited.jpg
tests/fixtures/made/ai-edited.jpg
  Edited with AI.
  - Recorded AI tool: Example Generative Fill.
  - Signed by C2PA Test Signing Cert, which is NOT on the C2PA trust lists: the record is intact, but who signed it is unconfirmed.
  - The record keeps a thumbnail of the image it was made from (A.jpg).
  ...
```

(A test image, signed with the C2PA test certificate, hence "NOT on the
trust lists". An image from a real signer says so instead.)

It reports evidence, never a guess. When there is no evidence it says so,
and that means **unknown**, not **real**.

## What it reads

| Evidence | Strength | Where it comes from |
|---|---|---|
| **Content Credentials** (C2PA) | Signed. Can't be altered without the check failing. | Adobe Firefly and Photoshop, OpenAI, Google, Microsoft, some cameras and phones |
| **Metadata labels** | Unverified. Anyone can add or remove one. | IPTC "digital source type" in XMP, the creating tool's name, the settings Stable Diffusion and ComfyUI write into PNGs |

Content Credentials answer three separate questions, and the report keeps
them separate:

1. **Is the record intact?** If the image or its record changed after
   signing, the record is reported as broken and nothing it says is trusted.
2. **Who signed it?** A valid signature proves the record wasn't altered. It
   does not prove who made it: anyone can create a certificate that says
   "OpenAI". So the signer is checked against the public C2PA trust lists.
3. **What happened?** Created or edited, by which tool, and whether
   generative AI was involved, read from every step in the record, so an AI
   image later cropped in an ordinary editor is still reported as AI.

Only two IPTC values mean generative AI: `trainedAlgorithmicMedia` (made by
AI) and `compositeWithTrainedAlgorithmicMedia` (partly AI). The similar
`algorithmicMedia` means made by a program *without* training data (a
gradient, a fractal) and is deliberately not counted.

## What it can't do

- **Show the original image** unless the record kept a thumbnail of it.
  Editing tools that write Content Credentials often do; nothing else does.
- **Spot an AI image whose records were stripped.** Most apps and platforms
  remove metadata on upload, and a screenshot removes everything. A
  detector model that guesses from the pixels is planned (v2), but only
  after it has been measured on a labelled test set: a wrong "this is AI" on
  someone's real photo does harm.
- **Read invisible watermarks** such as Google's SynthID. Only their makers
  can check those.

## Install

Python 3.10 or later.

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/aiimagecheck update-trust     # download the C2PA trust lists (do this first)
```

## Use

```sh
aiimagecheck photo.jpg more.png          # a report per image
aiimagecheck --json photo.jpg            # the same, as JSON
aiimagecheck photo.jpg --save-originals out/   # save any recorded source thumbnails
aiimagecheck serve                       # a page at http://127.0.0.1:3103 to drop images onto
aiimagecheck update-trust                # refresh the trust lists
```

The page runs on this computer only (it refuses any non-loopback address),
and images never leave it.

### Verdicts

| Verdict | Meaning |
|---|---|
| `ai_made` | Content Credentials say generative AI made it (or the image it came from) |
| `ai_edited` | Content Credentials say AI was used to change it |
| `no_ai_recorded` | Content Credentials are present and record no AI use |
| `broken` | Content Credentials are present but fail validation; not trusted |
| `ai_label` | No Content Credentials, but an unverified AI label in the metadata |
| `no_evidence` | Nothing either way. Not the same as real |
| `unreadable` | Not an image this tool can open |

Exit status: `0` all files read, `1` a file could not be read, `2` bad usage.

### Trust lists

`update-trust` downloads two public lists into `~/.cache/aiimagecheck`:
the [C2PA conformance trust list](https://github.com/c2pa-org/conformance-public)
and the Content Credentials interim list used by
[contentcredentials.org/verify](https://contentcredentials.org/verify),
which covers signers from before the conformance programme. They are not
shipped with the code because they change. Without them, signatures are
still checked but every signer is reported as unconfirmed.

## Development

```sh
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest
python tests/make_fixtures.py   # rebuild the signed test images
```

The tests never use the machine's cached trust lists; trusted-signer cases
use the C2PA test root as their only anchor.

```
src/aiimagecheck/
  credentials.py   Content Credentials: intact? who signed? what happened?
  labels.py        AI labels in XMP, EXIF and PNG text
  sources.py       the IPTC digital source type vocabulary
  report.py        the verdict and its wording
  trust.py         downloading and loading the trust lists
  cli.py           the command line
  server.py        the local drop-an-image page (page.html)
```

Built on the official [c2pa-python](https://github.com/contentauth/c2pa-python)
library and [Pillow](https://python-pillow.org/).

## Licence

MIT. See [LICENSE](LICENSE). Test images in `tests/fixtures/caidata` are
from c2pa-python, under its MIT licence.
