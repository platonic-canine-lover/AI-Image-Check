"""Say whether an image's own records show it was made or edited with AI.

The tool reports evidence, never a guess: Content Credentials (C2PA) when the
file carries them, and AI labels in its metadata. When neither is there it
says so, and that means "unknown", not "real".
"""

__version__ = "0.1.0"
