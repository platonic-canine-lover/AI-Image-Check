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
5. For a PDF the records are about the file, never its words: no verdict
   here says whether a person or a model wrote the text.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field

from . import sources
from .credentials import Credentials
from .labels import Label
from .pdf import Document

AI_MADE = "ai_made"
AI_EDITED = "ai_edited"
NO_AI_RECORDED = "no_ai_recorded"
BROKEN = "broken"
AI_LABEL = "ai_label"
NONE = "no_evidence"
UNREADABLE = "unreadable"

IMAGE = "image"
PDF = "pdf"
_NOUN = {IMAGE: "image", PDF: "PDF"}


@dataclass
class Report:
    name: str
    verdict: str
    headline: str
    reasons: list[str] = field(default_factory=list)
    credentials: Credentials | None = None
    labels: list[Label] = field(default_factory=list)
    kind: str = IMAGE
    document: Document | None = None   # a PDF's stated makers

    def to_dict(self, thumbnails: bool = False) -> dict:
        c = self.credentials
        out = {"name": self.name, "kind": self.kind, "verdict": self.verdict, "headline": self.headline,
               "reasons": self.reasons, "labels": [vars(l) for l in self.labels]}
        if self.document and (self.document.creator or self.document.producer):
            out["document"] = vars(self.document)
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
        d = self.document
        if d and (d.creator or d.producer):
            lines.append("  PDF info (unverified):")
            if d.creator:
                lines.append(f"    written in: {d.creator}")
            if d.producer:
                lines.append(f"    PDF made by: {d.producer}")
        return "\n".join(lines)


def build(name: str, cred: Credentials, labels: list[Label], read_error: str = "",
          kind: str = IMAGE, document: Document | None = None) -> Report:
    r = Report(name=name, verdict=NONE, headline="", credentials=cred, labels=labels, kind=kind, document=document)
    noun = _NOUN[kind]

    if cred.present and cred.state == "Invalid":
        r.verdict, r.headline = BROKEN, f"Content Credentials are broken: this {noun} or its record changed after signing."
        r.reasons.append("What the record says can't be relied on: " + ", ".join(cred.problems or ["validation failed"]) + ".")
        if cred.ai_made or cred.ai_edited:
            r.reasons.append("The broken record claims AI was used.")
        return r

    if cred.present:
        made_now = any(a.source_type in sources.AI_MADE and a.active for a in cred.actions)
        if cred.ai_made:
            r.verdict = AI_MADE
            r.headline = "Made with AI." if made_now else f"Made from an AI-generated {'file' if kind == PDF else 'image'}."
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
            r.reasons.append(f"The record keeps a thumbnail of the {'file' if kind == PDF else 'image'} it was made from"
                             f" ({cred.original.title or 'untitled'}).")
        if labels:
            r.reasons.append("Metadata labels agree or add detail; see below.")
        if kind == PDF:
            r.reasons.append(_PDF_SCOPE)
        return r

    if any(l.meaning in (AI_MADE, AI_EDITED, "ai_tool") for l in labels):
        r.verdict = AI_LABEL
        made = any(l.meaning == AI_MADE for l in labels)
        r.headline = ("AI label found: " + ("made with AI" if made else "AI was used") + " (unverified).")
        r.reasons.append("Metadata labels are not signed: anyone can add or remove one.")
        if kind == PDF:
            r.reasons.append(_PDF_SCOPE)
        return r

    if read_error:
        r.verdict, r.headline = UNREADABLE, f"Could not read this {'PDF' if kind == PDF else 'file as an image'}."
        r.reasons.append(read_error)
        return r
    if kind == PDF:
        r.headline = "No AI evidence found. That does not mean a person wrote it."
        r.reasons.append("Few tools that make PDFs record AI use, and printing or re-saving a PDF drops any"
                         " record that was there, so an AI-written document usually carries no trace.")
        if made_by := _made_by(document):
            r.reasons.append(made_by)
        r.reasons.append(_PDF_SCOPE)
    else:
        r.headline = "No AI evidence found. That does not mean the image is real."
        r.reasons.append("Many apps and platforms strip these records when an image is shared, and a"
                         " screenshot removes them entirely, so an AI image can arrive with no trace.")
    if cred.error:
        r.reasons.append(f"Content Credentials could not be read: {cred.error}")
    return r


_PDF_SCOPE = ("This reads the file's records only: it does not read the text, so it cannot tell whether"
              " the words were written by AI, and pictures inside the PDF are not checked.")


def _made_by(d: Document | None) -> str:
    """What the PDF says made it. Ordinary software, or it would be a label."""
    if not d or not (d.creator or d.producer):
        return ""
    parts = ([f"written in {d.creator}"] if d.creator else []) + ([f"made into a PDF by {d.producer}"] if d.producer else [])
    return "The PDF says it was " + " and ".join(parts) + " (unsigned; neither is an AI tool this check knows)."


def _signer_line(c: Credentials) -> str:
    who = c.signer or c.signer_name or "an unnamed signer"
    if c.state == "Trusted":
        return f"Signed by {who}, a signer on the C2PA trust lists."
    if c.trust_checked:
        return (f"Signed by {who}, which is NOT on the C2PA trust lists: the record is intact,"
                " but who signed it is unconfirmed.")
    return (f"Signed by {who} (unconfirmed: trust lists not loaded;"
            " run `aiimagecheck update-trust`)")
