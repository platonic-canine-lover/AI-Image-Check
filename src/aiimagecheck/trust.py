"""The C2PA trust lists: which signing certificates belong to known makers.

Without them a signature only proves the record was not altered. With them,
"signed by OpenAI" means the certificate really chains to one that the C2PA
(or the Content Credentials interim list) has accepted.

Two lists, both public:
- the C2PA conformance trust list (the formal programme), and
- the Content Credentials interim list used by contentcredentials.org/verify,
  which covers signers from before the conformance programme existed.

They are downloaded on request (`aiimagecheck update-trust`) and cached, not
shipped with the code: they change, and a stale copy would wrongly reject
new signers.
"""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SOURCES = {
    "c2pa-anchors.pem": "https://raw.githubusercontent.com/c2pa-org/conformance-public/main/trust-list/C2PA-TRUST-LIST.pem",
    "interim-anchors.pem": "https://contentcredentials.org/trust/anchors.pem",
    "interim-allowed.sha256.txt": "https://contentcredentials.org/trust/allowed.sha256.txt",
    "interim-store.cfg": "https://contentcredentials.org/trust/store.cfg",
}
MAX_BYTES = 2_000_000  # each list is tens of KB; anything this big is wrong

# The certificate uses ("extended key usages") a C2PA signer may have, as in
# the interim list's store.cfg. Without them the library rejects real signers
# such as OpenAI ("certificate missing required EKU") and the record looks
# broken. These are standard OIDs, not a trust list, so they ship with the
# code and apply even before `update-trust` has been run.
BASE_TRUST_CONFIG = """\
//id-kp-emailProtection
1.3.6.1.5.5.7.3.4
//id-kp-documentSigning
1.3.6.1.5.5.7.3.36
//id-kp-timeStamping
1.3.6.1.5.5.7.3.8
//id-kp-OCSPSigning
1.3.6.1.5.5.7.3.9
// MS C2PA Signing
1.3.6.1.4.1.311.76.59.1.9
// c2pa-claim_signing
1.3.6.1.4.1.62558.2.1
"""


def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(Path.home(), ".cache")
    return Path(base) / "aiimagecheck"


def update(directory: Path | None = None, timeout: float = 20.0) -> dict:
    """Download every list. Writes nothing unless all of them arrive, so a
    half-failed update never leaves a mixed set behind."""
    directory = directory or cache_dir()
    fetched = {}
    for name, url in SOURCES.items():
        req = urllib.request.Request(url, headers={"User-Agent": "ai-image-check"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError(f"{url} is larger than {MAX_BYTES} bytes")
        if name.endswith(".pem") and b"BEGIN CERTIFICATE" not in body:
            raise ValueError(f"{url} did not return certificates")
        fetched[name] = body
    directory.mkdir(parents=True, exist_ok=True)
    for name, body in fetched.items():
        (directory / name).write_bytes(body)
    info = {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "sources": SOURCES}
    (directory / "info.json").write_text(json.dumps(info, indent=2))
    return info


def settings(directory: Path | None = None) -> dict | None:
    """C2PA settings that turn trust checking on, or None if the lists have
    not been downloaded."""
    directory = directory or cache_dir()
    if not all((directory / name).is_file() for name in SOURCES):
        return None
    anchors = (directory / "c2pa-anchors.pem").read_text() + "\n" + (directory / "interim-anchors.pem").read_text()
    return {
        "verify": {"verify_trust": True},
        "trust": {
            "trust_anchors": anchors,
            "allowed_list": (directory / "interim-allowed.sha256.txt").read_text(),
            "trust_config": (directory / "interim-store.cfg").read_text(),
        },
    }


def with_base_ekus(settings: dict | None) -> dict:
    """The settings to read with: the given trust settings (or none, which
    checks the signature but not the signer), plus the standard signer
    certificate uses when the settings bring no list of their own."""
    out = {"verify": {"verify_trust": False}, "trust": {}}
    if settings:
        out = {k: dict(v) if isinstance(v, dict) else v for k, v in settings.items()}
        out.setdefault("trust", {})
    out["trust"].setdefault("trust_config", BASE_TRUST_CONFIG)
    return out


def updated_at(directory: Path | None = None) -> str:
    try:
        return json.loads(((directory or cache_dir()) / "info.json").read_text()).get("updated", "")
    except (OSError, ValueError):
        return ""
