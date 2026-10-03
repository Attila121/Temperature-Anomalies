"""Check the bundled release files against the recorded SHA-256 manifest."""

import hashlib
import json
import sys
from pathlib import Path

from project_paths import ROOT


def verify_release(root=ROOT):
    root = Path(root).resolve()
    manifest = json.loads((root / "release-manifest.json").read_text(encoding="utf-8"))
    errors = []
    for name, expected in manifest["files"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            errors.append(f"Missing or invalid path: {name}")
            continue
        with path.open("rb") as handle:
            actual = hashlib.file_digest(handle, "sha256").hexdigest()
        if actual != expected["sha256"] or path.stat().st_size != expected["bytes"]:
            errors.append(f"Changed file: {name}")
    return errors, len(manifest["files"])


def main():
    try:
        errors, count = verify_release()
    except (OSError, ValueError, KeyError) as exc:
        print(f"Release verification failed: {exc}", file=sys.stderr)
        return 1
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Verified {count} bundled files against release-manifest.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
