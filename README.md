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

> **Status: v1.** Content Credentials and metadata labels, a command line
> and a local page, all tested (see [Testing](#testing)). Checked against
> real ChatGPT output: "Made with AI", signed by OpenAI, on the trust lists.
> Firefly, Gemini and Photoshop generative fill are not checked yet. See
> [Roadmap](#roadmap).

## What it reads

| Evidence | Strength | Where it comes from |
|---|---|---|
| **Content Credentials** (C2PA) | Signed. Can't be altered without the check failing. | Tools and devices that sign their output, e.g. Adobe Firefly and Photoshop, OpenAI's image generation, some cameras and phones |
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
- **Spot an AI image whose records were stripped.** Many apps and platforms
  remove metadata when an image is shared, and a screenshot removes
  everything. A
  detector model that guesses from the pixels is planned (v2), but only
  after it has been measured on a labelled test set: a wrong "this is AI" on
  someone's real photo does harm.
- **Read invisible watermarks** such as Google's SynthID. Only their makers
  can check those.

## Install

Python 3.10 or later (developed and tested on 3.12; the c2pa-python
library itself needs 3.10).

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

What *is* shipped is the short list of certificate uses (EKUs) a C2PA signer
may have, copied from the interim list's `store.cfg`. Without it the library
rejects real signers such as OpenAI ("certificate missing required EKU"), and
a genuine ChatGPT image was reported as broken.

## Testing

```sh
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest
.venv/bin/python tests/make_fixtures.py   # rebuild the signed test images
```

54 tests, no network needed. They never use the machine's cached trust
lists; trusted-signer cases use the C2PA test root as their only anchor.

| Test images | What they cover |
|---|---|
| `tests/fixtures/caidata/` (official C2PA samples) | no credentials; computer-made but not AI; an edit that kept its source thumbnail; a broken signature; an image changed after signing; a real Adobe-signed composite |
| `tests/fixtures/made/` (built by `make_fixtures.py`) | made by AI; edited with AI; AI then cropped in an ordinary editor; a camera photo |
| `tests/fixtures/generators/` (saved straight from the generator) | a real ChatGPT image, signed by OpenAI; see its README |
| generated in the tests with Pillow | each metadata label, and look-alikes that must not count (a caption naming OpenAI, `algorithmicMedia`, a PNG chunk without generator settings) |

It has also been run by hand over older official C2PA samples with long
edit chains and several kinds of damage; each was read without error and
every damaged one was reported as broken.

**Continuous integration.** Each night a self-hosted
[ci-runner](https://github.com/platonic-canine-lover/CI-runner) builds any
new commit on `main`: it creates the virtual environment, installs the
package, byte-compiles `src` and `tests`, runs the tests, and reports the
result to GitHub as a commit status.

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

## Roadmap

| | |
|---|---|
| ✅ v1 | Content Credentials (integrity, trust lists, actions, source thumbnails), metadata labels, CLI, local page |
| ✅ | Real generator output: ChatGPT (gpt-image, signed by OpenAI) |
| next | The same for Firefly, Gemini and Photoshop generative fill |
| next | Measure what common apps and platforms strip (messaging apps, social networks, screenshots), so the "no evidence" wording can name them accurately |
| v2 | A local detector score for images with no records, added only after candidate models are measured on a labelled set, and always reported as an estimate |

Built on the official [c2pa-python](https://github.com/contentauth/c2pa-python)
library and [Pillow](https://python-pillow.org/).

## Licence

MIT. See [LICENSE](LICENSE). Test images in `tests/fixtures/caidata` are
from c2pa-python, under its MIT licence. The image in `tests/fixtures/generators`
was made by the maintainer with ChatGPT for these tests.
