"""Read an image's Content Credentials (C2PA) with the official library.

Three questions, kept apart because they have different strengths:

1. Is the record intact? (the signature and the image hash check out)
2. Who signed it, and is that signer on a C2PA trust list? A valid
   signature from an unknown certificate proves the record was not altered,
   not who made it: anyone can make a certificate that says "OpenAI".
3. What does the record say happened? Created, edited, by which tool, and
   whether AI was involved. Read from every manifest in the file, because an
   AI image edited later by an ordinary tool is still built on AI.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, field

import c2pa

from . import sources


@dataclass
class Action:
    action: str            # "c2pa.created", "c2pa.edited", ...
    software: str          # the tool that did it, when recorded
    source_type: str       # IPTC digital source type short name, or ""
    manifest: str          # which manifest recorded it
    active: bool           # recorded by the image's own (latest) manifest


@dataclass
class Ingredient:
    title: str
    relationship: str      # "parentOf" is the image this one was made from
    thumbnail: bytes | None = None
    thumbnail_type: str = ""


@dataclass
class Credentials:
    present: bool
    state: str = ""                 # "Trusted", "Valid" or "Invalid" (C2PA validation state)
    problems: list[str] = field(default_factory=list)   # failure codes, e.g. "assertion.dataHash.mismatch"
    signer: str = ""                # certificate issuer (organisation)
    signer_name: str = ""           # certificate common name
    signed_at: str = ""             # when signed, if timestamped (UTC)
    trust_checked: bool = False     # were trust lists loaded?
    generator: str = ""             # the tool that wrote the record
    actions: list[Action] = field(default_factory=list)
    ingredients: list[Ingredient] = field(default_factory=list)
    error: str = ""                 # the library could not read the record at all

    @property
    def ai_made(self) -> bool:
        return any(a.source_type in sources.AI_MADE for a in self.actions)

    @property
    def ai_edited(self) -> bool:
        return any(a.source_type in sources.AI_EDITED for a in self.actions)

    @property
    def original(self) -> Ingredient | None:
        """The image this one was made from, when the record kept a thumbnail of it."""
        for i in self.ingredients:
            if i.relationship == "parentOf" and i.thumbnail:
                return i
        return None


def read(data: bytes, trust: dict | None = None) -> Credentials:
    """Read the Content Credentials in an image's bytes.

    trust is the C2PA settings for trust lists (see trust.py); without it the
    signature is still checked but the signer cannot be confirmed.
    """
    context = c2pa.Context.from_dict(trust) if trust else None
    try:
        reader = c2pa.Reader(None, io.BytesIO(data), context=context)
    except c2pa.C2paError as err:
        if "ManifestNotFound" in type(err).__name__ or "no JUMBF" in str(err):
            return Credentials(present=False)
        # A record is there but unreadable, or the file type is unsupported.
        return Credentials(present=False, error=str(err))
    try:
        store = json.loads(reader.json())
        return _from_store(store, reader, trust_checked=bool(trust))
    finally:
        reader.close()
        if context:
            context.close()


def _from_store(store: dict, reader: c2pa.Reader, trust_checked: bool) -> Credentials:
    manifests = store.get("manifests", {})
    active_label = store.get("active_manifest", "")
    active = manifests.get(active_label, {})

    sig = active.get("signature_info") or {}
    gen = active.get("claim_generator") or ", ".join(
        " ".join(filter(None, [g.get("name"), g.get("version")]))
        for g in active.get("claim_generator_info") or []
    )
    cred = Credentials(
        present=True,
        state=store.get("validation_state", ""),
        problems=_failures(store),
        signer=sig.get("issuer", ""),
        signer_name=sig.get("common_name", ""),
        signed_at=sig.get("time", ""),
        trust_checked=trust_checked,
        generator=gen,
    )
    for label, manifest in manifests.items():
        cred.actions.extend(_actions(manifest, label, active=(label == active_label)))
    for ing in active.get("ingredients", []):
        cred.ingredients.append(_ingredient(ing, manifests, reader))
    return cred


def _failures(store: dict) -> list[str]:
    """Failure codes from the validation, without the noise of 'untrusted'
    when no trust lists were loaded (that is reported separately)."""
    results = store.get("validation_results") or {}
    failures = (results.get("activeManifest") or {}).get("failure")
    if failures is None:  # older library output
        failures = store.get("validation_status") or []
    # "untrusted" is not a defect in the record: it is the trust question,
    # which the validation state (Trusted / Valid) already answers.
    return [f.get("code", "") for f in failures
            if f.get("code") and f.get("code") != "signingCredential.untrusted"]


def _actions(manifest: dict, label: str, active: bool) -> list[Action]:
    out = []
    for assertion in manifest.get("assertions", []):
        if not assertion.get("label", "").startswith("c2pa.actions"):
            continue
        for a in (assertion.get("data") or {}).get("actions", []):
            agent = a.get("softwareAgent") or ""
            if isinstance(agent, dict):
                agent = " ".join(filter(None, [agent.get("name"), agent.get("version")]))
            out.append(Action(
                action=a.get("action", ""),
                software=str(agent),
                source_type=sources.short_name(a.get("digitalSourceType", "")),
                manifest=label,
                active=active,
            ))
    return out


def _ingredient(ing: dict, manifests: dict, reader: c2pa.Reader) -> Ingredient:
    out = Ingredient(title=ing.get("title", ""), relationship=ing.get("relationship", ""))
    thumb = ing.get("thumbnail")
    # An ingredient that had its own Content Credentials keeps its thumbnail
    # in its own manifest.
    if not thumb and ing.get("active_manifest") in manifests:
        thumb = manifests[ing["active_manifest"]].get("thumbnail")
    if thumb and thumb.get("identifier"):
        buf = io.BytesIO()
        try:
            reader.resource_to_stream(thumb["identifier"], buf)
            out.thumbnail = buf.getvalue() or None
            out.thumbnail_type = thumb.get("format", "")
        except c2pa.C2paError:
            pass  # a missing thumbnail is not worth failing the report over
    return out
