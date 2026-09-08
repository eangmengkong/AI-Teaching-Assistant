r"""
Repair mojibake in frontend source files.

Mojibake happens when UTF-8 text is mis-decoded as Windows-1252 and re-saved,
turning "..." into "...", the calendar emoji into garbage, etc.

Run from the project root:
    backend\\venv\\Scripts\\python.exe scripts\\fix_mojibake.py

Only files that actually contain broken sequences are rewritten (as UTF-8).
"""
import sys
from pathlib import Path

import ftfy

ROOT = Path(__file__).resolve().parents[1]
TARGET_DIRS = [ROOT / "frontend" / "src"]
EXTENSIONS = {".ts", ".tsx", ".css", ".json"}

# Tell-tale fragments of UTF-8-as-Windows-1252 double encoding.
MARKERS = ["â€", "âœ", "âš", "Â·", "ðŸ", "â†", "â°", "Ã", "ï¸"]


def looks_broken(text: str) -> bool:
    return any(marker in text for marker in MARKERS)


def repair(text: str) -> str:
    return ftfy.fix_text(text, config=ftfy.TextFixerConfig(uncurl_quotes=False))


def main() -> int:
    repaired = 0
    for base in TARGET_DIRS:
        for path in sorted(base.rglob("*")):
            if path.suffix not in EXTENSIONS or not path.is_file():
                continue
            raw = path.read_bytes()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                # File was saved as Windows-1252: decode it with that codepage.
                text = raw.decode("cp1252", errors="replace")
                print(f"non-UTF-8 file (was cp1252): {path.relative_to(ROOT)}")

            if not looks_broken(text):
                continue

            fixed = repair(text)
            if fixed == text:
                continue

            path.write_bytes(fixed.encode("utf-8"))
            before = text.splitlines()
            after = fixed.splitlines()
            diff = sum(1 for i in range(min(len(before), len(after))) if before[i] != after[i])
            print(f"repaired: {path.relative_to(ROOT)} ({diff} line(s) changed)")
            repaired += 1

    print(f"done — {repaired} file(s) repaired")
    return 0


if __name__ == "__main__":
    sys.exit(main())