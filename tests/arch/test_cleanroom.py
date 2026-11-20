from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS = ("quartz", "compat", "tools")
FORBIDDEN = (
    "SPDX-License-Identifier",
    "GNU General Public License",
    "Copyright (C) Blender",
    "Copyright Blender",
    "Maxon Computer",
    "All rights reserved",
)


def test_cleanroom():
    violations = []
    for d in SCAN_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            if "__pycache__" in p.parts:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            low = text.lower()
            for marker in FORBIDDEN:
                if marker.lower() in low:
                    violations.append(f"{p}: contains {marker!r}")
    assert not violations, "\n".join(violations)
