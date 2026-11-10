"""aiimagecheck: say whether a file's own records show AI was used.

    aiimagecheck photo.jpg [more.png report.pdf ...] [--json] [--save-originals DIR]
    aiimagecheck serve [--port 3103]
    aiimagecheck update-trust
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, check, trust

EXIT_OK, EXIT_ERROR, EXIT_USAGE = 0, 1, 2


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "serve":
        return _serve(argv[1:])
    if argv and argv[0] == "update-trust":
        return _update_trust()
    return _check(argv)


def _check(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="aiimagecheck", description="Report what an image's or PDF's own records say about AI use.",
                                epilog="Other commands: `aiimagecheck serve`, `aiimagecheck update-trust`.")
    p.add_argument("images", nargs="+", type=Path, metavar="file", help="image or PDF files to check")
    p.add_argument("--json", action="store_true", help="print JSON instead of text")
    p.add_argument("--save-originals", type=Path, metavar="DIR",
                   help="save any recorded source-image thumbnails into DIR")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    try:
        args = p.parse_args(argv)
    except SystemExit as e:
        return EXIT_USAGE if e.code else EXIT_OK

    settings = check.default_trust()
    if settings is None and not args.json:
        print("note: trust lists not downloaded, so signers can't be confirmed (run `aiimagecheck update-trust`)\n",
              file=sys.stderr)
    status, results = EXIT_OK, []
    for path in args.images:
        try:
            data = path.read_bytes()
        except OSError as err:
            print(f"{path}: {err.strerror}", file=sys.stderr)
            status = EXIT_ERROR
            continue
        r = check.check_bytes(data, str(path), settings)
        results.append(r)
        if args.save_originals:
            _save_originals(r, path, args.save_originals)
        if not args.json:
            print(r.to_text() + "\n")
    if args.json:
        print(json.dumps([r.to_dict() for r in results], indent=2))
    return status


def _save_originals(r, path: Path, directory: Path) -> None:
    c = r.credentials
    if not (c and c.present):
        return
    directory.mkdir(parents=True, exist_ok=True)
    for n, ing in enumerate(i for i in c.ingredients if i.thumbnail):
        ext = {"image/png": ".png", "image/webp": ".webp"}.get(ing.thumbnail_type, ".jpg")
        dest = directory / f"{path.stem}.{ing.relationship or 'ingredient'}.{n}{ext}"
        dest.write_bytes(ing.thumbnail)
        print(f"saved {ing.relationship} thumbnail: {dest}", file=sys.stderr)


def _update_trust() -> int:
    try:
        info = trust.update()
    except Exception as err:  # network, HTTP or content errors: report, don't trace
        print(f"update-trust failed: {err}", file=sys.stderr)
        return EXIT_ERROR
    print(f"trust lists updated {info['updated']} into {trust.cache_dir()}")
    return EXIT_OK


def _serve(argv: list[str]) -> int:
    from . import server
    p = argparse.ArgumentParser(prog="aiimagecheck serve", description="A local page to drop images and PDFs onto.")
    p.add_argument("--listen", default="127.0.0.1:3103", help="loopback address (default 127.0.0.1:3103)")
    try:
        args = p.parse_args(argv)
    except SystemExit as e:
        return EXIT_USAGE if e.code else EXIT_OK
    return server.run(args.listen)


if __name__ == "__main__":
    raise SystemExit(main())
