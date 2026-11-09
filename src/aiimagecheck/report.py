"""Turn what was found into a verdict a person can act on.

The rules, in order:
1. A broken record is never believed. If the image or its record changed
   after signing, what it claims is reported as a claim, not a fact.
2. Content Credentials outrank metadata labels: one is signed, the other is
   text anyone can type.
3. A valid signature from a signer not on a trust list proves the record is
   intact, not who made it. The report says which.
4. Finding nothing never means "real". Most platforms strip these records;
   the report says "no evidence", and why that is not a clean bill.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field

from . import sources
from .credentials import Credentials
from .labels import Label

AI_MADE = "ai_made"
AI_EDITED = "ai_edited"
NO_AI_RECORDED = "no_ai_recorded"
BROKEN = "broken"
AI_LABEL = "ai_label"
NONE = "no_evidence"
UNREADABLE = "unreadable"


@dataclass
class Report:
    name: str
    verdict: str
    headline: str
    reasons: list[str] = field(default_factory=list)
    credentials: Credentials | None = None
    labels: list[Label] = field(default_factory=list)

    def to_dict(self, thumbnails: bool = False) -> dict:
        c = self.credentials
        out = {"name": self.name, "verdict": self.verdict, "headline": self.headline, "reasons": self.reasons,
               "labels": [vars(l) for l in self.labels]}
        if c and c.present:
            out["credentials"] = {
                "state": c.state, "problems": c.problems, "signer": c.signer, "signerName": c.signer_name,
                "signedAt": c.signed_at, "trustChecked": c.trust_checked, "generator": c.generator,
                "actions": [vars(a) for a in c.actions],
                "ingredients": [
                    {"title": i.title, "relationship": i.relationship, "hasThumbnail": bool(i.thumbnail),
                     **({"thumbnail": f"data:{i.thumbnail_type or 'image/jpeg'};base64,"
                                      + base64.b64encode(i.thumbnail).decode()} if thumbnails and i.thumbnail else {})}
                    for i in c.ingredients
                ],
            }
        return out

    def to_text(self) -> str:
        lines = [f"{self.name}", f"  {self.headline}"]
        lines += [f"  - {r}" for r in self.reasons]
        c = self.credentials
        if c and c.present:
            lines.append("  Content Credentials:")
            lines.append(f"    record: {c.state}" + (f" ({', '.join(c.problems)})" if c.problems else ""))
            if c.generator:
                lines.append(f"    written by: {c.generator}")
            for a in c.actions:
                what = f"{a.action}" + (f" by {a.software}" if a.software else "")
                if a.source_type:
                    what += f": {sources.describe(a.source_type)}"
                lines.append(f"    {'' if a.active else '(earlier) '}{what}")
            for i in c.ingredients:
                lines.append(f"    ingredient: {i.title or '(untitled)'} [{i.relationship}]"
                             + (" with thumbnail" if i.thumbnail else ""))
        if self.labels:
            lines.append("  Metadata labels (unverified):")
            lines += [f"    {l.where}: {l.value}" for l in self.labels]
        return "\n".join(lines)


def build(name: str, cred: Credentials, labels: list[Label], read_error: str = "") -> Report:
    r = Report(name=name, verdict=NONE, headline="", credentials=cred, labels=labels)

    if cred.present and cred.state == "Invalid":
        r.verdict, r.headline = BROKEN, "Content Credentials are broken: this image or its record changed after signing."
        r.reasons.append("What the record says can't be relied on: " + ", ".join(cred.problems or ["validation failed"]) + ".")
        if cred.ai_made or cred.ai_edited:
            r.reasons.append("The broken record claims AI was used.")
        return r

    if cred.present:
        made_now = any(a.source_type in sources.AI_MADE and a.active for a in cred.actions)
        if cred.ai_made:
            r.verdict = AI_MADE
            r.headline = "Made with AI." if made_now else "Made from an AI-generated image."
        elif cred.ai_edited:
            r.verdict, r.headline = AI_EDITED, "Edited with AI."
        else:
            r.verdict, r.headline = NO_AI_RECORDED, "Content Credentials found; they record no AI use."
            r.reasons.append("A record covers only what the signing tools knew; edits made elsewhere are not in it.")
        tools = sorted({a.software for a in cred.actions
                        if a.software and a.source_type in sources.AI_MADE | sources.AI_EDITED})
        if tools:
            r.reasons.append("Recorded AI tool: " + ", ".join(tools) + ".")
        r.reasons.append(_signer_line(cred))
        if cred.original:
            r.reasons.append(f"The record keeps a thumbnail of the image it was made from ({cred.original.title or 'untitled'}).")
        if labels:
            r.reasons.append("Metadata labels agree or add detail; see below.")
        return r

    if any(l.meaning in (AI_MADE, AI_EDITED, "ai_tool") for l in labels):
        r.verdict = AI_LABEL
        made = any(l.meaning == AI_MADE for l in labels)
        r.headline = ("AI label found: " + ("made with AI" if made else "AI was used") + " (unverified).")
        r.reasons.append("Metadata labels are not signed: anyone can add or remove one.")
        return r

    if read_error:
        r.verdict, r.headline = UNREADABLE, "Could not read this file as an image."
        r.reasons.append(read_error)
        return r
    r.headline = "No AI evidence found. That does not mean the image is real."
    r.reasons.append("Many apps and platforms strip these records when an image is shared, and a"
                     " screenshot removes them entirely, so an AI image can arrive with no trace.")
    if cred.error:
        r.reasons.append(f"Content Credentials could not be read: {cred.error}")
    return r


def _signer_line(c: Credentials) -> str:
    who = c.signer or c.signer_name or "an unnamed signer"
    if c.state == "Trusted":
        return f"Signed by {who}, a signer on the C2PA trust lists."
    if c.trust_checked:
        return (f"Signed by {who}, which is NOT on the C2PA trust lists: the record is intact,"
                " but who signed it is unconfirmed.")
    return (f"Signed by {who} (unconfirmed: trust lists not loaded;"
            " run `aiimagecheck update-trust`)")
