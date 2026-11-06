"""Record hashes of the V1 source actually reused; never read runtime or secret files."""

import hashlib
import json
from pathlib import Path

SOURCE = Path("/Users/ashutoshanand/Downloads/Nyay sathi")
TARGET = Path(__file__).resolve().parents[2]
EXCLUDED = {
    ".git",
    ".venv",
    "node_modules",
    "runtime",
    "output",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".tools",
    "dist",
    "test-results",
    "playwright-report",
}


def main():
    manifest = []
    for path in sorted(SOURCE.rglob("*")):
        relative = path.relative_to(SOURCE)
        if (
            not path.is_file()
            or any(p in EXCLUDED for p in relative.parts)
            or path.name == ".env"
            or path.suffix == ".tsbuildinfo"
        ):
            continue
        copied = TARGET / relative
        if copied.exists():
            manifest.append(
                {
                    "path": str(relative),
                    "v1_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "v2_sha256_at_snapshot": hashlib.sha256(copied.read_bytes()).hexdigest(),
                }
            )
    output = TARGET / "docs" / "v1-source-manifest.json"
    output.write_text(
        json.dumps(
            {
                "source": str(SOURCE),
                "description": "Reference hashes captured during V2 implementation; differences include intentional V2 edits.",
                "files": manifest,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"Recorded {len(manifest)} source references in {output}")


if __name__ == "__main__":
    main()
